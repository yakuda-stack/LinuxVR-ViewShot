#!/usr/bin/env python3
"""Smoke-Test: baut das komplette Fenster ohne Bildschirm, wechselt alle
Seiten/Tabs einmal durch und beendet sich. Exit 0 = alles startet.

    python3 tests/smoke.py
"""
import os
import sys
import tempfile
from pathlib import Path

tmp = tempfile.mkdtemp(prefix="viewshot-smoke-")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["XDG_CONFIG_HOME"] = tmp          # echte Einstellungen nicht anfassen
os.environ["VIEWSHOT_OUTPUT_DIR"] = str(Path(tmp) / "photos")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "UI"))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from ui import nowheel  # noqa: E402
from ui.mainwindow import MainWindow  # noqa: E402

nowheel.install(app)
w = MainWindow()
w.show()
for page in range(w.pages.count()):
    w.switch_page(page)
    app.processEvents()
for tab in range(len(w.options_page.tab_pages)):
    w.options_page.show_tab(tab)
    app.processEvents()

# Beenden wie im echten Betrieb: über app.exec() → aboutToQuit.
# Nur so wird der Mausrad-Filter (ui/nowheel.py) wieder entfernt – ein
# App-weiter Filter, der beim Beenden noch hängt, lässt Python mit
# Signal 11 (SIGSEGV) abstürzen. Der Test prüft diesen Weg also mit.
QTimer.singleShot(0, w.close)
QTimer.singleShot(0, app.quit)
code = app.exec()
print("✔ Smoke-Test: Fenster, alle Seiten und Tabs bauen sich ohne Fehler auf")
sys.exit(code)
