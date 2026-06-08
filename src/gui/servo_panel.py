"""GUI panel for the throttle servo.

The panel runs in one of two mutually exclusive modes:

- **Calibration** — the user nudges the *raw* servo angle (0–180 °) with
  arrow keys or a spin box, then clicks *Save as 0 % throttle* or
  *Save as 100 % throttle* to record the current angle as one of the
  calibration end-points. Both end-points are persisted in
  ``AppConfig``. In this mode the four arrow keys nudge the angle by
  ``servo_calib_step_deg`` per press (``Shift`` makes the step 5×).

- **Throttle** — once both end-points are configured, the user types a
  percentage (0–100 %) or uses the keyboard. The panel linearly
  interpolates between the two calibrated angles and sends the resulting
  command to the Arduino. Keyboard behaviour in this mode is intentionally
  a **dead-man** pattern:

    - Pressing ``↑`` commands 100 % throttle for as long as it is held.
    - Releasing ``↑`` (or losing focus, or switching modes) snaps the
      throttle back to 0 % immediately.
    - Pressing ``↓`` (or ``Space``, or the red button) snaps the throttle
      to 0 % instantly.

Every commanded throttle value is broadcast on ``throttle_changed`` so
the :class:`~src.data_recorder.DataRecorder` can log it alongside the
RPM and torque streams.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..hardware.loadcell_serial import LoadCellSerial

log = logging.getLogger(__name__)


class _Mode(Enum):
    CALIBRATION = "calibration"
    THROTTLE = "throttle"


class ServoPanel(QWidget):
    """Calibration + manual / keyboard throttle control for the servo."""

    status_message = pyqtSignal(str)
    # Emitted every time a new throttle percentage is commanded (manual
    # spin-box entry, arrow-key dead-man press/release, mode toggle,
    # connection state change, etc.). The data recorder listens to this
    # signal so the CSV captures every throttle event.
    throttle_changed = pyqtSignal(float)

    def __init__(
        self,
        cfg: AppConfig,
        loadcell: LoadCellSerial,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._lc = loadcell

        # Allow the widget to receive key events when the user clicks on it.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # ---------- mode selector ----------
        self._calib_radio = QRadioButton("Calibration")
        self._throttle_radio = QRadioButton("Throttle")
        self._calib_radio.setChecked(True)
        self._calib_radio.toggled.connect(self._on_mode_toggled)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        mode_row.addWidget(self._calib_radio)
        mode_row.addWidget(self._throttle_radio)
        mode_row.addStretch(1)

        # ---------- big read-out ----------
        self._readout = QLabel("—")
        big = QFont("Consolas", 18, QFont.Weight.Bold)
        big.setStyleHint(QFont.StyleHint.Monospace)
        self._readout.setFont(big)
        self._readout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._readout.setStyleSheet(
            "background:#222; color:#f1c40f; padding:4px; border-radius:4px;"
        )

        # ---------- calibration controls ----------
        self._angle_spin = QDoubleSpinBox()
        self._angle_spin.setRange(0.0, 180.0)
        self._angle_spin.setDecimals(1)
        self._angle_spin.setSingleStep(1.0)
        self._angle_spin.setSuffix(" °")
        self._angle_spin.setValue(90.0)
        self._angle_spin.valueChanged.connect(self._on_angle_changed)

        self._set_zero_btn = QPushButton("Save as 0 % throttle")
        self._set_zero_btn.clicked.connect(self._save_zero)
        self._set_full_btn = QPushButton("Save as 100 % throttle")
        self._set_full_btn.clicked.connect(self._save_full)

        calib_btns = QHBoxLayout()
        calib_btns.addWidget(self._set_zero_btn)
        calib_btns.addWidget(self._set_full_btn)

        self._calib_label = QLabel()
        self._calib_label.setStyleSheet("color: gray;")
        self._refresh_calib_label()

        calib_form = QFormLayout()
        calib_form.addRow("Servo angle:", self._angle_spin)

        self._calib_box = QGroupBox("Calibration")
        calib_layout = QVBoxLayout(self._calib_box)
        calib_layout.addLayout(calib_form)
        calib_layout.addLayout(calib_btns)
        calib_layout.addWidget(self._calib_label)

        # ---------- throttle controls ----------
        self._throttle_spin = QDoubleSpinBox()
        self._throttle_spin.setRange(0.0, 100.0)
        self._throttle_spin.setDecimals(1)
        self._throttle_spin.setSingleStep(1.0)
        self._throttle_spin.setSuffix(" %")
        self._throttle_spin.setValue(0.0)
        self._throttle_spin.valueChanged.connect(self._on_throttle_changed)

        self._zero_btn = QPushButton("Throttle to 0 %  (Space)")
        self._zero_btn.setStyleSheet(
            "background:#c0392b; color:white; font-weight:bold; padding:6px;"
        )
        self._zero_btn.clicked.connect(self.zero_throttle)

        throttle_form = QFormLayout()
        throttle_form.addRow("Throttle:", self._throttle_spin)

        self._throttle_box = QGroupBox("Throttle")
        throttle_layout = QVBoxLayout(self._throttle_box)
        throttle_layout.addLayout(throttle_form)
        throttle_layout.addWidget(self._zero_btn)

        # ---------- arrow-key hint ----------
        self._hint = QLabel(
            "Click panel, then ↑/→ +  ↓/← -  Shift=5×  Space=0 %"
        )
        self._hint.setStyleSheet(
            "background:#222; color:#ddd; padding:3px 6px; border-radius:3px;"
        )

        # ---------- assemble ----------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(mode_row)
        layout.addWidget(self._readout)
        layout.addWidget(self._calib_box)
        layout.addWidget(self._throttle_box)
        layout.addWidget(self._hint)
        layout.addStretch(1)

        # Initial state: calibration mode visible, throttle hidden.
        self._mode = _Mode.CALIBRATION
        self._current_angle: float = float(self._angle_spin.value())
        self._current_throttle_pct: float = 0.0
        # Tracks whether the user is currently holding the ↑ key in
        # throttle mode. Used so a focus loss / mode switch can release
        # the dead-man hold even if the key release never reaches us.
        self._up_held: bool = False
        self._refresh_visibility()
        self._refresh_readout()

        # Wire up servo acknowledgements from the Arduino so the read-out
        # always reflects the angle the firmware actually applied.
        self._lc.servo_angle.connect(self._on_servo_ack)
        self._lc.connection_changed.connect(self._on_connection_changed)

    # ============================================================ helpers

    def _refresh_calib_label(self) -> None:
        self._calib_label.setText(
            f"0 % throttle = {self._cfg.servo_min_angle_deg:.1f} °     "
            f"100 % throttle = {self._cfg.servo_max_angle_deg:.1f} °"
        )

    def _refresh_visibility(self) -> None:
        calib = self._mode is _Mode.CALIBRATION
        self._calib_box.setVisible(calib)
        self._throttle_box.setVisible(not calib)
        # Keep the hint label in sync with the active key bindings.
        if calib:
            self._hint.setText(
                "Click panel · ↑/→ + · ↓/← - · Shift = 5×"
            )
        else:
            self._hint.setText(
                "Click panel · Hold ↑ = 100 % (auto-release) · ↓ or Space = 0 %"
            )

    def _refresh_readout(self) -> None:
        if self._mode is _Mode.CALIBRATION:
            self._readout.setText(f"{self._current_angle:5.1f} °")
        else:
            self._readout.setText(
                f"{self._current_throttle_pct:5.1f} %   "
                f"({self._throttle_to_angle(self._current_throttle_pct):.1f} °)"
            )

    def _throttle_to_angle(self, pct: float) -> float:
        """Linearly interpolate between the two calibrated angles."""
        pct = max(0.0, min(100.0, float(pct)))
        a0 = float(self._cfg.servo_min_angle_deg)
        a1 = float(self._cfg.servo_max_angle_deg)
        return a0 + (a1 - a0) * (pct / 100.0)

    def _send_angle(self, angle_deg: float) -> None:
        angle_deg = max(0.0, min(180.0, float(angle_deg)))
        self._current_angle = angle_deg
        ok = self._lc.set_servo_angle(angle_deg)
        if not ok and self._lc.is_open is False:
            self.status_message.emit("Servo: Arduino not connected")
        self._refresh_readout()

    # ============================================================ slots

    def _on_mode_toggled(self, _checked: bool) -> None:
        new_mode = (
            _Mode.CALIBRATION if self._calib_radio.isChecked() else _Mode.THROTTLE
        )

        # If we're leaving Throttle mode for Calibration, drop any active
        # dead-man hold and force the throttle to 0 % *before* the mode
        # flips so the spin-box / readout update still happens cleanly.
        # This also prevents a surprise where the engine resumes at the
        # last commanded percentage when the user later returns to
        # throttle mode.
        if self._mode is _Mode.THROTTLE and new_mode is _Mode.CALIBRATION:
            self._up_held = False
            self.zero_throttle()

        self._mode = new_mode
        self._refresh_visibility()
        # When entering throttle mode, immediately drive the servo to the
        # currently-selected throttle so the firmware angle matches what
        # the read-out shows.
        if self._mode is _Mode.THROTTLE:
            self._send_throttle(self._throttle_spin.value())
        else:
            # Re-sync the calibration spin box with the last commanded angle.
            self._angle_spin.blockSignals(True)
            self._angle_spin.setValue(self._current_angle)
            self._angle_spin.blockSignals(False)
        self._refresh_readout()

    def _on_angle_changed(self, value: float) -> None:
        if self._mode is _Mode.CALIBRATION:
            self._send_angle(value)

    def _on_throttle_changed(self, value: float) -> None:
        if self._mode is _Mode.THROTTLE:
            self._send_throttle(value)

    def _send_throttle(self, pct: float) -> None:
        pct = max(0.0, min(100.0, float(pct)))
        self._current_throttle_pct = pct
        self._send_angle(self._throttle_to_angle(pct))
        # Broadcast for the data recorder and any other listeners.
        self.throttle_changed.emit(pct)

    def _save_zero(self) -> None:
        self._cfg.servo_min_angle_deg = float(self._current_angle)
        self._refresh_calib_label()
        self.status_message.emit(
            f"Saved {self._current_angle:.1f} ° as 0 % throttle"
        )

    def _save_full(self) -> None:
        self._cfg.servo_max_angle_deg = float(self._current_angle)
        self._refresh_calib_label()
        self.status_message.emit(
            f"Saved {self._current_angle:.1f} ° as 100 % throttle"
        )

    def zero_throttle(self) -> None:
        """Command 0 % throttle (used on Space, disconnect and shutdown)."""
        if self._mode is _Mode.THROTTLE:
            self._throttle_spin.blockSignals(True)
            self._throttle_spin.setValue(0.0)
            self._throttle_spin.blockSignals(False)
        self._send_throttle(0.0)
        self.status_message.emit("Throttle to 0 %")

    def _on_servo_ack(self, angle: int) -> None:
        # The firmware confirmed an angle; update our cached value so
        # the read-out is exact even if the Arduino rounded or clamped.
        self._current_angle = float(angle)
        # Don't fight the user's spin-box editing; only update the
        # calibration spin box when we're actually showing it.
        if self._mode is _Mode.CALIBRATION:
            self._angle_spin.blockSignals(True)
            self._angle_spin.setValue(self._current_angle)
            self._angle_spin.blockSignals(False)
        self._refresh_readout()

    def _on_connection_changed(self, connected: bool) -> None:
        if not connected:
            # Don't try to send anything to a closed port; just reset our
            # local throttle to 0 % so the next connect starts safe.
            self._current_throttle_pct = 0.0
            self._throttle_spin.blockSignals(True)
            self._throttle_spin.setValue(0.0)
            self._throttle_spin.blockSignals(False)
            self._refresh_readout()
            return

        # Sync the firmware to whatever the panel is currently showing
        # so the live servo position matches the on-screen value the
        # moment the link comes up.
        if self._mode is _Mode.CALIBRATION:
            self._send_angle(self._angle_spin.value())
        else:
            self._send_throttle(self._throttle_spin.value())

    # ====================================================== arrow keys

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Auto-repeat events fire while a key is held; for both the
        # nudge-style calibration and the dead-man throttle hold we only
        # want to act once on the *initial* press.
        if event.isAutoRepeat():
            event.accept()
            return

        key = event.key()

        if key == Qt.Key.Key_Space:
            self.zero_throttle()
            event.accept()
            return

        if self._mode is _Mode.CALIBRATION:
            self._handle_calibration_key(event)
            return

        # ---- throttle mode: dead-man hold ----
        if key == Qt.Key.Key_Up:
            self._up_held = True
            self._throttle_spin.blockSignals(True)
            self._throttle_spin.setValue(100.0)
            self._throttle_spin.blockSignals(False)
            self._send_throttle(100.0)
            self.status_message.emit("Throttle: 100 % (hold ↑)")
            event.accept()
            return

        if key == Qt.Key.Key_Down:
            self.zero_throttle()
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            event.accept()
            return

        # The dead-man hold: when the user lets go of ↑ in throttle mode,
        # immediately drop the throttle back to 0 %.
        if (
            self._mode is _Mode.THROTTLE
            and event.key() == Qt.Key.Key_Up
            and self._up_held
        ):
            self._up_held = False
            self.zero_throttle()
            self.status_message.emit("Throttle: 0 % (released ↑)")
            event.accept()
            return

        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        # If the user is holding ↑ and focus moves away (alt-tab, clicking
        # another widget, switching modes via the mouse) the key-release
        # may never reach us. Force the throttle to 0 % as a safety so
        # the engine never gets "stuck" at part throttle.
        if self._up_held:
            self._up_held = False
            self.zero_throttle()
            self.status_message.emit("Throttle: 0 % (focus lost)")
        super().focusOutEvent(event)

    def _handle_calibration_key(self, event: QKeyEvent) -> None:
        """Original nudge-style arrow-key handling for calibration mode."""
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        direction = 0
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Right):
            direction = +1
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Left):
            direction = -1

        if direction == 0:
            super().keyPressEvent(event)
            return

        step = float(self._cfg.servo_calib_step_deg) * (5.0 if shift else 1.0)
        new_angle = self._current_angle + direction * step
        new_angle = max(0.0, min(180.0, new_angle))
        # Updating the spin box drives the angle via _on_angle_changed.
        self._angle_spin.setValue(new_angle)
        self.status_message.emit(f"Servo angle: {new_angle:.1f} °")
        event.accept()
