"""Embedded panel for picking the serial ports for the Arduino and the VESC.

This replaces the old modal *Connection* dialog: the same controls now live
directly in the left dock so the user can connect / disconnect without
opening a menu. The panel only gathers the user's choice and emits signals;
the actual opening / closing of the serial links is handled by the main
window.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports


@dataclass(frozen=True)
class ConnectionChoice:
    arduino_port: str
    arduino_baud: int
    vesc_port: str
    vesc_baud: int


class ConnectionPanel(QWidget):
    """In-window controls to pick the two serial ports and connect.

    Emits :pyattr:`connect_requested` with a :class:`ConnectionChoice` when the
    user clicks *Connect*, and :pyattr:`disconnect_requested` when the user
    clicks *Disconnect all*.
    """

    BAUD_CHOICES = [9600, 19_200, 38_400, 57_600, 115_200, 230_400, 460_800, 921_600]

    connect_requested = pyqtSignal(object)  # ConnectionChoice
    disconnect_requested = pyqtSignal()

    def __init__(
        self,
        arduino_port: str = "",
        arduino_baud: int = 115_200,
        vesc_port: str = "",
        vesc_baud: int = 115_200,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._arduino_combo = QComboBox()
        self._arduino_combo.setEditable(True)
        self._vesc_combo = QComboBox()
        self._vesc_combo.setEditable(True)

        self._arduino_baud = self._make_baud_combo(arduino_baud)
        self._vesc_baud = self._make_baud_combo(vesc_baud)

        form = QFormLayout()
        form.addRow("Arduino port (HX711)", self._arduino_combo)
        form.addRow("Arduino baud",         self._arduino_baud)
        form.addRow("VESC port",            self._vesc_combo)
        form.addRow("VESC baud",            self._vesc_baud)

        self._refresh_btn = QPushButton("Refresh ports")
        self._refresh_btn.clicked.connect(self._refresh_ports)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._emit_connect)
        self._disconnect_btn = QPushButton("Disconnect all")
        self._disconnect_btn.clicked.connect(self.disconnect_requested.emit)

        buttons = QHBoxLayout()
        buttons.addWidget(self._connect_btn)
        buttons.addWidget(self._disconnect_btn)

        self._status = QLabel("Arduino: disconnected   VESC: disconnected")
        self._status.setStyleSheet("color: gray;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(form)
        layout.addWidget(self._refresh_btn)
        layout.addLayout(buttons)
        layout.addWidget(self._status)

        self._refresh_ports()
        if arduino_port:
            self._select_or_insert(self._arduino_combo, arduino_port)
        if vesc_port:
            self._select_or_insert(self._vesc_combo, vesc_port)

    # ----------------------------------------------------------- building
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

    # ----------------------------------------------------------- choice / signals
    def choice(self) -> ConnectionChoice:
        return ConnectionChoice(
            arduino_port=self._arduino_combo.currentText().strip(),
            arduino_baud=int(self._arduino_baud.currentData()),
            vesc_port=self._vesc_combo.currentText().strip(),
            vesc_baud=int(self._vesc_baud.currentData()),
        )

    def _emit_connect(self) -> None:
        self.connect_requested.emit(self.choice())

    # ----------------------------------------------------------- status display
    def set_status(self, arduino_connected: bool, vesc_connected: bool,
                   arduino_port: str = "", vesc_port: str = "") -> None:
        """Update the small status line shown beneath the buttons."""
        ard = (
            f"Arduino: connected ({arduino_port})" if arduino_connected
            else "Arduino: disconnected"
        )
        ves = (
            f"VESC: connected ({vesc_port})" if vesc_connected
            else "VESC: disconnected"
        )
        self._status.setText(f"{ard}   {ves}")
        color = "#27ae60" if (arduino_connected or vesc_connected) else "gray"
        self._status.setStyleSheet(f"color: {color};")
