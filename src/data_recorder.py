"""CSV recorder for live RPM, torque and throttle data.

The recorder subscribes to three independent sample streams in the app:

- VESC telemetry (``rpm``), arriving at the VESC poll rate.
- Load-cell torque (``torque_mnm`` in millinewton-metres), arriving at
  the Arduino sample rate.
- Throttle command (``throttle_pct``), arriving whenever the user moves
  the throttle from the GUI or with the keyboard.

Because the streams are asynchronous, each incoming sample is written as
its own CSV row. The ``source`` column says which value is *fresh* on
that row, while the other columns carry the most recent value seen so
far (blank until the first sample of that kind arrives). This keeps
every raw sample without trying to resample any stream.

Rows look like::

    timestamp,elapsed_s,source,rpm,torque_mnm,throttle_pct
    2026-06-03T01:28:11.412,0.000,rpm,1234.500,,
    2026-06-03T01:28:11.418,0.006,torque,1234.500,1214.000,
    2026-06-03T01:28:12.013,0.601,throttle,1234.500,1214.000,100.000
"""

from __future__ import annotations

import csv
import logging
import time
from datetime import datetime
from typing import Optional, TextIO

from PyQt6.QtCore import QObject, pyqtSignal

from .hardware.vesc_controller import VescTelemetry

log = logging.getLogger(__name__)


class DataRecorder(QObject):
    """Append-only CSV logger for RPM and torque samples.

    Signals
    -------
    recording_changed : bool
        ``True`` when a recording starts, ``False`` when it stops.
    error : str
        Emitted if the file cannot be opened or a write fails.
    """

    recording_changed = pyqtSignal(bool)
    error = pyqtSignal(str)

    _FIELDNAMES = [
        "timestamp",
        "elapsed_s",
        "source",
        "rpm",
        "torque_mnm",
        "throttle_pct",
    ]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._file: Optional[TextIO] = None
        self._writer: Optional["csv._writer"] = None  # type: ignore[name-defined]
        self._path: Optional[str] = None
        self._start_monotonic: float = 0.0
        self._row_count: int = 0
        self._latest_rpm: Optional[float] = None
        self._latest_torque: Optional[float] = None
        self._latest_throttle: Optional[float] = None

    # ============================================================ state

    @property
    def is_recording(self) -> bool:
        return self._file is not None

    @property
    def path(self) -> Optional[str]:
        return self._path

    @property
    def row_count(self) -> int:
        return self._row_count

    # ============================================================ lifecycle

    def start(self, path: str) -> bool:
        """Open ``path`` for writing and emit the CSV header.

        Returns ``True`` on success. Any existing recording is stopped
        first so the recorder only ever owns one open file.
        """
        if self.is_recording:
            self.stop()

        try:
            self._file = open(path, "w", newline="", encoding="utf-8")
        except OSError as exc:
            log.error("Could not open CSV '%s': %s", path, exc)
            self.error.emit(f"Could not open '{path}': {exc}")
            self._file = None
            return False

        self._writer = csv.writer(self._file)
        self._writer.writerow(self._FIELDNAMES)
        self._path = path
        self._start_monotonic = time.monotonic()
        self._row_count = 0
        self._latest_rpm = None
        self._latest_torque = None
        self._latest_throttle = None
        self.recording_changed.emit(True)
        log.info("Recording RPM/torque to %s", path)
        return True

    def stop(self) -> None:
        if self._file is None:
            return
        try:
            self._file.flush()
            self._file.close()
        except OSError:
            pass
        log.info("Stopped recording (%d rows) -> %s", self._row_count, self._path)
        self._file = None
        self._writer = None
        self.recording_changed.emit(False)

    # ============================================================ sample sinks

    def on_rpm(self, telem: VescTelemetry) -> None:
        self._latest_rpm = telem.rpm
        self._write_row("rpm")

    def on_torque(self, _t_monotonic: float, torque_mnm: float) -> None:
        self._latest_torque = torque_mnm
        self._write_row("torque")

    def on_throttle(self, throttle_pct: float) -> None:
        self._latest_throttle = float(throttle_pct)
        self._write_row("throttle")

    # ============================================================ internals

    def _write_row(self, source: str) -> None:
        if self._writer is None:
            return

        elapsed = time.monotonic() - self._start_monotonic
        ts = datetime.now().isoformat(timespec="milliseconds")
        rpm = "" if self._latest_rpm is None else f"{self._latest_rpm:.3f}"
        # ``torque_mnm`` is in millinewton-metres; .3f gives µN·m
        # resolution, which is well below HX711 noise.
        torque = "" if self._latest_torque is None else f"{self._latest_torque:.3f}"
        throttle = (
            "" if self._latest_throttle is None else f"{self._latest_throttle:.3f}"
        )

        try:
            self._writer.writerow(
                [ts, f"{elapsed:.3f}", source, rpm, torque, throttle]
            )
            self._row_count += 1
        except (OSError, ValueError) as exc:
            log.error("CSV write failed: %s", exc)
            self.error.emit(f"Recording write failed: {exc}")
            self.stop()
