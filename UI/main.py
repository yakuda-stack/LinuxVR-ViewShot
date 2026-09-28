#!/usr/bin/env python3
"""
LinuxVR-ViewShot – Desktop-UI

Start:  python3 starter.py  (setzt den Prozessnamen)
   oder python3 main.py / ./start.sh
"""

import logging
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from core import paths
from ui import nowheel
from ui.mainwindow import MainWindow


def setup_log():
    """ui.log: was die App wann macht (Texterkennung, Übersetzung) – für Fehlersuche."""
    try:
        paths.UI_LOG.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=paths.UI_LOG, filemode="w", level=logging.INFO,
                            format="%(asctime)s %(threadName)s %(message)s")
    except OSError:
        pass


def run_app():
    setup_log()
    app = QApplication(sys.argv)
    app.setApplicationName("LinuxVR-ViewShot")
    # Taskleiste: Wayland ordnet das Fenster über diese ID der .desktop-Datei zu
    # (Icon + Name), unter X11 hilft zusätzlich das Fenster-Icon
    app.setDesktopFileName(paths.DESKTOP_ID)
    app.setWindowIcon(QIcon(str(paths.APP_ICON)))
    # Mausrad über Dropdowns/Slidern scrollt die Seite statt den Wert zu ändern
    # (1:1 aus OSC-DreamChatbox, siehe ui/nowheel.py)
    nowheel.install(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
