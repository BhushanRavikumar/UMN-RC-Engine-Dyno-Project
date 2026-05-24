"""GUI panel for load-cell calibration and live force / torque display.

The panel exposes two columns (one per cell) with:

- A live raw / filtered Newton reading.
- A *Tare* button that snapshots the current raw count as the zero offset.
- A *Calibrate* button that asks the user for the reference mass in kg
  and computes ``counts_per_newton`` from the difference between the
  current raw count and the tare offset.

A lever-arm spin box at the bottom converts the absolute difference of
the two forces to a torque in N·m, which is also published over the ``torque_changed``
signal so other widgets (e.g. the data logger) can listen in.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, LoadCellCalibration
from ..hardware.loadcell_serial import LoadCellSample, LoadCellSerial

G_M_S2 = 9.806_65  # Standard gravity, for converting kg of reference mass to N.


class _ChannelBox(QGroupBox):
    """One per load cell: shows force, has Tare and Calibrate buttons."""

    request_tare = pyqtSignal()
    request_calibrate = pyqtSignal(float)  # known mass in kg

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)

        self._force_label = QLabel("—")
        self._force_label.setStyleSheet("font-size: 22pt; font-weight: bold;")
        self._force_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._raw_label = QLabel("raw: —")
        self._raw_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._cal_label = QLabel("offset: 0  slope: 1.0 cnt/N")
        self._cal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cal_label.setStyleSheet("color: gray;")

        tare_btn = QPushButton("Tare")
        tare_btn.setToolTip("Set the current reading as the new zero.")
        tare_btn.clicked.connect(self.request_tare.emit)

        cal_btn = QPushButton("Calibrate…")
        cal_btn.setToolTip(
            "Place a known mass on the load cell, then enter the mass in kg."
        )
        cal_btn.clicked.connect(self._on_calibrate_clicked)

        btns = QHBoxLayout()
        btns.addWidget(tare_btn)
        btns.addWidget(cal_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._force_label)
        layout.addWidget(self._raw_label)
        layout.addWidget(self._cal_label)
        layout.addLayout(btns)

    def _on_calibrate_clicked(self) -> None:
        mass_kg, ok = QInputDialog.getDouble(
            self,
            "Calibrate load cell",
            "Reference mass currently on the cell (kg):",
            value=1.0,
            min=1e-6,
            max=1e6,
            decimals=4,
        )
        if ok:
            self.request_calibrate.emit(float(mass_kg))

    def update_reading(self, raw: int, force_n: float) -> None:
        self._force_label.setText(f"{force_n:+8.3f} N")
        self._raw_label.setText(f"raw: {raw}")

    def update_calibration(self, cal: LoadCellCalibration) -> None:
        self._cal_label.setText(
            f"offset: {cal.tare_offset:.0f}   slope: {cal.counts_per_newton:.4f} cnt/N"
        )


class LoadCellPanel(QWidget):
    """Top-level widget tying both channels together with a lever arm input."""

    # (t_monotonic, torque_nm) — paired so plots can timestamp samples
    # consistently with the load-cell stream rather than at receive time.
    torque_changed = pyqtSignal(float, float)

    def __init__(
        self,
        cfg: AppConfig,
        loadcell: LoadCellSerial,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._lc = loadcell
        self._latest_sample: Optional[LoadCellSample] = None

        self._lc1 = _ChannelBox("Load cell 1")
        self._lc2 = _ChannelBox("Load cell 2")
        self._lc1.update_calibration(cfg.lc1)
        self._lc2.update_calibration(cfg.lc2)

        # Lever-arm + torque section.
        self._lever_spin = QDoubleSpinBox()
        self._lever_spin.setRange(0.001, 10.0)
        self._lever_spin.setDecimals(4)
        self._lever_spin.setSingleStep(0.005)
        self._lever_spin.setSuffix(" m")
        self._lever_spin.setValue(cfg.lever_arm_m)
        self._lever_spin.valueChanged.connect(self._on_lever_changed)

        self._torque_label = QLabel("0.000 N·m")
        self._torque_label.setStyleSheet(
            "font-size: 28pt; font-weight: bold; color: #2566c8;"
        )
        self._torque_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)

        form = QFormLayout()
        form.addRow("Lever arm length:", self._lever_spin)
        form.addRow("Net torque:", self._torque_label)

        channels = QHBoxLayout()
        channels.addWidget(self._lc1)
        channels.addWidget(self._lc2)

        layout = QVBoxLayout(self)
        layout.addLayout(channels)
        layout.addWidget(sep)
        layout.addLayout(form)
        layout.addStretch(1)

        # Wire up signals.
        self._lc.sample.connect(self._on_sample)
        self._lc1.request_tare.connect(lambda: self._tare(channel=1))
        self._lc2.request_tare.connect(lambda: self._tare(channel=2))
        self._lc1.request_calibrate.connect(lambda m: self._calibrate(channel=1, mass_kg=m))
        self._lc2.request_calibrate.connect(lambda m: self._calibrate(channel=2, mass_kg=m))

    # =========================================================== slot logic

    def _on_sample(self, sample: LoadCellSample) -> None:
        self._latest_sample = sample
        self._lc1.update_reading(sample.raw1, sample.force1_n)
        self._lc2.update_reading(sample.raw2, sample.force2_n)

        torque = abs(sample.force1_n - sample.force2_n) * self._cfg.lever_arm_m
        self._torque_label.setText(f"{torque:+.3f} N·m")
        self.torque_changed.emit(sample.t_monotonic, torque)

    def _on_lever_changed(self, value: float) -> None:
        self._cfg.lever_arm_m = float(value)

    def _tare(self, channel: int) -> None:
        if self._latest_sample is None:
            QMessageBox.information(
                self,
                "Tare",
                "No load-cell samples received yet — is the Arduino connected?",
            )
            return

        if channel == 1:
            self._cfg.lc1.tare_offset = float(self._latest_sample.raw1)
            self._lc.set_calibration(self._cfg.lc1, self._cfg.lc2)
            self._lc1.update_calibration(self._cfg.lc1)
        else:
            self._cfg.lc2.tare_offset = float(self._latest_sample.raw2)
            self._lc.set_calibration(self._cfg.lc1, self._cfg.lc2)
            self._lc2.update_calibration(self._cfg.lc2)

    def _calibrate(self, channel: int, mass_kg: float) -> None:
        if self._latest_sample is None:
            QMessageBox.information(
                self,
                "Calibrate",
                "No load-cell samples received yet — is the Arduino connected?",
            )
            return

        cal = self._cfg.lc1 if channel == 1 else self._cfg.lc2
        raw = self._latest_sample.raw1 if channel == 1 else self._latest_sample.raw2

        delta = float(raw) - cal.tare_offset
        force_n = mass_kg * G_M_S2

        if not math.isfinite(delta) or abs(delta) < 1e-6 or force_n <= 0.0:
            QMessageBox.warning(
                self,
                "Calibrate",
                "Couldn't compute a slope — make sure the cell is tared first "
                "and that the reference mass is actually loaded.",
            )
            return

        cal.counts_per_newton = delta / force_n
        self._lc.set_calibration(self._cfg.lc1, self._cfg.lc2)
        if channel == 1:
            self._lc1.update_calibration(cal)
        else:
            self._lc2.update_calibration(cal)
