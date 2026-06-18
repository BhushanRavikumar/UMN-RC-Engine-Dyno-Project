# Graph Report - .  (2026-06-18)

## Corpus Check
- 0 files · ~11,536 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 261 nodes · 508 edges · 14 communities (11 shown, 3 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 55 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_VESC Motor Control|VESC Motor Control]]
- [[_COMMUNITY_Live Plotting & Telemetry Views|Live Plotting & Telemetry Views]]
- [[_COMMUNITY_Servo Throttle Panel|Servo Throttle Panel]]
- [[_COMMUNITY_Load Cell Panel & Calibration|Load Cell Panel & Calibration]]
- [[_COMMUNITY_Recording Viewer Tool|Recording Viewer Tool]]
- [[_COMMUNITY_Main Window & Menus|Main Window & Menus]]
- [[_COMMUNITY_Load Cell Serial IO|Load Cell Serial I/O]]
- [[_COMMUNITY_VESC Control Panel|VESC Control Panel]]
- [[_COMMUNITY_CSV Data Recording|CSV Data Recording]]
- [[_COMMUNITY_Connection Dialog|Connection Dialog]]
- [[_COMMUNITY_App Config & Entry Point|App Config & Entry Point]]
- [[_COMMUNITY_GUI Package Init|GUI Package Init]]
- [[_COMMUNITY_Hardware Package Init|Hardware Package Init]]
- [[_COMMUNITY_Source Package Init|Source Package Init]]

## God Nodes (most connected - your core abstractions)
1. `ServoPanel` - 33 edges
2. `VescController` - 30 edges
3. `MainWindow` - 29 edges
4. `LoadCellSerial` - 24 edges
5. `DataRecorder` - 23 edges
6. `VescPanel` - 21 edges
7. `LoadCellPanel` - 20 edges
8. `ViewerWindow` - 20 edges
9. `AppConfig` - 16 edges
10. `RpmView` - 16 edges

## Surprising Connections (you probably didn't know these)
- `ScrollingPlot` --semantically_similar_to--> `ViewerWindow`  [INFERRED] [semantically similar]
  src/gui/plots.py → view_recordings.py
- `Python Requirements` --conceptually_related_to--> `VescController`  [INFERRED]
  requirements.txt → src/hardware/vesc_controller.py
- `Motor Dyno README` --references--> `AppConfig`  [EXTRACTED]
  README.md → src/config.py
- `Motor Dyno README` --references--> `DataRecorder`  [EXTRACTED]
  README.md → src/data_recorder.py
- `Motor Dyno README` --references--> `ServoPanel`  [EXTRACTED]
  README.md → src/gui/servo_panel.py

## Import Cycles
- None detected.

## Communities (14 total, 3 thin omitted)

### Community 0 - "VESC Motor Control"
Cohesion: 0.07
Nodes (20): Any, Enum, _Mode, GUI panel for the throttle servo.  The panel runs in one of two mutually exclu, GUI panel for driving the VESC.  Layout:  - A grid of telemetry read-outs (v, ControlMode, Background controller for a VESC-based motor controller.  This module wraps th, Thread-safe asynchronous wrapper around a VESC over UART/USB-CDC.      Signals (+12 more)

### Community 1 - "Live Plotting & Telemetry Views"
Cohesion: 0.12
Nodes (13): LiveCounter, Reusable live-data widgets.  Two pieces are exported:  - :class:`LiveCounter, Scrolling time-series plot backed by a numpy ring buffer.      The plot only r, Large numeric read-out for a single scalar signal., ScrollingPlot, Live RPM view: composite of a big numeric counter + scrolling plot.  The widge, Big RPM counter on top, scrolling RPM-vs-time plot below., RpmView (+5 more)

### Community 2 - "Servo Throttle Panel"
Cohesion: 0.14
Nodes (10): Dead-man Throttle Control, Linearly interpolate between the two calibrated angles., Command 0 % throttle (used on Space, disconnect and shutdown)., Original nudge-style arrow-key handling for calibration mode., Calibration + manual / keyboard throttle control for the servo., ServoPanel, QKeyEvent, QGroupBox (+2 more)

### Community 3 - "Load Cell Panel & Calibration"
Cohesion: 0.11
Nodes (16): _ChannelBox, LoadCellPanel, GUI panel for load-cell calibration and live force / torque display.  The pane, Top-level widget tying both channels together with a lever arm input., One per load cell: shows force, has Tare and Calibrate buttons., LoadCellSample, Serial interface to the dual-HX711 + throttle-servo Arduino sketch.  The Ardui, A single synchronised reading from both load cells. (+8 more)

### Community 4 - "Recording Viewer Tool"
Cohesion: 0.13
Nodes (15): Namespace, ndarray, load_csv(), main(), _mask_finite(), _parse_args(), Path, Interactive viewer for dyno CSV recordings.  The companion to :mod:`src.data_r (+7 more)

### Community 5 - "Main Window & Menus"
Cohesion: 0.11
Nodes (6): MainWindow, Resize the window to fit the user's primary screen.          Picks the smaller, Put a panel inside a titled group box for the stacked left dock., QMainWindow, AppConfig, QWidget

### Community 6 - "Load Cell Serial I/O"
Cohesion: 0.14
Nodes (8): _apply_cal(), LoadCellSerial, Replace the in-memory calibration objects atomically., Send a throttle-servo angle command to the Arduino.          The angle is clam, Convert a raw HX711 count to Newtons using a tare + slope model., Background reader for the dual-HX711 Arduino.      Signals     -------     s, Motor Dyno README, LoadCellCalibration

### Community 7 - "VESC Control Panel"
Cohesion: 0.14
Nodes (8): One bordered cell: label + big value., Telemetry display and on-screen setpoint controls., _Readout, VescPanel, QFrame, AppConfig, VescTelemetry, VescController

### Community 8 - "CSV Data Recording"
Cohesion: 0.16
Nodes (6): QObject, Dyno Recording CSV Schema, DataRecorder, VescTelemetry, Append-only CSV logger for RPM and torque samples.      Signals     -------, Open ``path`` for writing and emit the CSV header.          Returns ``True`` o

### Community 9 - "Connection Dialog"
Cohesion: 0.24
Nodes (7): ConnectionChoice, ConnectionDialog, Modal dialog for picking the serial ports for the Arduino and the VESC., Lets the user pick the two serial ports without typing them by hand., Main application window.  Composition:  - Left dock: load-cell calibration /, QComboBox, QDialog

### Community 10 - "App Config & Entry Point"
Cohesion: 0.33
Nodes (6): AppConfig, Path, All persisted user settings., _configure_logging(), main(), Application entry point.  Run as::      python -m src.main

## Knowledge Gaps
- **13 isolated node(s):** `VescTelemetry`, `LoadCellCalibration`, `AppConfig`, `LoadCellSerial`, `LoadCellSample` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ServoPanel` connect `Servo Throttle Panel` to `VESC Motor Control`, `Live Plotting & Telemetry Views`, `Main Window & Menus`, `Load Cell Serial I/O`, `CSV Data Recording`, `Connection Dialog`, `App Config & Entry Point`?**
  _High betweenness centrality (0.195) - this node is a cross-community bridge._
- **Why does `DataRecorder` connect `CSV Data Recording` to `VESC Motor Control`, `Servo Throttle Panel`, `Load Cell Panel & Calibration`, `Recording Viewer Tool`, `Main Window & Menus`, `Load Cell Serial I/O`, `Connection Dialog`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Why does `VescController` connect `VESC Motor Control` to `Main Window & Menus`, `Load Cell Serial I/O`, `VESC Control Panel`, `CSV Data Recording`, `Connection Dialog`?**
  _High betweenness centrality (0.178) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `ServoPanel` (e.g. with `MainWindow` and `DataRecorder`) actually correct?**
  _`ServoPanel` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `VescController` (e.g. with `LoadCellSerial` and `Python Requirements`) actually correct?**
  _`VescController` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `MainWindow` (e.g. with `ConnectionDialog` and `LoadCellPanel`) actually correct?**
  _`MainWindow` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `LoadCellSerial` (e.g. with `ServoPanel` and `VescController`) actually correct?**
  _`LoadCellSerial` has 3 INFERRED edges - model-reasoned connections that need verification._