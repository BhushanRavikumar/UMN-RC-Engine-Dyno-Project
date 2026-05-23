# Motor Dyno Control & Telemetry GUI

A PyQt6 desktop application for a small motor dynamometer. It

- Calibrates and reads **two HX711 load cells** through an Arduino over serial.
- Converts the measured force into **torque** using a user-supplied lever-arm length.
- Talks to a **VESC**-based motor controller to set RPM / current / brake / handbrake /
  position, full-brake and switch-off (release) the motor.
- Lets the user **drive the motor with the arrow keys** (up = speed up, down = slow down,
  left = reverse current bump, right = forward current bump, space = full brake,
  Esc = release).
- Shows **live RPM** as a big numeric counter and a high-refresh-rate scrolling plot.
- Draws an **animated motor graphic** whose rotor angle follows the real motor.

```
+---------------------------------------------------------------+
|  File  Connection  Calibration  Help                          |
+--------------------+------------------------------------------+
| Connections        |  Live RPM:  1234.5  rpm                  |
|  - Arduino (HX711) |  +------------------------------------+  |
|  - VESC            |  |        RPM vs time plot            |  |
|                    |  +------------------------------------+  |
| Load cells         |                                          |
|  Tare / Calibrate  |   +---------+   Voltage:    24.1 V       |
|  LC1: 12.3 N       |   | Motor   |   Current:     3.2 A       |
|  LC2: 11.9 N       |   | spinner |   Duty:       42.1 %       |
|  Lever arm: 0.10 m |   +---------+   Temp:       38.5 C       |
|  Torque:  1.21 Nm  |                                          |
|                    |   Control mode:  [ RPM | Current | ...]  |
|                    |   Setpoint: [    1500 ] [Apply]          |
|                    |   [FULL BRAKE]   [RELEASE]               |
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
│   └── gui/
│       ├── main_window.py
│       ├── loadcell_panel.py
│       ├── vesc_panel.py
│       ├── rpm_view.py
│       └── motor_graphic.py
├── requirements.txt
└── README.md
```

## Quick start

1. Flash `arduino/dual_hx711/dual_hx711.ino` to your Arduino. Wire the two HX711
   amplifiers to the pins defined at the top of that sketch.
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
   as `(F1 + F2) * L`.
8. Click anywhere on the **VESC panel** to give it keyboard focus, then drive
   with the arrow keys, or type setpoints into the spin boxes.

## Safety

- The arrow-key control sends a *current* command; releasing the key calls
  `set_current(0)` so the motor coasts. Press **Space** for an active full brake
  and **Esc** to release the motor completely.
- Calibration and lever arm are stored in `config.json` next to the executable.
- A watchdog thread re-sends the last command at 50 Hz so the VESC does not
  time out and stop the motor unexpectedly.

## Notes on libraries

- `pyvesc` provides the binary VESC packet format. We use the high-level
  `pyvesc.VESC` wrapper for control and telemetry.
- `pyqtgraph` is used instead of matplotlib because it can comfortably plot
  100+ Hz updates with thousands of points.
- All serial I/O happens in background threads. The GUI thread only consumes
  queued samples, so the UI stays smooth even when the link is busy.
