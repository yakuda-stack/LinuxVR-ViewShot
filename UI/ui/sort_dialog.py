"""
ui/sort_dialog.py – 🗂 Foto-Ordner sortieren: Frage + Ergebnis.

Beim ersten Start dieser Version einmal (nur wenn es etwas zu sortieren gibt),
danach nur noch über den Knopf in Optionen → Allgemein → Ordner & Dateien.
"""

import os

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from core import config, sort_folder
from core.i18n import tr


def ask_and_sort(parent, quiet_if_empty: bool = False) -> dict | None:
    """Fragen, dann sortieren. → Zählung oder None (abgebrochen / nichts zu tun)."""
    todo = [src for src, _dst in sort_folder.pending() if not src.name.startswith(".")]
    if not todo:
        if not quiet_if_empty:
            QMessageBox.information(parent, tr("sort_title"), tr("sort_nothing"))
        return None
    box = QMessageBox(parent)
    box.setWindowTitle(tr("sort_title"))
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(tr("sort_question", n=len(todo)))
    now = box.addButton(tr("sort_now"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(tr("sort_later"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(now)
    box.exec()
    if box.clickedButton() is not now:
        return None
    res = sort_folder.sort_now()
    text = tr("sort_done", p=res["pictures"], g=res["gif_vid"])
    if res["skipped"]:
        text += "\n" + tr("sort_skipped", n=res["skipped"])
    QMessageBox.information(parent, tr("sort_title"), text)
    return res


def maybe_ask(window) -> None:
    """Einmalig nach dem Start fragen – danach nie wieder von selbst."""
    if window.cfg.get("folder_sort_asked") or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    window.cfg["folder_sort_asked"] = True
    config.save(window.cfg)
    QTimer.singleShot(1200, lambda: ask_and_sort(window, quiet_if_empty=True))
