from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from config import APP_NAME
from ui.main_window import MainWindow


def _load_stylesheet() -> str:
    """Read the QSS stylesheet from the resources folder."""
    here = os.path.dirname(os.path.abspath(__file__))
    qss_path = os.path.join(here, "resources", "styles.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    stylesheet = _load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
