"""Live torque view: big counter + scrolling plot.

Mirrors :class:`~src.gui.rpm_view.RpmView` but consumes
``(t, torque_mnm)`` tuples emitted by
:class:`~src.gui.loadcell_panel.LoadCellPanel`. Torque is in mN·m.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from .plots import LiveCounter, ScrollingPlot


class TorqueView(QWidget):
    """Big torque counter on top, scrolling torque-vs-time plot below."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._counter = LiveCounter(
            title="Torque",
            unit="mN·m",
            color="#2566c8",
            value_fmt="+8.1f",
            stat_fmt="+.1f",
        )
        self._plot = ScrollingPlot(
            y_label="Torque",
            y_units="mN·m",
            pen_color="#ffa502",
            name="Torque",
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._counter)
        layout.addWidget(self._plot, stretch=1)

    def add_sample(self, t_monotonic: float, torque_mnm: float) -> None:
        self._counter.add_value(torque_mnm)
        self._plot.add_point(t_monotonic, torque_mnm)

    def reset(self) -> None:
        self._counter.reset()
        self._plot.reset()
