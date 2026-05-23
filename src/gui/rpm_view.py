"""Live RPM view: composite of a big numeric counter + scrolling plot.

The widget consumes :class:`~src.hardware.vesc_controller.VescTelemetry`
snapshots so the caller just wires the VESC controller's ``telemetry``
signal to :meth:`add_sample`.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..hardware.vesc_controller import VescTelemetry
from .plots import LiveCounter, ScrollingPlot


class RpmView(QWidget):
    """Big RPM counter on top, scrolling RPM-vs-time plot below."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._counter = LiveCounter(
            title="RPM",
            unit="rpm",
            color="#1f3a93",
            value_fmt="+9.1f",
            stat_fmt="+.1f",
        )
        self._plot = ScrollingPlot(
            y_label="RPM",
            pen_color="#2ed573",
            name="RPM",
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._counter)
        layout.addWidget(self._plot, stretch=1)

    def add_sample(self, telem: VescTelemetry) -> None:
        self._counter.add_value(telem.rpm)
        self._plot.add_point(telem.t_monotonic, telem.rpm)

    def reset(self) -> None:
        self._counter.reset()
        self._plot.reset()
