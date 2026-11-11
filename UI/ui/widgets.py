"""
ui/widgets.py – Kleine Bausteine, die mehrere Seiten benutzen.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PyQt6.QtWidgets import QComboBox, QFrame, QLabel, QVBoxLayout

WARN_COLOR = "#e8a33d"  # 🟠 Layer veraltet (Desktop ❗, VR ⓘ)

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


def draw_play_badge(painter: QPainter, w: int, h: int):
    """🎬 Video: weißes ▶ in einem dunklen Kreis in der Mitte."""
    r = max(12, min(w, h) // 6)
    cx, cy = w // 2, h // 2
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 150))
    painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
    painter.setBrush(QColor("#ffffff"))
    s = r * 0.55
    painter.drawPolygon(QPolygonF([QPointF(cx - s * 0.6, cy - s), QPointF(cx - s * 0.6, cy + s), QPointF(cx + s, cy)]))


# Sprachen für die Knöpfe in Optionen → Allgemein: (Wert, Name in der eigenen Sprache)
LANGUAGES = (("de", "Deutsch"), ("en", "English"), ("fr", "Français"))


def flag_icon(code: str, w: int = 36, h: int = 24) -> QIcon:
    """Kleine Flagge selbst gemalt – Emoji-Flaggen zeigt Linux oft nur als Buchstaben.
    de = Deutschland, en = Vereinigtes Königreich, fr = Frankreich."""
    scale = 3  # scharf auf HiDPI
    pix = QPixmap(w * scale, h * scale)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(scale, scale)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), 3, 3)
    p.setClipPath(clip)
    p.setPen(Qt.PenStyle.NoPen)
    if code == "de":
        for i, color in enumerate(("#000000", "#dd0000", "#ffce00")):
            p.fillRect(QRectF(0, i * h / 3, w, h / 3 + 0.5), QColor(color))
    elif code == "fr":
        for i, color in enumerate(("#002395", "#ffffff", "#ed2939")):
            p.fillRect(QRectF(i * w / 3, 0, w / 3 + 0.5, h), QColor(color))
    else:  # Union Jack (vereinfacht)
        p.fillRect(QRectF(0, 0, w, h), QColor("#012169"))
        for color, width in (("#ffffff", h * 0.22), ("#c8102e", h * 0.08)):
            p.setPen(QPen(QColor(color), width))
            p.drawLine(QPointF(0, 0), QPointF(w, h))
            p.drawLine(QPointF(0, h), QPointF(w, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(QRectF(w / 2 - h * 0.18, 0, h * 0.36, h), QColor("#ffffff"))
        p.fillRect(QRectF(0, h / 2 - h * 0.18, w, h * 0.36), QColor("#ffffff"))
        p.fillRect(QRectF(w / 2 - h * 0.1, 0, h * 0.2, h), QColor("#c8102e"))
        p.fillRect(QRectF(0, h / 2 - h * 0.1, w, h * 0.2), QColor("#c8102e"))
    p.end()
    pix.setDevicePixelRatio(scale)
    return QIcon(pix)
