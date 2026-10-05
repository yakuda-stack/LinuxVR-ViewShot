"""
ui/welcome.py – 👋 Willkommen beim ersten Start (drei kurze Fenster nacheinander):

  1. Diese App ist nur zum Einstellen und Installieren – danach kannst du sie
     schließen und alles in VR machen.                         [Weiter]
  2. Gleich installieren, damit in VR alles geht.   [Jetzt installieren] [Später]
     (fällt weg, wenn schon installiert)
  3. Bitte richte deine Übersetzer ein.             [OK] → Optionen → Übersetzung

Danach steht in ui.json "welcome_done": true – es kommt nie wieder.
"""

import os

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from core import config, layer_install, paths
from core.i18n import tr

TRANSLATION_TAB = 3  # Optionen: General · Shot · VR · Übersetzung


def needs_install() -> bool:
    if not paths.layer_installed():
        return True
    return paths.copies_layer() and layer_install.needs_update()


def ask(window, title: str, text: str, buttons: list[str]) -> int:
    """Fenster mit Text und Knöpfen → Nummer des gedrückten Knopfs (Schließen = letzter)."""
    box = QMessageBox(window)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Information)
    box.setStyleSheet("QLabel { min-width: 460px; }")  # gut lesbar, auch in VR (WayVR)
    added = [box.addButton(b, QMessageBox.ButtonRole.AcceptRole) for b in buttons]
    box.setDefaultButton(added[0])
    box.exec()
    clicked = box.clickedButton()
    return added.index(clicked) if clicked in added else len(added) - 1


def run(window) -> None:
    """Alle Schritte nacheinander (window = MainWindow)."""
    ask(window, tr("welcome_title"), tr("welcome_1"), [tr("welcome_next")])
    if needs_install():
        if ask(window, tr("welcome_title"), tr("welcome_2"), [tr("welcome_install_now"), tr("welcome_later")]) == 0:
            window.switch_page(0)              # Main-Seite: dort sieht man den Fortschritt
            window.main_page.run_install()
    ask(window, tr("welcome_title"), tr("welcome_3"), [tr("ok")])
    window.cfg["welcome_done"] = True
    config.save(window.cfg)
    window.switch_page(2)                      # Optionen …
    window.options_page.show_tab(TRANSLATION_TAB)  # … → Übersetzung


def maybe_start(window) -> None:
    """Beim ersten Start (und nicht in Tests ohne Bildschirm) kurz nach dem Fenster zeigen."""
    if window.cfg.get("welcome_done") or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    QTimer.singleShot(400, lambda: run(window))
