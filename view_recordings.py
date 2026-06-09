"""Interactive viewer for dyno CSV recordings.

The companion to :mod:`src.data_recorder`. Reads any CSV produced by the
live recorder (columns ``timestamp, elapsed_s, source, rpm, torque_nm,
throttle_pct``) and plots the three telemetry channels — RPM, torque and
throttle — on an interactive pyqtgraph canvas.

The viewer offers two layout modes:

- **Stacked**  — three vertically aligned plots with linked X axes, each
  with its own Y scale. Best for reading exact values per channel.
- **Overlay**  — a single plot with three independent Y axes (one per
  channel) so signals at wildly different scales (RPM in the thousands,
  torque in single N·m, throttle in 0–100 %) can be compared visually
  without sacrificing their native units.

The mouse moves a crosshair across all visible curves; a live read-out
at the top shows the values of each channel at the cursor's time.

Usage::

    python view_recordings.py                 # opens ./Recordings
    python view_recordings.py path/to/folder  # opens an explicit folder
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- channels

# (csv_column, display_label, color, units, value format used in the
# crosshair read-out). Order here matches the stacked-plot order from
# top to bottom and the overlay axis order from left to right.
CHANNELS: list[tuple[str, str, str, str, str]] = [
    ("rpm",          "RPM",      "#2ed573", "rpm", "+9.1f"),
    ("torque_nm",    "Torque",   "#ffa502", "N·m", "+8.3f"),
    ("throttle_pct", "Throttle", "#1e90ff", "%",   "+6.1f"),
]


# ---------------------------------------------------------------- CSV loader

def load_csv(path: Path) -> dict[str, np.ndarray]:
    """Parse a dyno recording CSV.

    Returns a dict with keys ``t`` and one entry per CSV column listed in
    :data:`CHANNELS`. Each value is a numpy array of the same length;
    missing cells become ``NaN`` so matplotlib / pyqtgraph can mask them
    automatically.
    """
    t_vals: list[float] = []
    cols: dict[str, list[float]] = {name: [] for name, *_ in CHANNELS}

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                elapsed = float(row["elapsed_s"])
            except (KeyError, ValueError, TypeError):
                continue
            t_vals.append(elapsed)
            for name, *_ in CHANNELS:
                raw = row.get(name, "") or ""
                raw = raw.strip()
                if raw == "":
                    cols[name].append(float("nan"))
                else:
                    try:
                        cols[name].append(float(raw))
                    except ValueError:
                        cols[name].append(float("nan"))

    out: dict[str, np.ndarray] = {
        "t": np.asarray(t_vals, dtype=np.float64),
    }
    for name, values in cols.items():
        out[name] = np.asarray(values, dtype=np.float64)
    return out


def _mask_finite(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (t, y) keeping only points where ``y`` is finite (non-NaN)."""
    if y.size == 0:
        return t, y
    mask = np.isfinite(y)
    return t[mask], y[mask]


# ---------------------------------------------------------------- main window

class ViewerWindow(QMainWindow):
    """Top-level viewer window: toolbar + plot canvas + read-out strip."""

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.setWindowTitle("Dyno Recording Viewer")
        self._size_to_screen()

        self._folder: Path = folder
        self._data: Optional[dict[str, np.ndarray]] = None

        # References to extra plot artifacts that must survive a layout
        # rebuild (Python may GC ViewBoxes / AxisItems otherwise).
        self._extra_viewboxes: list[pg.ViewBox] = []
        self._extra_axes: list[pg.AxisItem] = []
        self._extra_curves: list[pg.PlotDataItem] = []
        self._crosshair_lines: list[pg.InfiniteLine] = []
        # Items we added to the QGraphicsScene directly (overlay-mode
        # ViewBoxes, the manual LegendItem, etc.). ``GraphicsLayoutWidget``'s
        # ``clear()`` only empties the central layout, so anything in this
        # list must be removed from the scene by hand on every rebuild —
        # otherwise the previous mode's artefacts ghost behind the new
        # plots.
        self._scene_items: list = []
        # Resize-sync hook installed in overlay mode; we need to drop it
        # before destroying the ViewBoxes its closure captures.
        self._sync_signal = None
        self._sync_slot = None
        self._cursor_proxy: Optional[pg.SignalProxy] = None
        self._main_plot: Optional[pg.PlotItem] = None
        self._main_vb: Optional[pg.ViewBox] = None
        self._stacked_plots: list[pg.PlotItem] = []

        # ---------- toolbar ----------
        self._file_combo = QComboBox()
        self._file_combo.setMinimumWidth(280)
        self._file_combo.currentIndexChanged.connect(self._on_file_selected)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_files)

        browse_btn = QPushButton("Browse folder…")
        browse_btn.clicked.connect(self._browse_folder)

        self._stacked_radio = QRadioButton("Stacked")
        self._overlay_radio = QRadioButton("Overlay")
        self._stacked_radio.setChecked(True)
        layout_group = QButtonGroup(self)
        layout_group.addButton(self._stacked_radio)
        layout_group.addButton(self._overlay_radio)
        self._stacked_radio.toggled.connect(self._on_layout_changed)

        self._folder_label = QLabel()
        self._folder_label.setStyleSheet("color: gray;")
        self._update_folder_label()

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Recording:"))
        toolbar.addWidget(self._file_combo, 1)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(browse_btn)
        toolbar.addSpacing(20)
        toolbar.addWidget(QLabel("Layout:"))
        toolbar.addWidget(self._stacked_radio)
        toolbar.addWidget(self._overlay_radio)

        # ---------- crosshair read-out strip ----------
        self._readout_label = QLabel("Hover a plot to inspect values")
        readout_font = QFont("Consolas", 11)
        readout_font.setStyleHint(QFont.StyleHint.Monospace)
        self._readout_label.setFont(readout_font)
        self._readout_label.setStyleSheet(
            "background:#16191d; color:#ddd; padding:6px; border-radius:4px;"
        )
        self._readout_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---------- plot canvas ----------
        pg.setConfigOptions(antialias=True)
        self._canvas = pg.GraphicsLayoutWidget()
        self._canvas.setBackground("#101418")

        # ---------- assemble ----------
        outer = QVBoxLayout()
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(toolbar)
        outer.addWidget(self._folder_label)
        outer.addWidget(self._readout_label)
        outer.addWidget(self._canvas, 1)

        central = QWidget()
        central.setLayout(outer)
        self.setCentralWidget(central)

        # ---------- initial load ----------
        self._refresh_files()

    # ============================================================ window sizing

    def _size_to_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1200, 800)
            return
        avail = screen.availableGeometry()
        w = min(1400, max(900, avail.width() - 80))
        h = min(900, max(600, avail.height() - 100))
        self.resize(w, h)
        self.move(
            avail.x() + (avail.width() - w) // 2,
            avail.y() + (avail.height() - h) // 2,
        )

    # ============================================================ file picking

    def _update_folder_label(self) -> None:
        self._folder_label.setText(f"Folder: {self._folder.resolve()}")

    def _refresh_files(self) -> None:
        self._file_combo.blockSignals(True)
        self._file_combo.clear()

        files: list[Path] = []
        if self._folder.is_dir():
            files = sorted(
                self._folder.glob("*.csv"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,  # newest first
            )

        for p in files:
            self._file_combo.addItem(p.name, userData=str(p))

        self._file_combo.blockSignals(False)

        if files:
            self._file_combo.setCurrentIndex(0)
            self._on_file_selected(0)
        else:
            self._data = None
            self._canvas.clear()
            self._readout_label.setText(
                f"No CSV files in {self._folder.resolve()}"
            )

    def _browse_folder(self) -> None:
        start = str(self._folder.resolve()) if self._folder.exists() else ""
        new = QFileDialog.getExistingDirectory(
            self, "Select recordings folder", start
        )
        if new:
            self._folder = Path(new)
            self._update_folder_label()
            self._refresh_files()

    def _on_file_selected(self, _index: int) -> None:
        path = self._file_combo.currentData()
        if not path:
            return
        try:
            self._data = load_csv(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Open failed", f"Could not read CSV:\n{exc}")
            self._data = None
            self._canvas.clear()
            return

        if self._data["t"].size == 0:
            self._canvas.clear()
            self._readout_label.setText("Selected file has no rows")
            return

        self._rebuild_plots()

    def _on_layout_changed(self, _checked: bool) -> None:
        if self._data is not None:
            self._rebuild_plots()

    # ============================================================ plot build

    def _rebuild_plots(self) -> None:
        """Tear down any previous plot graph and build the active mode."""
        # Drop the mouse-tracking proxy first so it can't fire against
        # items we're about to delete.
        self._cursor_proxy = None

        # Disconnect the overlay-mode resize sync before its captured
        # ViewBoxes / curves go away; otherwise the closure can keep
        # ghosting them alive after a mode switch.
        if self._sync_signal is not None and self._sync_slot is not None:
            try:
                self._sync_signal.disconnect(self._sync_slot)
            except (TypeError, RuntimeError):
                pass
        self._sync_signal = None
        self._sync_slot = None

        # Items added to the QGraphicsScene directly are NOT removed by
        # ``GraphicsLayoutWidget.clear()``. Remove them by hand so the
        # previous overlay's extra ViewBoxes / legend don't keep painting
        # behind the new stacked plots.
        scene = self._canvas.scene()
        if scene is not None:
            for item in self._scene_items:
                try:
                    scene.removeItem(item)
                except (RuntimeError, ValueError):
                    pass
        self._scene_items.clear()

        self._main_plot = None
        self._main_vb = None
        self._extra_viewboxes.clear()
        self._extra_axes.clear()
        self._extra_curves.clear()
        self._crosshair_lines.clear()
        self._stacked_plots.clear()
        self._canvas.clear()

        if self._data is None or self._data["t"].size == 0:
            return

        if self._stacked_radio.isChecked():
            self._build_stacked()
        else:
            self._build_overlay()

        self._install_crosshair()

    # ---------------------------------------------------------- stacked

    def _build_stacked(self) -> None:
        t = self._data["t"]
        first: Optional[pg.PlotItem] = None

        for i, (name, label, color, units, _fmt) in enumerate(CHANNELS):
            y = self._data.get(name)
            if y is None or y.size == 0:
                continue
            tt, yy = _mask_finite(t, y)

            plot: pg.PlotItem = self._canvas.addPlot(row=i, col=0)
            plot.setLabel("left", label, units=units)
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.plot(tt, yy, pen=pg.mkPen(color, width=2), name=label)

            # Link X axes so panning one plot pans them all.
            if first is None:
                first = plot
                plot.setLabel("bottom", "", units="")  # blank until last
            else:
                plot.setXLink(first)

            # Only the bottom-most plot shows the X label.
            if i == len(CHANNELS) - 1:
                plot.setLabel("bottom", "Time", units="s")
            else:
                plot.getAxis("bottom").setStyle(showValues=True)
                plot.setLabel("bottom", "")

            self._stacked_plots.append(plot)

        if self._stacked_plots:
            self._main_plot = self._stacked_plots[0]
            self._main_vb = self._main_plot.vb

    # ---------------------------------------------------------- overlay

    def _build_overlay(self) -> None:
        """Single plot, three independent Y axes (one per channel).

        The first channel uses the PlotItem's native left axis. Each
        subsequent channel gets its own ``ViewBox`` and ``AxisItem``
        added to the right side of the layout, all sharing the main X
        axis.
        """
        t = self._data["t"]

        # Resolve which channels actually have any finite data so we
        # don't waste an axis on an empty signal.
        active: list[tuple[str, str, str, str, str]] = []
        for entry in CHANNELS:
            name = entry[0]
            y = self._data.get(name)
            if y is None or not np.isfinite(y).any():
                continue
            active.append(entry)

        if not active:
            return

        # First channel -> primary left axis of the main PlotItem.
        first_name, first_label, first_color, first_units, _ = active[0]
        plot: pg.PlotItem = self._canvas.addPlot(row=0, col=0)
        plot.setLabel("bottom", "Time", units="s")
        plot.setLabel("left", first_label, units=first_units, color=first_color)
        plot.getAxis("left").setTextPen(first_color)
        plot.showGrid(x=True, y=True, alpha=0.3)
        tt, yy = _mask_finite(t, self._data[first_name])
        first_curve = plot.plot(
            tt, yy, pen=pg.mkPen(first_color, width=2), name=first_label
        )
        self._extra_curves.append(first_curve)

        self._main_plot = plot
        self._main_vb = plot.vb

        # Subsequent channels -> extra ViewBoxes on the right.
        for col_offset, entry in enumerate(active[1:], start=1):
            name, label, color, units, _ = entry
            tt, yy = _mask_finite(t, self._data[name])

            axis = pg.AxisItem("right")
            axis.setLabel(label, units=units, color=color)
            axis.setTextPen(color)
            self._canvas.addItem(axis, row=0, col=col_offset)

            vb = pg.ViewBox()
            # The ViewBox is added to the scene directly (not to the
            # layout) so we must remember to remove it by hand on the
            # next rebuild — see _rebuild_plots.
            self._canvas.scene().addItem(vb)
            self._scene_items.append(vb)
            axis.linkToView(vb)
            vb.setXLink(plot)

            curve = pg.PlotDataItem(tt, yy, pen=pg.mkPen(color, width=2))
            vb.addItem(curve)

            self._extra_viewboxes.append(vb)
            self._extra_axes.append(axis)
            self._extra_curves.append(curve)

        # The extra ViewBoxes don't follow the main PlotItem's resize on
        # their own; sync them whenever the main view box geometry
        # changes (resize, splitter drag, dock undock, etc.).
        def _sync_views() -> None:
            if self._main_vb is None:
                return
            geom = self._main_vb.sceneBoundingRect()
            for vb in self._extra_viewboxes:
                vb.setGeometry(geom)
                vb.linkedViewChanged(self._main_vb, vb.XAxis)

        _sync_views()
        plot.vb.sigResized.connect(_sync_views)
        # Remember the connection so _rebuild_plots can disconnect it
        # before tearing down the ViewBoxes the closure captures.
        self._sync_signal = plot.vb.sigResized
        self._sync_slot = _sync_views

        # Custom legend so all three curves are listed even though they
        # live in different ViewBoxes (PlotItem.addLegend only picks up
        # its own items). The legend's parent is the main viewbox, but
        # under the hood it lives directly in the scene — track it so
        # the next rebuild can purge it cleanly.
        legend = pg.LegendItem(offset=(70, 30))
        legend.setParentItem(plot.vb)
        for entry, curve in zip(active, self._extra_curves):
            label = f"{entry[1]} ({entry[3]})"
            legend.addItem(curve, label)
        self._scene_items.append(legend)

    # ============================================================ crosshair

    def _install_crosshair(self) -> None:
        if self._main_plot is None or self._main_vb is None:
            return

        v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#888"))
        h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#444"))
        self._main_plot.addItem(v_line, ignoreBounds=True)
        self._main_plot.addItem(h_line, ignoreBounds=True)
        self._crosshair_lines.append(v_line)
        self._crosshair_lines.append(h_line)

        # In stacked mode, drop a synchronised vertical line on every
        # plot so the cursor X is consistent across all three signals.
        if self._stacked_radio.isChecked() and hasattr(self, "_stacked_plots"):
            for plot in self._stacked_plots[1:]:
                vl = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#888"))
                plot.addItem(vl, ignoreBounds=True)
                self._crosshair_lines.append(vl)

        # Throttle the mouse-move signal so we don't repaint at every
        # sub-pixel motion. SignalProxy keeps the cost bounded.
        self._cursor_proxy = pg.SignalProxy(
            self._main_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def _on_mouse_moved(self, evt) -> None:
        """Update the crosshair position and the value read-out strip."""
        if self._main_plot is None or self._main_vb is None or self._data is None:
            return

        pos = evt[0]
        if not self._main_plot.sceneBoundingRect().contains(pos):
            return

        mouse_pt: QPointF = self._main_vb.mapSceneToView(pos)
        x = float(mouse_pt.x())

        # Move every vertical line to the cursor's X.
        for line in self._crosshair_lines:
            if line.angle == 90:
                line.setPos(x)
            else:
                line.setPos(float(mouse_pt.y()))

        # Look up the sample nearest to the cursor X in time. The CSV
        # rows are written in order so the elapsed-time column is
        # monotonic and ``searchsorted`` finds the right index in
        # O(log n) without a full scan.
        t = self._data["t"]
        if t.size == 0:
            return
        idx = int(np.clip(np.searchsorted(t, x), 0, t.size - 1))
        # Use the closer of (idx-1, idx) so a cursor between samples
        # picks the visually nearest one.
        if idx > 0 and abs(t[idx - 1] - x) < abs(t[idx] - x):
            idx -= 1

        parts = [f"t = {t[idx]:6.3f} s"]
        for name, label, color, units, fmt in CHANNELS:
            y = self._data.get(name)
            if y is None or y.size == 0:
                continue
            val = y[idx]
            if not np.isfinite(val):
                parts.append(
                    f"<span style='color:{color}'>{label}: —</span>"
                )
            else:
                parts.append(
                    f"<span style='color:{color}'>"
                    f"{label}: {val:{fmt}} {units}"
                    f"</span>"
                )

        self._readout_label.setText("    ".join(parts))


# ---------------------------------------------------------------- entry point

def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive viewer for dyno recording CSVs. Lists every "
            "*.csv in the given folder; defaults to ./Recordings."
        ),
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default="Recordings",
        help="Folder to scan for CSV recordings (default: ./Recordings)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    app = QApplication(sys.argv)
    app.setApplicationName("Dyno Recording Viewer")
    app.setOrganizationName("UMN")

    window = ViewerWindow(folder=Path(args.folder))
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
