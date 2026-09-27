"""
ui/widgets.py – Kleine Bausteine, die mehrere Seiten benutzen.
"""

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


def make_card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Eine Karte mit Überschrift. Gibt (Karte, Layout) zurück –
    in das Layout packst du dann deine Widgets."""
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setObjectName("cardtitle")
    layout.addWidget(heading)
    return card, layout


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pagetitle")
    return label


def open_path(path) -> None:
    """Öffnet Datei oder Ordner mit dem Standard-Programm (Dolphin, Gwenview …)."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
