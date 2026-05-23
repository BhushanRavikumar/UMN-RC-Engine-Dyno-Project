"""Application entry point.

Run as::

    python -m src.main
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from .config import AppConfig
from .gui.main_window import MainWindow


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    _configure_logging()

    cfg = AppConfig.load()

    app = QApplication(sys.argv)
    app.setApplicationName("Motor Dyno")
    app.setOrganizationName("UMN")

    window = MainWindow(cfg)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
