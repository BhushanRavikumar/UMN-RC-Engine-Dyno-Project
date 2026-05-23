"""Background controller for a VESC-based motor controller.

This module wraps the binary VESC protocol provided by ``pyvesc`` with:

- A *single* background I/O thread that owns the serial port. The GUI never
  touches ``pyserial`` directly, which avoids the data-corruption you get
  when two threads call ``write()`` concurrently.
- A "sticky setpoint" model: the most recent command (RPM / current /
  brake / handbrake / duty / position) is re-sent at a fixed cadence so
  the VESC's command watchdog never trips and the motor does not
  unexpectedly coast to a stop.
- Periodic ``GetValues`` polling at the same cadence. Decoded telemetry is
  emitted as a Qt signal so the GUI can stay completely off the serial
  thread.

Units
-----
- RPM is electrical RPM (the VESC's native unit).
- Currents are in **Amps** (the convenience wrappers in this class
  internally scale to the milli-amps the VESC firmware expects).
- Duty cycle is a fraction in ``[-1.0, 1.0]``.
- Position is in degrees, ``0..360``.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Optional

import serial
from PyQt6.QtCore import QObject, pyqtSignal
from pyvesc.protocol.base import VESCMessage
from pyvesc.protocol.interface import decode, encode, encode_request
from pyvesc.VESC.messages import (
    Alive,
    GetValues,
    SetCurrent,
    SetCurrentBrake,
    SetDutyCycle,
    SetPosition,
    SetRPM,
    VedderCmd,
)

log = logging.getLogger(__name__)


# ``pyvesc`` does not ship a SetHandbrake class, so we declare one. The VESC
# firmware expects an int32 of (handbrake_amps * 1000), matching SetCurrent.
class SetHandbrake(metaclass=VESCMessage):  # type: ignore[misc]
    id = VedderCmd.COMM_SET_HANDBRAKE
    fields = [("handbrake", "i", 1000)]


class ControlMode(Enum):
    RELEASED = auto()     # Motor coasts; loop sends Alive only.
    RPM = auto()
    CURRENT = auto()
    BRAKE = auto()
    HANDBRAKE = auto()
    DUTY = auto()
    POSITION = auto()


@dataclass(frozen=True)
class VescTelemetry:
    """One snapshot of VESC measurements."""

    rpm: float
    voltage_v: float
    motor_current_a: float
    input_current_a: float
    duty: float                # fraction in [-1, 1]
    mosfet_temp_c: float
    motor_temp_c: float
    amp_hours_consumed: float
    watt_hours_consumed: float
    tachometer: int            # mechanical position counter
    t_monotonic: float

    @classmethod
    def from_pyvesc(cls, m: Any) -> "VescTelemetry":
        """Build a snapshot from whatever fields the running firmware exposes.

        Older VESC firmwares omit some fields, so every attribute is fetched
        with a safe default.
        """

        def _get(name: str, default: float = 0.0) -> float:
            return float(getattr(m, name, default))

        return cls(
            rpm=_get("rpm"),
            voltage_v=_get("v_in"),
            motor_current_a=_get("current_motor"),
            input_current_a=_get("current_in"),
            duty=_get("duty_now"),
            mosfet_temp_c=_get("temp_fet_filtered", _get("temp_fet")),
            motor_temp_c=_get("temp_motor_filtered", _get("temp_motor")),
            amp_hours_consumed=_get("amp_hours"),
            watt_hours_consumed=_get("watt_hours"),
            tachometer=int(_get("tachometer", 0)),
            t_monotonic=time.monotonic(),
        )


class VescController(QObject):
    """Thread-safe asynchronous wrapper around a VESC over UART/USB-CDC.

    Signals
    -------
    telemetry : VescTelemetry
        Emitted every ``poll_interval_s`` seconds when a valid response
        comes back from the VESC.
    connection_changed : bool
        Emitted with ``True`` on successful connect and ``False`` on close
        / I/O failure.
    error : str
        Emitted on any I/O failure.
    """

    telemetry = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._ser: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # The active setpoint and its desired wire encoding. ``_setpoint_bytes``
        # is what the I/O thread re-sends on every tick; assigning a new
        # bytes object atomically swaps the "sticky" command.
        self._mode: ControlMode = ControlMode.RELEASED
        self._setpoint_value: float = 0.0
        self._setpoint_bytes: bytes = encode(Alive())
        self._one_shot: bytes = b""

        # Pre-encoded GetValues request and the expected response length.
        msg = GetValues()
        self._get_values_msg: bytes = encode_request(msg)
        self._get_values_expected_len: int = msg._full_msg_size  # type: ignore[attr-defined]

        # Tunables.
        self.poll_interval_s: float = 0.020       # 50 Hz
        self.response_timeout_s: float = 0.080

    # ============================================================ lifecycle

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self, port: str, baud: int = 115_200) -> None:
        if self.is_open:
            self.close()

        try:
            self._ser = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=self.response_timeout_s,
                write_timeout=0.2,
            )
        except serial.SerialException as exc:
            self._ser = None
            log.error("Could not open VESC on %s: %s", port, exc)
            self.error.emit(f"VESC open failed: {exc}")
            return

        with self._lock:
            self._mode = ControlMode.RELEASED
            self._setpoint_value = 0.0
            self._setpoint_bytes = encode(Alive())
            self._one_shot = b""

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._io_loop, name="VescController", daemon=True
        )
        self._thread.start()
        self.connection_changed.emit(True)
        log.info("VESC opened on %s @ %d", port, baud)

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._ser is not None:
            # Make a best effort to release the motor before disconnecting.
            try:
                self._ser.write(encode(SetCurrent(0)))
                self._ser.flush()
            except (serial.SerialException, OSError):
                pass
            try:
                self._ser.close()
            except serial.SerialException:
                pass
            self._ser = None

        self.connection_changed.emit(False)
        log.info("VESC closed")

    # ============================================================== control

    @property
    def mode(self) -> ControlMode:
        with self._lock:
            return self._mode

    @property
    def setpoint(self) -> float:
        with self._lock:
            return self._setpoint_value

    def _set_command(
        self,
        mode: ControlMode,
        value: float,
        wire: bytes,
        sticky: bool = True,
    ) -> None:
        """Atomically update the active setpoint.

        Parameters
        ----------
        sticky:
            If True (the default for closed-loop commands) the encoded
            ``wire`` bytes are re-sent forever so the VESC watchdog stays
            happy. If False (e.g. a one-shot SetPosition request) the loop
            sends the message once and then falls back to ``Alive`` so as
            not to spam a position command that was already accepted.
        """
        with self._lock:
            self._mode = mode
            self._setpoint_value = value
            if sticky:
                self._setpoint_bytes = wire
                self._one_shot = b""
            else:
                self._setpoint_bytes = encode(Alive())
                self._one_shot = wire

    # --- public command API ----------------------------------------------

    def set_rpm(self, rpm: float) -> None:
        self._set_command(ControlMode.RPM, rpm, encode(SetRPM(int(rpm))))

    def set_current(self, amps: float) -> None:
        self._set_command(
            ControlMode.CURRENT, amps, encode(SetCurrent(float(amps)))
        )

    def set_brake_current(self, amps: float) -> None:
        # The VESC interprets a negative brake current as "no brake"; clamp
        # to non-negative for safety.
        amps = max(0.0, float(amps))
        self._set_command(
            ControlMode.BRAKE, amps, encode(SetCurrentBrake(amps))
        )

    def set_handbrake_current(self, amps: float) -> None:
        amps = max(0.0, float(amps))
        self._set_command(
            ControlMode.HANDBRAKE, amps, encode(SetHandbrake(amps))
        )

    def set_duty_cycle(self, duty: float) -> None:
        duty = max(-1.0, min(1.0, float(duty)))
        self._set_command(
            ControlMode.DUTY, duty, encode(SetDutyCycle(duty))
        )

    def set_position(self, degrees: float) -> None:
        deg = float(degrees) % 360.0
        # Position is a one-shot request; the VESC will hold the position
        # under its own PID once accepted.
        self._set_command(
            ControlMode.POSITION,
            deg,
            encode(SetPosition(deg)),
            sticky=False,
        )

    def full_brake(self) -> None:
        """Apply maximum brake current (effectively a hard stop)."""
        self.set_brake_current(self._max_brake_current_a)

    def release(self) -> None:
        """Stop driving the motor — it will coast."""
        with self._lock:
            self._mode = ControlMode.RELEASED
            self._setpoint_value = 0.0
            self._setpoint_bytes = encode(Alive())
            self._one_shot = b""

    # The full-brake current the GUI considers "max". The VESC panel writes
    # this attribute when the user changes the limit in the settings.
    _max_brake_current_a: float = 30.0

    def set_max_brake_current(self, amps: float) -> None:
        self._max_brake_current_a = max(0.0, float(amps))

    # ============================================================ I/O loop

    def _io_loop(self) -> None:
        assert self._ser is not None
        ser = self._ser
        next_tick = time.monotonic()

        # Drain whatever the VESC printed during connect.
        try:
            ser.reset_input_buffer()
        except serial.SerialException:
            pass

        while not self._stop_event.is_set():
            try:
                self._tick_once(ser)
            except serial.SerialException as exc:
                log.error("VESC serial error: %s", exc)
                self.error.emit(f"VESC serial error: {exc}")
                break
            except Exception as exc:  # noqa: BLE001
                log.exception("Unexpected VESC I/O error")
                self.error.emit(f"VESC I/O error: {exc}")
                # Keep going - a single malformed packet shouldn't kill us.

            # Steady-rate scheduling rather than sleep(N) drift.
            next_tick += self.poll_interval_s
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                self._stop_event.wait(sleep_for)
            else:
                # Fell behind; reset the reference to avoid burst-firing.
                next_tick = time.monotonic()

        # Signal disconnect if we exited because of an error rather than
        # an explicit close().
        if not self._stop_event.is_set():
            self.connection_changed.emit(False)

    def _tick_once(self, ser: serial.Serial) -> None:
        # 1) Push the active setpoint (or a one-shot, or just Alive).
        with self._lock:
            one_shot = self._one_shot
            sticky = self._setpoint_bytes
            if one_shot:
                self._one_shot = b""

        if one_shot:
            ser.write(one_shot)
        ser.write(sticky)

        # 2) Ask for telemetry and try to read the full response.
        ser.write(self._get_values_msg)
        ser.flush()

        deadline = time.monotonic() + self.response_timeout_s
        buf = bytearray()
        expected = self._get_values_expected_len

        while time.monotonic() < deadline and len(buf) < expected:
            chunk = ser.read(expected - len(buf))
            if not chunk:
                break
            buf.extend(chunk)

        # Anything left in the input buffer (e.g. an Alive echo or stale
        # bytes) should be flushed so the next iteration is in sync.
        try:
            extra = ser.in_waiting
            if extra:
                buf.extend(ser.read(extra))
        except serial.SerialException:
            pass

        if not buf:
            return

        msg, _consumed = decode(bytes(buf))
        if msg is None:
            return

        telem = VescTelemetry.from_pyvesc(msg)
        self.telemetry.emit(telem)
