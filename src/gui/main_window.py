"""Main application window.

Composition:

- Left dock: load-cell calibration / torque panel stacked above the
  throttle-servo panel and the VESC motor-control panel, split
  vertically.
- Center (main area): "Live" view — RPM counter + scrolling RPM plot
  stacked above the torque counter + scrolling torque plot.

A *Connect* menu opens the connection dialog; a *Record* menu starts /
stops logging RPM and torque to a user-chosen CSV file. A status bar
shows the state of both serial links and the recording.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig
from ..data_recorder import DataRecorder
from ..hardware.loadcell_serial import LoadCellSerial
from ..hardware.vesc_controller import VescController
from .connection_dialog import ConnectionDialog
from .loadcell_panel import LoadCellPanel
from .rpm_view import RpmView
from .servo_panel import ServoPanel
from .torque_view import TorqueView
from .vesc_panel import VescPanel

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    # Preferred starting size when the screen is generous enough.
    _PREFERRED_W = 1400
    _PREFERRED_H = 880
    # Margin we leave around the window so the title bar, taskbar,
    # and OS chrome are never clipped.
    _SCREEN_MARGIN = 80

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle("Motor Dyno — Load Cell & VESC")
        # The window must never be larger than the user's screen, otherwise
        # the bottom panels of the left dock can get pushed off-screen.
        self._size_to_screen()

        self._cfg = cfg
        self._loadcell = LoadCellSerial(cfg.lc1, cfg.lc2, parent=self)
        self._vesc = VescController(parent=self)

        # ---------- left dock: load-cell, servo, and VESC panels ----------
        self._lc_panel = LoadCellPanel(cfg, self._loadcell, parent=self)
        self._servo_panel = ServoPanel(cfg, self._loadcell, parent=self)
        self._vesc_panel = VescPanel(cfg, self._vesc, parent=self)

        # All three panels live in a single dock on the left, split vertically:
        # load cells / torque on top, throttle servo in the middle, VESC
        # motor control at the bottom.
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self._wrap_in_group("Load cells & torque", self._lc_panel))
        left_splitter.addWidget(self._wrap_in_group("Throttle servo", self._servo_panel))
        left_splitter.addWidget(self._wrap_in_group("Motor control", self._vesc_panel))
        left_splitter.setStretchFactor(0, 2)
        left_splitter.setStretchFactor(1, 2)
        left_splitter.setStretchFactor(2, 2)
        # Keep handles obvious so the user can drag panel boundaries.
        left_splitter.setHandleWidth(6)
        left_splitter.setChildrenCollapsible(False)

        # Wrap the splitter in a scroll area so the three stacked panels
        # always remain reachable on shorter screens — a vertical scrollbar
        # appears only when they don't fit, and disappears as soon as the
        # user resizes the dock wide / tall enough.
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        left_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        left_scroll.setWidget(left_splitter)

        left_dock = QDockWidget("Controls", self)
        left_dock.setObjectName("ControlsDock")
        left_dock.setWidget(left_scroll)
        left_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left_dock)

        # ---------- central widget: live view ----------
        self._rpm_view = RpmView(parent=self)
        self._torque_view = TorqueView(parent=self)

        # Live view: RPM stacked above torque. Both axes use independent
        # ring buffers so they scroll at their own native sample rates.
        plots_splitter = QSplitter(Qt.Orientation.Vertical)
        plots_splitter.addWidget(self._rpm_view)
        plots_splitter.addWidget(self._torque_view)
        plots_splitter.setStretchFactor(0, 1)
        plots_splitter.setStretchFactor(1, 1)

        self.setCentralWidget(plots_splitter)

        # ---------- data recorder ----------
        self._recorder = DataRecorder(parent=self)

        # ---------- status bar ----------
        self._arduino_status = QLabel("Arduino: disconnected")
        self._vesc_status = QLabel("VESC: disconnected")
        self._record_status = QLabel("Not recording")
        self._arduino_status.setStyleSheet("color: gray;")
        self._vesc_status.setStyleSheet("color: gray;")
        self._record_status.setStyleSheet("color: gray;")

        status = QStatusBar(self)
        status.addPermanentWidget(self._arduino_status)
        status.addPermanentWidget(QLabel("    "))
        status.addPermanentWidget(self._vesc_status)
        status.addPermanentWidget(QLabel("    "))
        status.addPermanentWidget(self._record_status)
        self.setStatusBar(status)

        # ---------- menus ----------
        self._build_menus()

        # ---------- signals ----------
        self._loadcell.connection_changed.connect(self._on_arduino_conn)
        self._loadcell.error.connect(self._on_serial_error)
        self._vesc.connection_changed.connect(self._on_vesc_conn)
        self._vesc.error.connect(self._on_serial_error)
        self._vesc.telemetry.connect(self._rpm_view.add_sample)
        self._lc_panel.torque_changed.connect(self._torque_view.add_sample)
        self._vesc_panel.status_message.connect(self.statusBar().showMessage)
        self._servo_panel.status_message.connect(self.statusBar().showMessage)

        # Recording taps the same live streams as the plots, plus every
        # throttle command the user issues from the servo panel.
        self._vesc.telemetry.connect(self._recorder.on_rpm)
        self._lc_panel.torque_changed.connect(self._recorder.on_torque)
        self._servo_panel.throttle_changed.connect(self._recorder.on_throttle)
        self._recorder.recording_changed.connect(self._on_recording_changed)
        self._recorder.error.connect(self._on_serial_error)

    # ============================================================ layout helpers

    def _size_to_screen(self) -> None:
        """Resize the window to fit the user's primary screen.

        Picks the smaller of the preferred design size and the available
        screen geometry (minus a margin for the title bar / taskbar),
        then centres the window. This guarantees the bottom of the left
        dock — and the status bar — are always on-screen no matter what
        resolution the host runs at.
        """
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(self._PREFERRED_W, self._PREFERRED_H)
            return

        avail = screen.availableGeometry()
        w = min(self._PREFERRED_W, max(800, avail.width() - self._SCREEN_MARGIN))
        h = min(self._PREFERRED_H, max(600, avail.height() - self._SCREEN_MARGIN))
        self.resize(w, h)

        # Centre on the screen.
        x = avail.x() + (avail.width() - w) // 2
        y = avail.y() + (avail.height() - h) // 2
        self.move(x, y)

    @staticmethod
    def _wrap_in_group(title: str, inner: QWidget) -> QGroupBox:
        """Put a panel inside a titled group box for the stacked left dock."""
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(inner)
        return box

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

        record_menu = menubar.addMenu("&Record")
        self._start_record_act = QAction("Start recording…", self)
        self._start_record_act.setShortcut(QKeySequence("Ctrl+R"))
        self._start_record_act.triggered.connect(self._start_recording)
        record_menu.addAction(self._start_record_act)

        self._stop_record_act = QAction("Stop recording", self)
        self._stop_record_act.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self._stop_record_act.triggered.connect(self._stop_recording)
        self._stop_record_act.setEnabled(False)
        record_menu.addAction(self._stop_record_act)

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

    # ----------------------------------------------------------- recording

    def _start_recording(self) -> None:
        default_name = datetime.now().strftime("dyno_%Y%m%d_%H%M%S.csv")
        start_dir = self._cfg.last_record_dir or str(Path.home())
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Save RPM / torque recording",
            str(Path(start_dir) / default_name),
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        if self._recorder.start(path):
            self._cfg.last_record_dir = str(Path(path).parent)
            self.statusBar().showMessage(f"Recording to {path}", 4_000)

    def _stop_recording(self) -> None:
        rows = self._recorder.row_count
        path = self._recorder.path
        self._recorder.stop()
        if path is not None:
            self.statusBar().showMessage(
                f"Saved {rows} rows to {path}", 5_000
            )

    def _on_recording_changed(self, recording: bool) -> None:
        self._start_record_act.setEnabled(not recording)
        self._stop_record_act.setEnabled(recording)
        if recording:
            name = Path(self._recorder.path).name if self._recorder.path else ""
            self._record_status.setText(f"● REC  {name}")
            self._record_status.setStyleSheet("color: #c0392b; font-weight: bold;")
        else:
            self._record_status.setText("Not recording")
            self._record_status.setStyleSheet("color: gray;")

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
            "with live RPM and torque plotting and CSV recording.</p>",
        )

    # ============================================================ shutdown

    def closeEvent(self, event) -> None:  # noqa: N802
        # Flush any in-progress recording before everything tears down.
        self._recorder.stop()
        # Make sure the throttle is fully closed and the motor is not
        # left spinning when the GUI exits.
        try:
            self._servo_panel.zero_throttle()
        except Exception:  # noqa: BLE001
            pass
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
