"""GUI panel for driving the VESC.

Layout:

- A grid of telemetry read-outs (voltage, currents, duty, temps).
- A mode selector and a single setpoint spin box whose meaning depends on
  the mode (RPM → integer RPM, Current → Amps, Brake → Amps, etc.).
- Action buttons: ``Apply``, ``FULL BRAKE`` (Space), ``RELEASE`` (Esc).
- Live "arrow-key" hint label.

When the panel has keyboard focus, the arrow keys send relative *current*
commands (so the user can immediately feel the motor respond). Releasing
the arrow key falls back to ``set_current(0)`` so the motor coasts —
nothing keeps spinning by accident if the user tabs away.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..hardware.vesc_controller import ControlMode, VescController, VescTelemetry

log = logging.getLogger(__name__)


_MODE_ORDER = [
    (ControlMode.RPM,       "RPM"),
    (ControlMode.CURRENT,   "Current (A)"),
    (ControlMode.BRAKE,     "Brake current (A)"),
    (ControlMode.HANDBRAKE, "Handbrake current (A)"),
    (ControlMode.DUTY,      "Duty cycle (-1..1)"),
    (ControlMode.POSITION,  "Position (deg)"),
]


class _Readout(QFrame):
    """One bordered cell: label + big value."""

    def __init__(self, name: str, unit: str, color: str = "#ecf0f1") -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._name_label = QLabel(name)
        self._name_label.setStyleSheet("color: gray;")
        self._value_label = QLabel("—")
        big_font = QFont("Consolas", 18, QFont.Weight.Bold)
        big_font.setStyleHint(QFont.StyleHint.Monospace)
        self._value_label.setFont(big_font)
        self._value_label.setStyleSheet(f"color: {color};")
        self._unit_label = QLabel(unit)
        self._unit_label.setStyleSheet("color: gray;")

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 4, 8, 4)
        v.addWidget(self._name_label)
        v.addWidget(self._value_label)
        v.addWidget(self._unit_label)

    def set_value(self, text: str) -> None:
        self._value_label.setText(text)


class VescPanel(QWidget):
    """Telemetry display + setpoint controls + arrow-key driving."""

    status_message = pyqtSignal(str)

    def __init__(
        self,
        cfg: AppConfig,
        controller: VescController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._ctl = controller
        # Tell the controller what counts as "full brake".
        self._ctl.set_max_brake_current(cfg.max_brake_current_a)

        # Need focus for the arrow keys to be delivered to this widget.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # ---------- telemetry read-outs ----------
        self._ro_voltage   = _Readout("Battery voltage", "V")
        self._ro_current   = _Readout("Motor current",   "A", color="#ff7675")
        self._ro_in_current = _Readout("Input current",  "A")
        self._ro_duty      = _Readout("Duty cycle",      "%", color="#fdcb6e")
        self._ro_fet_temp  = _Readout("MOSFET temp",     "°C")
        self._ro_motor_temp = _Readout("Motor temp",     "°C")
        self._ro_ah        = _Readout("Charge used",     "Ah")
        self._ro_wh        = _Readout("Energy used",     "Wh")

        readouts = QGridLayout()
        readouts.addWidget(self._ro_voltage,    0, 0)
        readouts.addWidget(self._ro_current,    0, 1)
        readouts.addWidget(self._ro_in_current, 0, 2)
        readouts.addWidget(self._ro_duty,       0, 3)
        readouts.addWidget(self._ro_fet_temp,   1, 0)
        readouts.addWidget(self._ro_motor_temp, 1, 1)
        readouts.addWidget(self._ro_ah,         1, 2)
        readouts.addWidget(self._ro_wh,         1, 3)

        readouts_box = QGroupBox("Telemetry")
        readouts_box.setLayout(readouts)

        # ---------- control row ----------
        self._mode_combo = QComboBox()
        for _mode, label in _MODE_ORDER:
            self._mode_combo.addItem(label)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._setpoint_spin = QDoubleSpinBox()
        self._setpoint_spin.setDecimals(3)
        self._setpoint_spin.setRange(-cfg.max_rpm, cfg.max_rpm)
        self._setpoint_spin.setSingleStep(50.0)
        self._setpoint_spin.setValue(0.0)

        self._apply_btn = QPushButton("Apply setpoint")
        self._apply_btn.clicked.connect(self._on_apply)

        ctl_form = QFormLayout()
        ctl_form.addRow("Mode:", self._mode_combo)
        ctl_form.addRow("Setpoint:", self._setpoint_spin)
        ctl_form.addRow("", self._apply_btn)

        self._full_brake_btn = QPushButton("FULL BRAKE  (Space)")
        self._full_brake_btn.setStyleSheet(
            "background:#c0392b; color:white; font-weight:bold; padding:8px;"
        )
        self._full_brake_btn.clicked.connect(self._full_brake)

        self._release_btn = QPushButton("RELEASE  (Esc)")
        self._release_btn.setStyleSheet(
            "background:#7f8c8d; color:white; font-weight:bold; padding:8px;"
        )
        self._release_btn.clicked.connect(self._release)

        big_btns = QHBoxLayout()
        big_btns.addWidget(self._full_brake_btn)
        big_btns.addWidget(self._release_btn)

        # ---------- limits row ----------
        self._max_rpm_spin = QDoubleSpinBox()
        self._max_rpm_spin.setRange(0.0, 200_000.0)
        self._max_rpm_spin.setValue(cfg.max_rpm)
        self._max_rpm_spin.setSuffix(" rpm")
        self._max_rpm_spin.valueChanged.connect(self._on_limits_changed)

        self._max_current_spin = QDoubleSpinBox()
        self._max_current_spin.setRange(0.0, 200.0)
        self._max_current_spin.setValue(cfg.max_current_a)
        self._max_current_spin.setSuffix(" A")
        self._max_current_spin.valueChanged.connect(self._on_limits_changed)

        self._max_brake_spin = QDoubleSpinBox()
        self._max_brake_spin.setRange(0.0, 200.0)
        self._max_brake_spin.setValue(cfg.max_brake_current_a)
        self._max_brake_spin.setSuffix(" A")
        self._max_brake_spin.valueChanged.connect(self._on_limits_changed)

        self._arrow_step_spin = QDoubleSpinBox()
        self._arrow_step_spin.setRange(0.01, 50.0)
        self._arrow_step_spin.setValue(cfg.arrow_current_step_a)
        self._arrow_step_spin.setSuffix(" A / press")
        self._arrow_step_spin.setSingleStep(0.1)
        self._arrow_step_spin.valueChanged.connect(self._on_limits_changed)

        limits_form = QFormLayout()
        limits_form.addRow("Max RPM:",            self._max_rpm_spin)
        limits_form.addRow("Max motor current:", self._max_current_spin)
        limits_form.addRow("Max brake current:", self._max_brake_spin)
        limits_form.addRow("Arrow-key step:",    self._arrow_step_spin)

        limits_box = QGroupBox("Limits")
        limits_box.setLayout(limits_form)

        ctl_box = QGroupBox("Control")
        ctl_box_layout = QVBoxLayout(ctl_box)
        ctl_box_layout.addLayout(ctl_form)
        ctl_box_layout.addLayout(big_btns)

        # ---------- arrow-key hint ----------
        self._hint = QLabel(
            "Click here, then drive with the arrow keys:\n"
            "    ↑ / ↓  ramp current forward / reverse\n"
            "    →     bump forward    ←  bump reverse\n"
            "    Space full brake          Esc release"
        )
        self._hint.setStyleSheet(
            "background:#222; color:#ddd; padding:6px; border-radius:4px;"
        )

        self._arrow_current: float = 0.0

        # ---------- layout ----------
        bottom = QHBoxLayout()
        bottom.addWidget(ctl_box, 2)
        bottom.addWidget(limits_box, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(readouts_box)
        layout.addLayout(bottom)
        layout.addWidget(self._hint)
        layout.addStretch(1)

        self._on_mode_changed(0)

        # Wire telemetry.
        self._ctl.telemetry.connect(self._on_telemetry)
        self._ctl.connection_changed.connect(self._on_connection_changed)

    # ================================================================ slots

    def _on_telemetry(self, t: VescTelemetry) -> None:
        self._ro_voltage.set_value(f"{t.voltage_v:5.2f}")
        self._ro_current.set_value(f"{t.motor_current_a:+6.2f}")
        self._ro_in_current.set_value(f"{t.input_current_a:+6.2f}")
        self._ro_duty.set_value(f"{t.duty * 100:+5.1f}")
        self._ro_fet_temp.set_value(f"{t.mosfet_temp_c:5.1f}")
        self._ro_motor_temp.set_value(f"{t.motor_temp_c:5.1f}")
        self._ro_ah.set_value(f"{t.amp_hours_consumed:6.3f}")
        self._ro_wh.set_value(f"{t.watt_hours_consumed:6.2f}")

    def _on_connection_changed(self, connected: bool) -> None:
        self.setEnabled(connected)
        if not connected:
            self._arrow_current = 0.0

    def _on_mode_changed(self, idx: int) -> None:
        mode, _label = _MODE_ORDER[idx]
        spin = self._setpoint_spin
        spin.blockSignals(True)
        if mode is ControlMode.RPM:
            spin.setRange(-self._cfg.max_rpm, self._cfg.max_rpm)
            spin.setDecimals(0)
            spin.setSingleStep(50.0)
        elif mode is ControlMode.CURRENT:
            spin.setRange(-self._cfg.max_current_a, self._cfg.max_current_a)
            spin.setDecimals(2)
            spin.setSingleStep(0.5)
        elif mode in (ControlMode.BRAKE, ControlMode.HANDBRAKE):
            spin.setRange(0.0, self._cfg.max_brake_current_a)
            spin.setDecimals(2)
            spin.setSingleStep(0.5)
        elif mode is ControlMode.DUTY:
            spin.setRange(-1.0, 1.0)
            spin.setDecimals(3)
            spin.setSingleStep(0.01)
        elif mode is ControlMode.POSITION:
            spin.setRange(0.0, 360.0)
            spin.setDecimals(2)
            spin.setSingleStep(1.0)
        spin.setValue(0.0)
        spin.blockSignals(False)

    def _on_apply(self) -> None:
        mode, _ = _MODE_ORDER[self._mode_combo.currentIndex()]
        value = self._setpoint_spin.value()

        if mode is ControlMode.RPM:
            self._ctl.set_rpm(value)
        elif mode is ControlMode.CURRENT:
            self._ctl.set_current(value)
        elif mode is ControlMode.BRAKE:
            self._ctl.set_brake_current(value)
        elif mode is ControlMode.HANDBRAKE:
            self._ctl.set_handbrake_current(value)
        elif mode is ControlMode.DUTY:
            self._ctl.set_duty_cycle(value)
        elif mode is ControlMode.POSITION:
            self._ctl.set_position(value)

        self.status_message.emit(
            f"Applied {_MODE_ORDER[self._mode_combo.currentIndex()][1]}: {value}"
        )

    def _full_brake(self) -> None:
        self._arrow_current = 0.0
        self._ctl.full_brake()
        self.status_message.emit("FULL BRAKE engaged")

    def _release(self) -> None:
        self._arrow_current = 0.0
        self._ctl.release()
        self.status_message.emit("Motor released")

    def _on_limits_changed(self, _value: float = 0.0) -> None:
        self._cfg.max_rpm = float(self._max_rpm_spin.value())
        self._cfg.max_current_a = float(self._max_current_spin.value())
        self._cfg.max_brake_current_a = float(self._max_brake_spin.value())
        self._cfg.arrow_current_step_a = float(self._arrow_step_spin.value())
        self._ctl.set_max_brake_current(self._cfg.max_brake_current_a)
        # Re-apply current-mode range in case the user is in current mode.
        self._on_mode_changed(self._mode_combo.currentIndex())

    # =================================================== arrow-key control

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            event.accept()
            return

        key = event.key()
        step = float(self._cfg.arrow_current_step_a)
        max_i = float(self._cfg.max_current_a)

        if key == Qt.Key.Key_Up:
            self._arrow_current = min(max_i, self._arrow_current + step)
            self._ctl.set_current(self._arrow_current)
            self.status_message.emit(f"Arrow: I = {self._arrow_current:+.2f} A")
        elif key == Qt.Key.Key_Down:
            self._arrow_current = max(-max_i, self._arrow_current - step)
            self._ctl.set_current(self._arrow_current)
            self.status_message.emit(f"Arrow: I = {self._arrow_current:+.2f} A")
        elif key == Qt.Key.Key_Right:
            # Small forward bump on top of whatever's set.
            self._arrow_current = min(max_i, self._arrow_current + step * 0.5)
            self._ctl.set_current(self._arrow_current)
        elif key == Qt.Key.Key_Left:
            self._arrow_current = max(-max_i, self._arrow_current - step * 0.5)
            self._ctl.set_current(self._arrow_current)
        elif key == Qt.Key.Key_Space:
            self._full_brake()
        elif key == Qt.Key.Key_Escape:
            self._release()
        else:
            super().keyPressEvent(event)
            return

        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.isAutoRepeat():
            event.accept()
            return
        # We deliberately do NOT zero current on key release: the user
        # may want to hold a setpoint while reading a meter. They can
        # press Esc to release or Space to brake. This mirrors how VESC
        # tool behaves with its sliders.
        super().keyReleaseEvent(event)
