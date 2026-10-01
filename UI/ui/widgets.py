"""
ui/widgets.py – Kleine Bausteine, die mehrere Seiten benutzen.
"""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import QComboBox, QFrame, QLabel, QVBoxLayout

# Markierung für Überschrift-Zeilen in Dropdowns („── KI-Übersetzung ──“)
HEADER_ROLE = Qt.ItemDataRole.UserRole + 1


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


def add_header(combo: QComboBox, text: str) -> None:
    """Überschrift im Dropdown: nicht wählbar, nur zum Gliedern."""
    combo.addItem(f"──  {text}  ──")
    i = combo.count() - 1
    combo.setItemData(i, True, HEADER_ROLE)
    combo.setItemData(i, QColor("#5b8dc9"), Qt.ItemDataRole.ForegroundRole)  # blau = Überschrift
    item = combo.model().item(i)
    if item is not None:  # QStandardItemModel (Standard bei QComboBox)
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # nicht anklickbar, grau


def is_header(combo: QComboBox, index: int) -> bool:
    return bool(combo.itemData(index, HEADER_ROLE))


def fill_methods(combo: QComboBox, methods: list[str], tooltip=None) -> None:
    """Dienste ins Dropdown – gegliedert: erst normale Übersetzer, dann die KIs.
    tooltip(method) → Text beim Drüberfahren (optional)."""
    from core import translation
    from core.i18n import tr
    for title, group in translation.method_groups(methods):
        if not group:
            continue
        add_header(combo, tr(title))
        for m in group:
            combo.addItem(tr("tr_m_" + m), m)
            if tooltip is not None:
                combo.setItemData(combo.count() - 1, tooltip(m), Qt.ItemDataRole.ToolTipRole)


def select_data(combo: QComboBox, value) -> None:
    """Eintrag mit diesem Wert wählen – nie eine Überschrift (sonst der erste echte Eintrag)."""
    i = combo.findData(value)
    if i < 0 or is_header(combo, i):
        i = next((k for k in range(combo.count()) if not is_header(combo, k)), 0)
    combo.setCurrentIndex(i)


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pagetitle")
    return label


def open_path(path) -> None:
    """Öffnet Datei oder Ordner mit dem Standard-Programm (Dolphin, Gwenview …)."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
