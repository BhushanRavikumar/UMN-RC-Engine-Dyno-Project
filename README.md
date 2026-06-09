# Motor Dyno Control & Telemetry GUI

A PyQt6 desktop application for a small motor dynamometer. It

- Calibrates and reads **two HX711 load cells** through an Arduino over serial.
- Converts the measured force into **torque** using a user-supplied lever-arm length.
- Drives a **throttle servo** on the same Arduino. The user calibrates the
  servo angles corresponding to 0 % and 100 % throttle, then sets the throttle
  either by typing a percentage or by nudging it with the arrow keys.
- Talks to a **VESC**-based motor controller to set RPM / current / brake / handbrake /
  position, full-brake and switch-off (release) the motor.
- Shows **live RPM and torque** as big numeric counters and high-refresh-rate
  scrolling plots.
- **Records RPM and torque to a CSV file** at a path the user chooses.

```
+---------------------------------------------------------------+
|  File  Connection  Record  Help                               |
+--------------------+------------------------------------------+
| Load cells & torque|  Live RPM:  1234.5  rpm                  |
|  Tare / Calibrate  |  +------------------------------------+  |
|  LC1: 12.3 N       |  |        RPM vs time plot            |  |
|  LC2: 11.9 N       |  +------------------------------------+  |
|  Lever arm: 0.10 m |  Live Torque:  1.21 N·m                  |
|  Torque:  1.21 Nm  |  +------------------------------------+  |
|--------------------|  |       Torque vs time plot          |  |
| Throttle servo     |  +------------------------------------+  |
|  Mode: Cal / Thr   |                                          |
|  Angle / Throttle  |                                          |
|--------------------|                                          |
| Motor control      |                                          |
|  Telemetry / mode  |                                          |
|  Setpoint [Apply]  |                                          |
|  [FULL BRAKE]      |                                          |
|  [RELEASE]         |                                          |
+--------------------+------------------------------------------+
```

## Project layout

```
.
├── arduino/
│   └── dual_hx711/dual_hx711.ino       # Arduino sketch
├── src/
│   ├── main.py                         # Entry point
│   ├── config.py                       # JSON-backed settings
│   ├── hardware/
│   │   ├── loadcell_serial.py          # Arduino HX711 link
│   │   └── vesc_controller.py          # VESC UART wrapper
│   ├── data_recorder.py                # RPM / torque / throttle CSV logger
│   └── gui/
│       ├── main_window.py
│       ├── loadcell_panel.py
│       ├── servo_panel.py                # Throttle-servo calibration + control
│       ├── vesc_panel.py
│       ├── rpm_view.py
│       └── torque_view.py
├── view_recordings.py                  # Standalone CSV recording viewer
├── Recordings/                         # Default folder the viewer scans
├── requirements.txt
└── README.md
```

## Quick start

1. Flash `arduino/dual_hx711/dual_hx711.ino` to your Arduino. Wire the two HX711
   amplifiers to the pins defined at the top of that sketch, and connect the
   throttle servo's signal pin to **D9** (powered from an external 5 V supply
   with its ground tied to the Arduino's ground). The sketch needs the
   bundled `Servo` library in addition to Bogdan Necula's `HX711` library.
2. Connect the VESC's UART to a USB-UART adapter (or use the VESC's built-in USB
   port).
3. Create a virtual environment and install the dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   The CRC dependency of `pyvesc` (`PyCRC`) was renamed on PyPI; if
   `pip` accidentally pulls `pycrc` instead of the legacy `PyCRC`, run:

   ```powershell
   pip uninstall -y pycrc
   pip install pythoncrc
   ```

4. Launch the GUI:

   ```powershell
   python -m src.main
   ```

5. From the **Connection** menu pick the serial ports for the Arduino and the VESC
   and click *Connect*.
6. From the **Calibration** panel, *Tare* each load cell with no load applied,
   then place a known mass on each cell and enter the reference value in kg.
   The slope (counts per Newton) is saved to `config.json`.
7. Enter the **lever-arm length** in meters. Torque is now computed continuously
   as `|F1 - F2| * L`.
8. In the **Throttle servo** panel, leave the *Calibration* radio selected and
   use the angle spin box or the arrow keys (`↑` / `→` and `↓` / `←`, hold
   `Shift` for a 5× step) to drive the servo. Click *Save as 0 % throttle*
   when the engine is at idle and *Save as 100 % throttle* when it is at wide
   open throttle. Both angles are written to `config.json`.
9. Switch the panel to *Throttle* mode. You have two ways to drive the
   throttle, and they share the same calibration:
   - **Type a percentage** (0–100 %) into the spin box.
   - **Hold the ↑ arrow** to command 100 % throttle for as long as it is
     held (dead-man style). Release ↑ and the throttle snaps back to 0 %
     immediately. Press ↓ (or `Space`, or the red button) to slam the
     throttle to 0 % instantly. Clicking outside the panel or switching
     back to *Calibration* also releases the hold.
10. In the **Motor control** panel (lower-left), pick a mode, type a setpoint
    into the spin box and click *Apply setpoint*. Use the *FULL BRAKE* and
    *RELEASE* buttons for the corresponding stop actions.
11. To log data, open the **Record** menu and choose *Start recording…* (Ctrl+R).
    Pick a `.csv` path; RPM, torque and throttle samples are appended live.
    Choose *Stop recording* (Ctrl+Shift+R) when done. Each row is
    `timestamp, elapsed_s, source, rpm, torque_nm, throttle_pct`, where
    `source` is one of `rpm`, `torque`, or `throttle` and marks which value
    is fresh on that row; the other columns carry the most recent reading
    of each signal.

## Viewing recordings

A standalone post-processing viewer lives in `view_recordings.py`. It scans
a folder for the CSVs produced by the live recorder and plots RPM, torque
and throttle on an interactive pyqtgraph canvas.

```powershell
# default: scan ./Recordings (latest file first)
python view_recordings.py

# or point at any folder
python view_recordings.py "C:\path\to\my\recordings"
```

The toolbar lets you:

- Pick which recording to display from a drop-down (newest first).
- *Browse folder…* to switch to a different directory.
- *Refresh* to re-scan after a new recording is dropped in.
- Toggle the **Layout**:
  - **Stacked** — three vertically aligned plots, one per channel, with
    their X axes linked so panning / zooming one pans all of them. Best
    when you want to read exact values per channel.
  - **Overlay** — a single plot with three independent Y axes (RPM on the
    left, torque and throttle on the right). The channels share an X axis
    but each keeps its native units, so signals at wildly different
    scales remain legible.

A crosshair follows the mouse on the plot canvas and the strip above the
plot shows the value of every channel at the cursor's time in the
channel's own colour. Standard pyqtgraph mouse interactions apply: scroll
to zoom, click-and-drag to pan, right-click for export / view-options.

## Safety

- The VESC is driven only by the on-screen *Apply setpoint*, *FULL BRAKE* and
  *RELEASE* buttons; that panel intentionally ignores keyboard input so a stray
  key press cannot move the motor.
- The throttle servo *does* respond to the arrow keys, but only when the
  *Throttle servo* panel has keyboard focus (click anywhere on it first). In
  *Throttle* mode the keys are configured as a **dead-man** control: holding
  `↑` commands 100 % throttle, and **releasing** it (or losing focus, or
  switching modes) immediately snaps the throttle back to 0 %. `↓`, `Space`,
  the red button, an Arduino disconnect or closing the application also
  command 0 % throttle.
- Servo calibration angles, load-cell calibration and lever arm are all stored
  in `config.json` next to the executable.
- A watchdog thread re-sends the last command at 50 Hz so the VESC does not
  time out and stop the motor unexpectedly.

## Notes on libraries

- `pyvesc` provides the binary VESC packet format. We use the high-level
  `pyvesc.VESC` wrapper for control and telemetry.
- `pyqtgraph` is used instead of matplotlib because it can comfortably plot
  100+ Hz updates with thousands of points.
- All serial I/O happens in background threads. The GUI thread only consumes
  queued samples, so the UI stays smooth even when the link is busy.
