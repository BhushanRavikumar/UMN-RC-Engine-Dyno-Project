"""Animated 2-D motor graphic.

The widget integrates the live RPM into a rotor angle and repaints itself
at a fixed 60 Hz. Visual cues:

- The rotor (with two permanent magnets) spins at the real motor's RPM.
- The stator's "energised" tooth glows red/blue depending on the sign of
  the current.
- The shaft key-mark makes the rotation direction obvious at a glance.
- A small text overlay echoes the current numerical RPM so the graphic
  works as a stand-alone status indicator.

The widget owns no model state of its own: feed it
:class:`~src.hardware.vesc_controller.VescTelemetry` snapshots and it
takes care of everything else.
"""

from __future__ import annotations

import math
import time
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from ..hardware.vesc_controller import VescTelemetry


class MotorGraphic(QWidget):
    """A QWidget that animates a stylised BLDC motor."""

    # Constants tuning the visual.
    _STATOR_POLES = 12
    _ROTOR_POLES = 2  # one N, one S magnet for visual clarity

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(220, 220)

        self._rpm: float = 0.0
        self._current_a: float = 0.0
        self._temp_c: float = 25.0
        self._duty: float = 0.0
        self._connected: bool = False

        # Rotor mechanical angle in degrees, integrated from RPM.
        self._angle_deg: float = 0.0
        self._last_anim_t: float = time.monotonic()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 FPS

    # =========================================================== public API

    def add_sample(self, telem: VescTelemetry) -> None:
        """Update the model state from a fresh telemetry snapshot."""
        self._rpm = telem.rpm
        self._current_a = telem.motor_current_a
        self._temp_c = telem.mosfet_temp_c
        self._duty = telem.duty
        self._connected = True

    def set_connected(self, connected: bool) -> None:
        self._connected = bool(connected)
        if not connected:
            self._rpm = 0.0
            self._current_a = 0.0
            self._duty = 0.0

    # ========================================================= animation

    def _tick(self) -> None:
        now = time.monotonic()
        dt = max(0.0, min(0.1, now - self._last_anim_t))
        self._last_anim_t = now
        # rpm -> deg/s is x6 (one revolution = 360 deg, 60 s/min)
        self._angle_deg = (self._angle_deg + self._rpm * 6.0 * dt) % 360.0
        self.update()

    # ========================================================= painting

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        size = min(rect.width(), rect.height())
        cx, cy = rect.center().x(), rect.center().y()

        r_outer = size * 0.46
        r_stator_in = size * 0.34
        r_rotor_out = size * 0.30
        r_shaft = size * 0.06

        self._draw_background(painter, cx, cy, r_outer)
        self._draw_stator(painter, cx, cy, r_outer, r_stator_in)
        self._draw_air_gap(painter, cx, cy, r_stator_in, r_rotor_out)
        self._draw_rotor(painter, cx, cy, r_rotor_out, r_shaft)
        self._draw_shaft(painter, cx, cy, r_shaft)
        self._draw_overlay(painter, rect)

    # ------------------------------------------------------------------ bg

    def _draw_background(
        self, p: QPainter, cx: float, cy: float, r_outer: float
    ) -> None:
        # Soft halo whose intensity tracks |current|.
        intensity = min(1.0, abs(self._current_a) / 20.0)
        if intensity > 0.01:
            halo = QRadialGradient(QPointF(cx, cy), r_outer * 1.8)
            base = QColor("#ff5252") if self._current_a >= 0 else QColor("#54a0ff")
            base.setAlphaF(0.40 * intensity)
            halo.setColorAt(0.0, base)
            base_outer = QColor(base)
            base_outer.setAlphaF(0.0)
            halo.setColorAt(1.0, base_outer)
            p.setBrush(QBrush(halo))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(
                QPointF(cx, cy), r_outer * 1.8, r_outer * 1.8
            )

    # --------------------------------------------------------------- stator

    def _draw_stator(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r_outer: float,
        r_inner: float,
    ) -> None:
        # Iron yoke.
        p.setPen(QPen(QColor("#2c3e50"), 2))
        p.setBrush(QBrush(QColor("#34495e")))
        p.drawEllipse(QPointF(cx, cy), r_outer, r_outer)

        # Stator teeth: short trapezoids pointing inward.
        tooth_count = self._STATOR_POLES
        # Identify which tooth is currently "energised" - rotate the
        # active tooth so it appears to be chasing the rotor.
        if self._connected and abs(self._duty) > 0.01:
            active_tooth = int(self._angle_deg / 360.0 * tooth_count) % tooth_count
        else:
            active_tooth = -1

        for i in range(tooth_count):
            theta = (i / tooth_count) * 2 * math.pi
            self._draw_tooth(
                p, cx, cy, r_outer * 0.96, r_inner, theta,
                is_active=(i == active_tooth),
            )

    def _draw_tooth(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r_outer: float,
        r_inner: float,
        theta: float,
        is_active: bool,
    ) -> None:
        # Half-angular width of one tooth (in radians).
        half = (math.pi / self._STATOR_POLES) * 0.55

        # Compute the four corner points of the trapezoid.
        outer1 = QPointF(cx + r_outer * math.cos(theta - half),
                         cy + r_outer * math.sin(theta - half))
        outer2 = QPointF(cx + r_outer * math.cos(theta + half),
                         cy + r_outer * math.sin(theta + half))
        inner1 = QPointF(cx + r_inner * math.cos(theta - half * 0.5),
                         cy + r_inner * math.sin(theta - half * 0.5))
        inner2 = QPointF(cx + r_inner * math.cos(theta + half * 0.5),
                         cy + r_inner * math.sin(theta + half * 0.5))

        if is_active:
            energised_color = (
                QColor("#ff5252") if self._current_a >= 0 else QColor("#54a0ff")
            )
            p.setBrush(QBrush(energised_color))
            p.setPen(QPen(energised_color.darker(150), 1.2))
        else:
            p.setBrush(QBrush(QColor("#7f8c8d")))
            p.setPen(QPen(QColor("#2c3e50"), 1.2))

        p.drawPolygon(outer1, outer2, inner2, inner1)

    def _draw_air_gap(
        self, p: QPainter, cx: float, cy: float, r_in: float, r_rotor: float
    ) -> None:
        # Just a subtle dark ring for visual separation.
        p.setBrush(QBrush(QColor("#0f1419")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r_in, r_in)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # ---------------------------------------------------------------- rotor

    def _draw_rotor(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        r_out: float,
        r_shaft: float,
    ) -> None:
        # The rotor body uses a conical gradient so the rotation is
        # immediately visible even if you cannot see the key-mark.
        grad = QConicalGradient(QPointF(cx, cy), -self._angle_deg)
        grad.setColorAt(0.00, QColor("#ecf0f1"))
        grad.setColorAt(0.25, QColor("#bdc3c7"))
        grad.setColorAt(0.50, QColor("#ecf0f1"))
        grad.setColorAt(0.75, QColor("#bdc3c7"))
        grad.setColorAt(1.00, QColor("#ecf0f1"))

        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor("#1c2833"), 2))
        p.drawEllipse(QPointF(cx, cy), r_out, r_out)

        # Two opposing magnet sectors (N/S).
        sector_half_deg = 50.0
        rect = QRectF(cx - r_out, cy - r_out, 2 * r_out, 2 * r_out)
        for sign, color in ((+1, QColor("#e74c3c")), (-1, QColor("#3498db"))):
            start_angle = (self._angle_deg + (0 if sign > 0 else 180)) - sector_half_deg
            p.setBrush(QBrush(color))
            p.setPen(QPen(color.darker(150), 1))
            # drawPie wants Qt's 16ths-of-a-degree convention.
            p.drawPie(rect, int(start_angle * 16), int(sector_half_deg * 2 * 16))

        # Key-mark line so direction is unmistakable.
        rad = math.radians(self._angle_deg)
        p.setPen(QPen(QColor("#2c3e50"), 3))
        p.drawLine(
            QPointF(cx, cy),
            QPointF(cx + r_out * 0.85 * math.cos(rad),
                    cy + r_out * 0.85 * math.sin(rad)),
        )

    def _draw_shaft(
        self, p: QPainter, cx: float, cy: float, r_shaft: float
    ) -> None:
        p.setBrush(QBrush(QColor("#1c2833")))
        p.setPen(QPen(QColor("#0b0e11"), 1))
        p.drawEllipse(QPointF(cx, cy), r_shaft, r_shaft)

    # -------------------------------------------------------------- overlay

    def _draw_overlay(self, p: QPainter, rect) -> None:
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        p.setFont(font)
        p.setPen(QPen(QColor("#ecf0f1")))

        lines = [
            f"RPM:    {self._rpm:+8.0f}",
            f"I:      {self._current_a:+6.2f} A",
            f"Duty:   {self._duty * 100:+5.1f} %",
            f"T_fet:  {self._temp_c:5.1f} C",
        ]
        if not self._connected:
            lines.append("[disconnected]")

        x = rect.left() + 8
        y = rect.bottom() - 8 - 14 * (len(lines) - 1)
        for line in lines:
            p.drawText(x, y, line)
            y += 14
