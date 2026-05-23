"""Serial interface to the dual-HX711 Arduino sketch.

The Arduino streams lines of the form ``LC,<raw1>,<raw2>``. This module
parses those lines in a background thread and emits a Qt signal on every
fresh sample so that the GUI can update without blocking on serial I/O.

Calibration (tare / counts-per-Newton) is applied here so that downstream
consumers only see physical units (Newtons).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import serial
from PyQt6.QtCore import QObject, pyqtSignal

from ..config import LoadCellCalibration

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadCellSample:
    """A single synchronised reading from both load cells."""

    raw1: int
    raw2: int
    force1_n: float
    force2_n: float
    t_monotonic: float


class LoadCellSerial(QObject):
    """Background reader for the dual-HX711 Arduino.

    Signals
    -------
    sample : LoadCellSample
        Emitted every time a fresh ``LC,...`` line is parsed.
    connection_changed : bool
        Emitted with ``True`` when the port opens, ``False`` when it closes
        (either explicitly or after a read error).
    error : str
        Emitted on serial I/O failures so the GUI can surface them.
    """

    sample = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(
        self,
        cal1: LoadCellCalibration,
        cal2: LoadCellCalibration,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._cal1 = cal1
        self._cal2 = cal2
        self._ser: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Cache the most recent raw values for calibration helpers.
        self._lock = threading.Lock()
        self._last_raw1: Optional[int] = None
        self._last_raw2: Optional[int] = None

    # ------------------------------------------------------------------ API

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def set_calibration(
        self,
        cal1: LoadCellCalibration,
        cal2: LoadCellCalibration,
    ) -> None:
        """Replace the in-memory calibration objects atomically."""
        with self._lock:
            self._cal1 = cal1
            self._cal2 = cal2

    def latest_raw(self) -> tuple[Optional[int], Optional[int]]:
        with self._lock:
            return self._last_raw1, self._last_raw2

    def open(self, port: str, baud: int = 115_200) -> None:
        if self.is_open:
            self.close()

        try:
            self._ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
        except serial.SerialException as exc:
            self._ser = None
            log.error("Could not open Arduino on %s: %s", port, exc)
            self.error.emit(f"Arduino open failed: {exc}")
            return

        # Give the bootloader a moment so the first reads are not garbage.
        time.sleep(2.0)
        self._ser.reset_input_buffer()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop, name="LoadCellSerial", daemon=True
        )
        self._thread.start()
        self.connection_changed.emit(True)
        log.info("Arduino opened on %s @ %d", port, baud)

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

        if self._ser is not None:
            try:
                self._ser.close()
            except serial.SerialException:
                pass
            self._ser = None

        self.connection_changed.emit(False)
        log.info("Arduino closed")

    # ---------------------------------------------------------------- thread

    def _read_loop(self) -> None:
        assert self._ser is not None
        ser = self._ser

        while not self._stop_event.is_set():
            try:
                raw = ser.readline()
            except serial.SerialException as exc:
                log.error("Arduino read error: %s", exc)
                self.error.emit(f"Arduino read error: {exc}")
                break

            if not raw:
                continue

            try:
                line = raw.decode("ascii", errors="ignore").strip()
            except UnicodeDecodeError:
                continue

            if not line or line.startswith("#"):
                continue

            parsed = self._parse_line(line)
            if parsed is None:
                continue

            raw1, raw2 = parsed
            with self._lock:
                self._last_raw1 = raw1
                self._last_raw2 = raw2
                cal1 = self._cal1
                cal2 = self._cal2

            sample = LoadCellSample(
                raw1=raw1,
                raw2=raw2,
                force1_n=_apply_cal(raw1, cal1),
                force2_n=_apply_cal(raw2, cal2),
                t_monotonic=time.monotonic(),
            )
            self.sample.emit(sample)

        # Make sure listeners learn about an abrupt disconnect.
        if not self._stop_event.is_set():
            self.connection_changed.emit(False)

    @staticmethod
    def _parse_line(line: str) -> Optional[tuple[int, int]]:
        # Expected format: "LC,<raw1>,<raw2>"
        if not line.startswith("LC,"):
            return None
        parts = line.split(",")
        if len(parts) != 3:
            return None
        try:
            return int(parts[1]), int(parts[2])
        except ValueError:
            return None


def _apply_cal(raw: int, cal: LoadCellCalibration) -> float:
    """Convert a raw HX711 count to Newtons using a tare + slope model."""
    slope = cal.counts_per_newton if cal.counts_per_newton != 0 else 1.0
    return (raw - cal.tare_offset) / slope
