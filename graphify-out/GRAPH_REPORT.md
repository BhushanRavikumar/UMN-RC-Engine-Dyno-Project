# Graph Report - UMN Final Project  (2026-06-18)

## Corpus Check
- 18 files · ~11,771 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 271 nodes · 533 edges · 14 communities (11 shown, 3 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 66 edges (avg confidence: 0.72)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `811c80c4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
1. `ServoPanel` - 34 edges
2. `MainWindow` - 31 edges
3. `VescController` - 30 edges
4. `LoadCellSerial` - 24 edges
5. `DataRecorder` - 23 edges
6. `VescPanel` - 22 edges
7. `LoadCellPanel` - 21 edges
8. `ViewerWindow` - 20 edges
9. `ConnectionPanel` - 17 edges
10. `RpmView` - 17 edges

## Surprising Connections (you probably didn't know these)
- `ScrollingPlot` --semantically_similar_to--> `ViewerWindow`  [INFERRED] [semantically similar]
  src/gui/plots.py → view_recordings.py
- `Python Requirements` --conceptually_related_to--> `VescController`  [INFERRED]
  requirements.txt → src/hardware/vesc_controller.py
- `load_csv()` --conceptually_related_to--> `Dyno Recording CSV Schema`  [INFERRED]
  view_recordings.py → src/data_recorder.py
- `DataRecorder` --shares_data_with--> `load_csv()`  [INFERRED]
  src/data_recorder.py → view_recordings.py
- `ViewerWindow` --references--> `DataRecorder`  [EXTRACTED]
  view_recordings.py → src/data_recorder.py

## Import Cycles
- None detected.

## Communities (14 total, 3 thin omitted)

### Community 0 - "VESC Motor Control"
Cohesion: 0.10
Nodes (12): GUI panel for driving the VESC.  Layout:  - A grid of telemetry read-outs (v, ControlMode, Background controller for a VESC-based motor controller.  This module wraps th, Thread-safe asynchronous wrapper around a VESC over UART/USB-CDC.      Signals, Atomically update the active setpoint.          Parameters         ----------, Apply maximum brake current (effectively a hard stop)., Stop driving the motor — it will coast., SetHandbrake (+4 more)

### Community 1 - "Live Plotting & Telemetry Views"
Cohesion: 0.12
Nodes (13): LiveCounter, Reusable live-data widgets.  Two pieces are exported:  - :class:`LiveCounter, Scrolling time-series plot backed by a numpy ring buffer.      The plot only r, Large numeric read-out for a single scalar signal., ScrollingPlot, Live RPM view: composite of a big numeric counter + scrolling plot.  The widge, Big RPM counter on top, scrolling RPM-vs-time plot below., RpmView (+5 more)

### Community 2 - "Servo Throttle Panel"
Cohesion: 0.14
Nodes (10): Dead-man Throttle Control, Linearly interpolate between the two calibrated angles., Command 0 % throttle (used on Space, disconnect and shutdown)., Original nudge-style arrow-key handling for calibration mode., Calibration + manual / keyboard throttle control for the servo., ServoPanel, QKeyEvent, QGroupBox (+2 more)

### Community 3 - "Load Cell Panel & Calibration"
Cohesion: 0.10
Nodes (19): Enum, _ChannelBox, LoadCellPanel, GUI panel for load-cell calibration and live force / torque display.  The pane, Top-level widget tying both channels together with a lever arm input., One per load cell: shows force, has Tare and Calibrate buttons., _Mode, GUI panel for the throttle servo.  The panel runs in one of two mutually exclu (+11 more)

### Community 4 - "Recording Viewer Tool"
Cohesion: 0.13
Nodes (15): Namespace, ndarray, load_csv(), main(), _mask_finite(), _parse_args(), Path, Interactive viewer for dyno CSV recordings.  The companion to :mod:`src.data_r (+7 more)

### Community 5 - "Main Window & Menus"
Cohesion: 0.13
Nodes (8): MainWindow, QMainWindow, AppConfig, Path, All persisted user settings., _configure_logging(), main(), Application entry point.  Run as::      python -m src.main

### Community 6 - "Load Cell Serial I/O"
Cohesion: 0.13
Nodes (8): _apply_cal(), LoadCellSerial, Replace the in-memory calibration objects atomically., Send a throttle-servo angle command to the Arduino.          The angle is clam, Convert a raw HX711 count to Newtons using a tare + slope model., Background reader for the dual-HX711 Arduino.      Signals     -------     s, QObject, LoadCellCalibration

### Community 7 - "VESC Control Panel"
Cohesion: 0.14
Nodes (8): One bordered cell: label + big value., Telemetry display and on-screen setpoint controls., _Readout, VescPanel, QFrame, AppConfig, VescTelemetry, VescController

### Community 8 - "CSV Data Recording"
Cohesion: 0.12
Nodes (10): Any, One snapshot of VESC measurements., Build a snapshot from whatever fields the running firmware exposes.          O, VescTelemetry, Dyno Recording CSV Schema, DataRecorder, VescTelemetry, CSV recorder for live RPM, torque and throttle data.  The recorder subscribes (+2 more)

### Community 9 - "Connection Dialog"
Cohesion: 0.12
Nodes (12): ConnectionChoice, ConnectionChoice, ConnectionPanel, Embedded panel for picking the serial ports for the Arduino and the VESC.  Thi, Update the small status line shown beneath the buttons., In-window controls to pick the two serial ports and connect.      Emits :pyatt, Main application window.  Composition:  - Left dock: connection controls on, Resize the window to fit the user's primary screen.          Picks the smaller (+4 more)

### Community 10 - "App Config & Entry Point"
Cohesion: 0.29
Nodes (6): Motor Dyno Control & Telemetry GUI, Notes on libraries, Project layout, Quick start, Safety, Viewing recordings

## Knowledge Gaps
- **18 isolated node(s):** `VescTelemetry`, `LoadCellCalibration`, `AppConfig`, `LoadCellSerial`, `LoadCellSample` (+13 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ServoPanel` connect `Servo Throttle Panel` to `Live Plotting & Telemetry Views`, `Load Cell Panel & Calibration`, `Main Window & Menus`, `Load Cell Serial I/O`, `CSV Data Recording`, `Connection Dialog`, `App Config & Entry Point`?**
  _High betweenness centrality (0.194) - this node is a cross-community bridge._
- **Why does `DataRecorder` connect `CSV Data Recording` to `Servo Throttle Panel`, `Load Cell Panel & Calibration`, `Recording Viewer Tool`, `Main Window & Menus`, `Load Cell Serial I/O`, `Connection Dialog`, `App Config & Entry Point`?**
  _High betweenness centrality (0.189) - this node is a cross-community bridge._
- **Why does `VescController` connect `VESC Motor Control` to `Main Window & Menus`, `Load Cell Serial I/O`, `VESC Control Panel`, `Connection Dialog`, `App Config & Entry Point`?**
  _High betweenness centrality (0.176) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `ServoPanel` (e.g. with `ConnectionChoice` and `MainWindow`) actually correct?**
  _`ServoPanel` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `MainWindow` (e.g. with `ConnectionChoice` and `ConnectionPanel`) actually correct?**
  _`MainWindow` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `VescController` (e.g. with `LoadCellSerial` and `Python Requirements`) actually correct?**
  _`VescController` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `LoadCellSerial` (e.g. with `ServoPanel` and `VescController`) actually correct?**
  _`LoadCellSerial` has 3 INFERRED edges - model-reasoned connections that need verification._