"""Persistent JSON-backed application settings.

The config file lives next to the running script (``config.json``) so that
calibration data, lever-arm length and the most recently used serial ports
survive between runs.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class LoadCellCalibration:
    """Two-point linear calibration for a single load cell.

    The transfer function applied by the host is::

        force_newton = (raw_count - tare_offset) / counts_per_newton

    ``counts_per_newton`` defaults to 1.0 so that, before calibration, the
    GUI shows raw HX711 counts rather than silently reporting zero.
    """

    tare_offset: float = 0.0
    counts_per_newton: float = 1.0


@dataclass
class AppConfig:
    """All persisted user settings."""

    arduino_port: str = ""
    arduino_baud: int = 115_200
    vesc_port: str = ""
    vesc_baud: int = 115_200

    lever_arm_m: float = 0.10
    lc1: LoadCellCalibration = field(default_factory=LoadCellCalibration)
    lc2: LoadCellCalibration = field(default_factory=LoadCellCalibration)

    # Control limits used by the VESC panel.
    max_rpm: float = 10_000.0
    max_current_a: float = 30.0
    max_brake_current_a: float = 30.0
    arrow_current_step_a: float = 0.5

    # ------------------------------------------------------------------ I/O

    @classmethod
    def default_path(cls) -> Path:
        return Path(os.getcwd()) / "config.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        path = path or cls.default_path()
        if not path.exists():
            log.info("No config file at %s, using defaults", path)
            return cls()

        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Config %s could not be read (%s); using defaults", path, exc)
            return cls()

        cfg = cls()
        for key, value in data.items():
            if key in ("lc1", "lc2") and isinstance(value, dict):
                setattr(cfg, key, LoadCellCalibration(**value))
            elif hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or self.default_path()
        try:
            path.write_text(
                json.dumps(asdict(self), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            log.error("Could not save config to %s: %s", path, exc)
