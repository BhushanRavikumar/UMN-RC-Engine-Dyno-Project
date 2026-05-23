"""Main application window.

Composition:

- Left dock: load-cell calibration / torque panel.
- Right side (main area): tabbed view with
    * "Live": RPM counter + scrolling RPM plot + animated motor graphic.
    * "Control": VESC control panel (arrow-key driving).

A *Connect* menu opens the connection dialog; a status bar shows the
state of both serial links.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..hardware.loadcell_serial import LoadCellSerial
from ..hardware.vesc_controller import VescController
from .connection_dialog import ConnectionDialog
from .loadcell_panel import LoadCellPanel
from .motor_graphic import MotorGraphic
from .rpm_view import RpmView
from .torque_view import TorqueView
from .vesc_panel import VescPanel

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("Motor Dyno — Load Cell & VESC")
        self.resize(1400, 880)

        self._cfg = cfg
        self._loadcell = LoadCellSerial(cfg.lc1, cfg.lc2, parent=self)
        self._vesc = VescController(parent=self)

        # ---------- left dock: load-cell panel ----------
        self._lc_panel = LoadCellPanel(cfg, self._loadcell, parent=self)
        lc_dock = QDockWidget("Load cells && torque", self)
        lc_dock.setObjectName("LoadCellDock")
        lc_dock.setWidget(self._lc_panel)
        lc_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, lc_dock)

        # ---------- central widget: tabs ----------
        self._rpm_view = RpmView(parent=self)
        self._torque_view = TorqueView(parent=self)
        self._motor_graphic = MotorGraphic(parent=self)
        self._vesc_panel = VescPanel(cfg, self._vesc, parent=self)

        # "Live" tab: motor graphic on the left, RPM stacked above torque
        # on the right. Both axes use independent ring buffers so they
        # scroll at their own native sample rates.
        live_tab = QWidget()
        plots_splitter = QSplitter(Qt.Orientation.Vertical)
        plots_splitter.addWidget(self._rpm_view)
        plots_splitter.addWidget(self._torque_view)
        plots_splitter.setStretchFactor(0, 1)
        plots_splitter.setStretchFactor(1, 1)

        live_splitter = QSplitter(Qt.Orientation.Horizontal, live_tab)
        live_splitter.addWidget(self._motor_graphic)
        live_splitter.addWidget(plots_splitter)
        live_splitter.setStretchFactor(0, 1)
        live_splitter.setStretchFactor(1, 2)

        live_layout = QHBoxLayout(live_tab)
        live_layout.setContentsMargins(0, 0, 0, 0)
        live_layout.addWidget(live_splitter)

        tabs = QTabWidget()
        tabs.addTab(live_tab, "Live")
        tabs.addTab(self._vesc_panel, "Control")
        self.setCentralWidget(tabs)

        # ---------- status bar ----------
        self._arduino_status = QLabel("Arduino: disconnected")
        self._vesc_status = QLabel("VESC: disconnected")
        self._arduino_status.setStyleSheet("color: gray;")
        self._vesc_status.setStyleSheet("color: gray;")

        status = QStatusBar(self)
        status.addPermanentWidget(self._arduino_status)
        status.addPermanentWidget(QLabel("    "))
        status.addPermanentWidget(self._vesc_status)
        self.setStatusBar(status)

        # ---------- menus ----------
        self._build_menus()

        # ---------- signals ----------
        self._loadcell.connection_changed.connect(self._on_arduino_conn)
        self._loadcell.error.connect(self._on_serial_error)
        self._vesc.connection_changed.connect(self._on_vesc_conn)
        self._vesc.connection_changed.connect(self._motor_graphic.set_connected)
        self._vesc.error.connect(self._on_serial_error)
        self._vesc.telemetry.connect(self._rpm_view.add_sample)
        self._vesc.telemetry.connect(self._motor_graphic.add_sample)
        self._lc_panel.torque_changed.connect(self._torque_view.add_sample)
        self._vesc_panel.status_message.connect(self.statusBar().showMessage)

    # ============================================================ menu/actions

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        save_act = QAction("Save settings", self)
        save_act.setShortcut(QKeySequence("Ctrl+S"))
        save_act.triggered.connect(self._save_settings)
        file_menu.addAction(save_act)
        file_menu.addSeparator()
        quit_act = QAction("Quit", self)
        quit_act.setShortcut(QKeySequence("Ctrl+Q"))
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        conn_menu = menubar.addMenu("&Connection")
        connect_act = QAction("Connect…", self)
        connect_act.setShortcut(QKeySequence("Ctrl+K"))
        connect_act.triggered.connect(self._open_connection_dialog)
        conn_menu.addAction(connect_act)

        disconnect_act = QAction("Disconnect all", self)
        disconnect_act.triggered.connect(self._disconnect_all)
        conn_menu.addAction(disconnect_act)

        help_menu = menubar.addMenu("&Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    # ============================================================ slots

    def _open_connection_dialog(self) -> None:
        dlg = ConnectionDialog(
            arduino_port=self._cfg.arduino_port,
            arduino_baud=self._cfg.arduino_baud,
            vesc_port=self._cfg.vesc_port,
            vesc_baud=self._cfg.vesc_baud,
            parent=self,
        )
        if dlg.exec() != ConnectionDialog.DialogCode.Accepted:
            return

        choice = dlg.choice()
        self._cfg.arduino_port = choice.arduino_port
        self._cfg.arduino_baud = choice.arduino_baud
        self._cfg.vesc_port = choice.vesc_port
        self._cfg.vesc_baud = choice.vesc_baud

        # Disconnect first to avoid double-open errors.
        self._loadcell.close()
        self._vesc.close()

        if choice.arduino_port:
            self._loadcell.open(choice.arduino_port, choice.arduino_baud)
        if choice.vesc_port:
            self._vesc.open(choice.vesc_port, choice.vesc_baud)

    def _disconnect_all(self) -> None:
        self._loadcell.close()
        self._vesc.close()

    def _save_settings(self) -> None:
        try:
            self._cfg.save()
            self.statusBar().showMessage("Settings saved", 2_000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Save failed", str(exc))

    def _on_arduino_conn(self, connected: bool) -> None:
        if connected:
            self._arduino_status.setText(
                f"Arduino: connected ({self._cfg.arduino_port})"
            )
            self._arduino_status.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            self._arduino_status.setText("Arduino: disconnected")
            self._arduino_status.setStyleSheet("color: gray;")

    def _on_vesc_conn(self, connected: bool) -> None:
        if connected:
            self._vesc_status.setText(f"VESC: connected ({self._cfg.vesc_port})")
            self._vesc_status.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            self._vesc_status.setText("VESC: disconnected")
            self._vesc_status.setStyleSheet("color: gray;")

    def _on_serial_error(self, message: str) -> None:
        log.warning("Serial error: %s", message)
        self.statusBar().showMessage(message, 5_000)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            "<h3>Motor Dyno GUI</h3>"
            "<p>HX711 load cells via Arduino + VESC motor controller "
            "with live RPM, torque, and animated motor graphic.</p>",
        )

    # ============================================================ shutdown

    def closeEvent(self, event) -> None:  # noqa: N802
        # Make sure the motor is not left spinning when the GUI exits.
        try:
            self._vesc.release()
        except Exception:  # noqa: BLE001
            pass
        self._loadcell.close()
        self._vesc.close()
        try:
            self._cfg.save()
        except Exception:  # noqa: BLE001
            log.exception("Failed to save settings on shutdown")
        super().closeEvent(event)
