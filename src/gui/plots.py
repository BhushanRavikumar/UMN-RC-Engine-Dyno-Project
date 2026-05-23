"""Reusable live-data widgets.

Two pieces are exported:

- :class:`LiveCounter` — a giant numeric read-out with a trailing-window
  min / avg / max stats line.
- :class:`ScrollingPlot` — a high-refresh-rate scrolling pyqtgraph plot
  backed by a numpy ring buffer, decoupled from the sample arrival rate
  by a fixed redraw timer.

Both widgets are intentionally telemetry-agnostic: feed them ``(value)``
or ``(timestamp, value)`` tuples and they handle the rest. This lets us
build the RPM view, the torque view, and any future scalar telemetry
view from the same plumbing.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class LiveCounter(QWidget):
    """Large numeric read-out for a single scalar signal."""

    def __init__(
        self,
        title: str,
        unit: str,
        color: str = "#1f3a93",
        value_fmt: str = "+9.1f",
        stat_fmt: str = "+.1f",
        window_samples: int = 200,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        self._value_fmt = value_fmt
        self._stat_fmt = stat_fmt

        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setStyleSheet("color: gray; font-size: 11pt;")

        self._big = QLabel("0")
        big_font = QFont("Consolas", 60, QFont.Weight.Bold)
        big_font.setStyleHint(QFont.StyleHint.Monospace)
        self._big.setFont(big_font)
        self._big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._big.setStyleSheet(f"color: {color};")

        self._unit = QLabel(unit)
        self._unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unit.setStyleSheet("font-size: 13pt; color: gray;")

        self._stats = QLabel("min: —    avg: —    max: —")
        self._stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stats.setStyleSheet("color: #555;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(self._title)
        layout.addWidget(self._big)
        layout.addWidget(self._unit)
        layout.addWidget(self._stats)

        self._window_max = int(window_samples)
        self._window: list[float] = []

    def add_value(self, value: float) -> None:
        self._big.setText(f"{value:{self._value_fmt}}")

        self._window.append(float(value))
        if len(self._window) > self._window_max:
            del self._window[: len(self._window) - self._window_max]

        arr = np.asarray(self._window)
        self._stats.setText(
            f"min: {arr.min():{self._stat_fmt}}    "
            f"avg: {arr.mean():{self._stat_fmt}}    "
            f"max: {arr.max():{self._stat_fmt}}"
        )

    def reset(self) -> None:
        self._window.clear()
        self._big.setText("0")
        self._stats.setText("min: —    avg: —    max: —")


class ScrollingPlot(pg.PlotWidget):
    """Scrolling time-series plot backed by a numpy ring buffer.

    The plot only redraws on a fixed timer (default 60 Hz) rather than on
    every sample, which keeps the GUI smooth even when samples arrive
    faster than the display can refresh.
    """

    def __init__(
        self,
        y_label: str,
        y_units: str = "",
        pen_color: str = "#2ed573",
        window_seconds: float = 10.0,
        max_samples: int = 5_000,
        refresh_hz: float = 60.0,
        name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        pg.setConfigOptions(antialias=True)
        super().__init__(parent=parent, background="#101418")

        self.setLabel("left", y_label, units=y_units or None)
        self.setLabel("bottom", "Time", units="s")
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.addLegend()

        self._curve = self.plot(
            pen=pg.mkPen(pen_color, width=2),
            name=name or y_label,
        )
        # Faint zero line — useful for bidirectional signals (RPM, torque).
        self.addLine(y=0, pen=pg.mkPen("#888", width=1, style=Qt.PenStyle.DashLine))

        self._window_seconds = float(window_seconds)
        self._capacity = int(max_samples)
        self._t = np.zeros(self._capacity, dtype=np.float64)
        self._y = np.zeros(self._capacity, dtype=np.float64)
        self._count = 0
        self._head = 0  # next write position
        self._t0: Optional[float] = None
        self._dirty = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._maybe_redraw)
        self._timer.start(max(1, int(1000.0 / refresh_hz)))

    def add_point(self, t_monotonic: float, value: float) -> None:
        if self._t0 is None:
            self._t0 = float(t_monotonic)

        self._t[self._head] = float(t_monotonic) - self._t0
        self._y[self._head] = float(value)
        self._head = (self._head + 1) % self._capacity
        self._count = min(self._count + 1, self._capacity)
        self._dirty = True

    def reset(self) -> None:
        self._count = 0
        self._head = 0
        self._t0 = None
        self._curve.setData([], [])

    def _maybe_redraw(self) -> None:
        if not self._dirty or self._count == 0:
            return
        self._dirty = False

        if self._count < self._capacity:
            t = self._t[: self._count]
            y = self._y[: self._count]
        else:
            order = np.concatenate(
                (
                    np.arange(self._head, self._capacity),
                    np.arange(0, self._head),
                )
            )
            t = self._t[order]
            y = self._y[order]

        t_max = t[-1]
        t_min = max(0.0, t_max - self._window_seconds)
        mask = t >= t_min
        self._curve.setData(t[mask], y[mask])
        self.setXRange(t_min, t_max + 1e-3, padding=0)
