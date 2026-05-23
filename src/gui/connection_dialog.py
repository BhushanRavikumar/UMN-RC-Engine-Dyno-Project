"""Modal dialog for picking the serial ports for the Arduino and the VESC."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from serial.tools import list_ports


@dataclass(frozen=True)
class ConnectionChoice:
    arduino_port: str
    arduino_baud: int
    vesc_port: str
    vesc_baud: int


class ConnectionDialog(QDialog):
    """Lets the user pick the two serial ports without typing them by hand."""

    BAUD_CHOICES = [9600, 19_200, 38_400, 57_600, 115_200, 230_400, 460_800, 921_600]

    def __init__(
        self,
        arduino_port: str = "",
        arduino_baud: int = 115_200,
        vesc_port: str = "",
        vesc_baud: int = 115_200,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connect to hardware")

        self._arduino_combo = QComboBox()
        self._arduino_combo.setEditable(True)
        self._vesc_combo = QComboBox()
        self._vesc_combo.setEditable(True)

        self._arduino_baud = self._make_baud_combo(arduino_baud)
        self._vesc_baud = self._make_baud_combo(vesc_baud)

        self._refresh_btn = QPushButton("Refresh ports")
        self._refresh_btn.clicked.connect(self._refresh_ports)

        form = QFormLayout()
        form.addRow("Arduino port (HX711)", self._arduino_combo)
        form.addRow("Arduino baud",         self._arduino_baud)
        form.addRow("VESC port",            self._vesc_combo)
        form.addRow("VESC baud",            self._vesc_baud)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._refresh_btn)
        layout.addWidget(buttons)

        self._refresh_ports()
        if arduino_port:
            self._select_or_insert(self._arduino_combo, arduino_port)
        if vesc_port:
            self._select_or_insert(self._vesc_combo, vesc_port)

    def _make_baud_combo(self, current: int) -> QComboBox:
        combo = QComboBox()
        for b in self.BAUD_CHOICES:
            combo.addItem(str(b), userData=b)
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else self.BAUD_CHOICES.index(115_200))
        return combo

    def _refresh_ports(self) -> None:
        ports = sorted(p.device for p in list_ports.comports())
        for combo in (self._arduino_combo, self._vesc_combo):
            current = combo.currentText()
            combo.clear()
            combo.addItems(ports)
            if current:
                self._select_or_insert(combo, current)

    @staticmethod
    def _select_or_insert(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx < 0:
            combo.addItem(value)
            idx = combo.findText(value)
        combo.setCurrentIndex(idx)

    def choice(self) -> ConnectionChoice:
        return ConnectionChoice(
            arduino_port=self._arduino_combo.currentText().strip(),
            arduino_baud=int(self._arduino_baud.currentData()),
            vesc_port=self._vesc_combo.currentText().strip(),
            vesc_baud=int(self._vesc_baud.currentData()),
        )
