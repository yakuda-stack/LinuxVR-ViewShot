"""
ui/vr_panel.py – 🪟 Übersetzungs-Panel für VR.

Ein ganz normales Qt-Fenster – nur unsichtbar. Die App speichert es als Bild
(<Foto-Ordner>/panel/panel.png), der Layer zeigt es in VR an: an der linken/rechten
Hand, am Kopf oder in der Welt (Optionen → Shot).

Klicks: Der Layer schickt „click <u> <v>“ (0..1) per UDP an 127.0.0.1:<panel_port>.
Hier wird daraus ein echter Maus-Klick ins unsichtbare Fenster – so funktionieren
alle Knöpfe, ohne sie in Rust nachzubauen.

Inhalt: Foto mit Nummern ①②③ auf den Textzeilen · darunter die Übersetzungen
1, 2, 3 (lang → ▼ / ▲ blättern) · Dienst (+ Modus 🤖/✋) / Aufgabe / Von → Nach
(Auswahl als Liste im Panel, keine Dropdowns – deren Klapplisten wären eigene
Fenster und nicht im Bild) · ↻ · ⚙ springt auf die Einstellungs-Seite.

Seiten: 🌐 Übersetzung, 🖼 Galerie und ⚙ Einstellungen – Tabs ganz unten wechseln die Seite.
Jede Seite hat ihre eigene Größe in VR (panel_sizes.json) – die Galerie ist standardmäßig größer.
🌐 Übersetzung: links Foto + Übersetzung, rechts ein Seitenpanel (Dienst, Sprachen, Aufgabe),
mit › einklappbar (dann nur „Einstellungen“ senkrecht, layer.json „panel_side_closed“).
⚙ Einstellungen: links Kategorien (📸 Shot / 🥽 VR), rechts das Untermenü der gewählten –
was drinsteht, kommt aus core/vr_settings.py (gleiche Liste nutzt der Rust-Dienst).
Galerie = Raster mit Vorschaubildern über die
ganze Fläche, Monats-Trenner („── 2026 Oktober ──“); Antippen öffnet das Foto groß mit
📋 Kopieren · ☁ Hochladen + Link · ↗ Teilen · 🌐 Übersetzen · ⓘ Info · 🗑 Löschen.
"""

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QIcon, QImage, QImageReader, QMouseEvent, QMovie, QPainter,
                         QPixmap, QTextLayout)
from PyQt6.QtNetwork import QHostAddress, QUdpSocket
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                             QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from core import (clipboard, config, layer_config, layer_install, overlay, paths, share, tags, translation, uploader,
                  vr_settings)
from core.version import VERSION
from core import llm_translator as llm
from core.i18n import month_title, tr
from ui.style import STYLE
from ui.widgets import WARN_COLOR, draw_play_badge

WIDE = 1000              # Pixel-Breite des Panel-Bilds, alle Seiten (Höhe ergibt sich aus dem Inhalt)
SIDE_W = 300             # 🌐 Seitenpanel rechts (offen)
STRIP_W = 64             # 🌐 Seitenpanel eingeklappt: nur „Einstellungen“ senkrecht
COL_GAP = 14             # Abstand zwischen zwei Spalten
CAT_W = 360              # ⚙ Kategorien-Liste links
PHOTO_MAX_H = 360        # so hoch darf das Foto im Panel höchstens werden
CHECK_MS = 400           # so oft schauen, ob sich etwas geändert hat
RESULT_MAX_H = 300       # Übersetzung höher → blättern (▼ / ▲)
SIZE_CM = (15, 80)       # Panel-Breite in VR (Schieber „Größe“)
BUTTON_CM = (2, 20)      # 🔘 Knopf-Durchmesser in VR (Schieber „Knopf-Größe“)
# 🔘 Knopf-Farben zum Antippen in VR (passend zu Hand-Overlays wie WayVR)
BUTTON_COLORS = ("#5b8dc9", "#9b6bd6", "#4caf7a", "#e0913a", "#d05a5a", "#6b7280", "#e5e9ef")
NAV_H = 52               # Zeile ganz unten: ◀ links, ▶ rechts (Seite wechseln)
GRID_COLS = 4            # Galerie: Vorschaubilder nebeneinander (Standard)
GALLERY_COLS = (3, 4, 5) # 🖼 zur Auswahl im Seitenpanel (layer.json „gallery_cols“)
GRID_GAP = 8
THUMB_RATIO = 0.75       # Höhe/Breite einer Kachel
MONTH_H = 34             # Höhe eines Monats-Trenners im Raster
GALLERY_H = 760          # Galerie ohne von Hand gezogene Höhe: so hoch wird das Panel
SINGLE_MAX_H = 360       # Einzelansicht: so hoch darf das Foto höchstens werden
GIF_MIN_FRAME_S = 0.125  # 🎞 GIF in VR: höchstens so oft ein neues Panel-Bild (der Layer schaut alle 80 ms)
PAGES = ("translate", "gallery", "settings")
PAGE_SIZE_DEFAULT = {"translate": 0.44, "gallery": 0.62, "settings": 0.56}  # Breite in VR (m) je Seite
PAGE_WIDTH = {"translate": WIDE, "gallery": WIDE, "settings": WIDE}  # Pixel-Breite je Seite
PAGE_ICONS = {"translate": "🌐", "gallery": "🖼", "settings": "⚙"}
# Stapel-Seiten im Panel
PAGE_MAIN, PAGE_PICK, PAGE_SETTINGS, PAGE_GALLERY, PAGE_SINGLE, PAGE_SHARE, PAGE_INFO = range(7)
NAV_PAGES = (PAGE_MAIN, PAGE_GALLERY, PAGE_SETTINGS)  # nur hier ist die Tab-Leiste unten zu sehen
BADGE = QColor(70, 150, 255)
NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def panel_file() -> Path:
    return paths.photo_dir() / "panel" / "panel.png"


def pose_file() -> Path:
    return paths.CONFIG_DIR / "panel_pose.json"


def panel_open() -> bool:
    """🔘 Ist das Panel in VR aufgeklappt? (panel_state.json schreibt der Layer; fehlt = ja)"""
    try:
        return bool(json.loads((paths.CONFIG_DIR / "panel_state.json").read_text()).get("open", True))
    except (OSError, ValueError, AttributeError):
        return True


def number(i: int) -> str:
    return NUMBERS[i] if i < len(NUMBERS) else f"({i + 1})"


def enabled() -> bool:
    return bool(layer_config.load().get("panel", True))


def side_closed() -> bool:
    """🌐 Seitenpanel rechts eingeklappt? (layer.json – gilt auch für den ⚙ Dienst)"""
    return bool(layer_config.load().get("panel_side_closed"))


def gallery_cols() -> int:
    """🖼 Spalten im Raster (layer.json „gallery_cols“) – nur 3 / 4 / 5, sonst 4."""
    try:
        cols = round(float(layer_config.load().get("gallery_cols") or GRID_COLS))
    except (TypeError, ValueError):
        cols = GRID_COLS
    return cols if cols in GALLERY_COLS else GRID_COLS


def main_w(closed: bool) -> int:
    """Linke Spalte neben dem Seitenpanel (🌐 Foto, 🖼 Raster)."""
    return WIDE - 36 - COL_GAP - (STRIP_W if closed else SIDE_W)


def fixed_height_px(page: str = "translate") -> int | None:
    """Höhe von Hand gezogen (Ecke oben links in VR)? → Pixel-Höhe passend dazu (bei der Breite der Seite)."""
    try:
        data = json.loads(pose_file().read_text(encoding="utf-8"))
        width, height = float(data["width"]), data.get("height")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not height or width <= 0:
        return None
    return max(160, round(PAGE_WIDTH.get(page, WIDE) * float(height) / width))


def opacity() -> float:
    try:
        return max(30, min(100, float(layer_config.load().get("panel_opacity", 100)))) / 100
    except (TypeError, ValueError):
        return 1.0


def width_cm() -> int | None:
    """Breite des Panels in VR (cm) – steht in panel_pose.json (legt der Layer an)."""
    try:
        return round(float(json.loads(pose_file().read_text(encoding="utf-8"))["width"]) * 100)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def set_width_cm(cm: int) -> bool:
    """Größe ändern: Breite (und eine von Hand gezogene Höhe im selben Verhältnis).
    Der Layer liest die Datei neu, sobald sie sich ändert."""
    try:
        data = json.loads(pose_file().read_text(encoding="utf-8"))
        old = float(data["width"])
    except (OSError, ValueError, KeyError, TypeError):
        return False  # noch nie in VR gezeigt → Layer legt die Datei erst an
    new = max(SIZE_CM[0], min(SIZE_CM[1], cm)) / 100
    data["width"] = new
    if data.get("height"):
        data["height"] = float(data["height"]) * new / old
    tmp = pose_file().with_suffix(".ui-tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, pose_file())
    return True


def sizes_file() -> Path:
    """Größe je Seite + aktuelle Seite – gilt für App UND ⚙ Dienst (daemon/src/panel.rs)."""
    return paths.CONFIG_DIR / "panel_sizes.json"


def load_sizes() -> dict:
    try:
        data = json.loads(sizes_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def current_page() -> str:
    """Welche Seite zuletzt offen war (App und Dienst machen dort weiter)."""
    page = load_sizes().get("page")
    return page if page in PAGES else PAGES[0]


def switch_page_size(old: str, new: str) -> None:
    """Seite wechseln: Größe der alten Seite merken, die der neuen in panel_pose.json
    schreiben (der Layer liest sie sofort). Galerie standardmäßig größer.
    Gibt es panel_pose.json noch nicht (nie in VR gezeigt), wird nur die Seite gemerkt."""
    sizes = load_sizes()
    sizes["page"] = new
    try:
        pose = json.loads(pose_file().read_text(encoding="utf-8"))
        width = float(pose["width"])
    except (OSError, ValueError, KeyError, TypeError):
        pose = None
    if pose is not None and old != new:
        sizes[old] = {"width": width, "height": pose.get("height")}
        target = sizes.get(new)
        if not isinstance(target, dict) or not target.get("width"):
            target = {"width": PAGE_SIZE_DEFAULT[new], "height": None}
        pose["width"] = max(SIZE_CM[0] / 100, min(SIZE_CM[1] / 100, float(target["width"])))
        if target.get("height"):
            pose["height"] = float(target["height"])
        else:
            pose.pop("height", None)  # Höhe automatisch (so hoch wie der Inhalt)
        tmp = pose_file().with_suffix(".ui-tmp")
        tmp.write_text(json.dumps(pose, indent=2), encoding="utf-8")
        os.replace(tmp, pose_file())
    try:
        sizes_file().parent.mkdir(parents=True, exist_ok=True)
        sizes_file().write_text(json.dumps(sizes, indent=2), encoding="utf-8")
    except OSError:
        pass


def page_width_cm(page: str) -> int | None:
    """Breite einer Seite in VR (cm): die offene aus panel_pose.json, die anderen aus
    panel_sizes.json (oder Standard). None = Panel war noch nie in VR zu sehen."""
    now = width_cm()
    if page == current_page() or now is None:
        return now
    entry = load_sizes().get(page)
    width = entry.get("width") if isinstance(entry, dict) else None
    return round(float(width or PAGE_SIZE_DEFAULT[page]) * 100)


def set_page_width_cm(page: str, cm: int) -> bool:
    """Größe einer Seite ändern – die offene sofort in VR, die anderen beim nächsten Wechsel."""
    if page == current_page():
        return set_width_cm(cm)
    if width_cm() is None:
        return False
    sizes = load_sizes()
    entry = sizes.get(page) if isinstance(sizes.get(page), dict) else {}
    old = float(entry.get("width") or PAGE_SIZE_DEFAULT[page])
    new = max(SIZE_CM[0], min(SIZE_CM[1], cm)) / 100
    height = entry.get("height")
    sizes[page] = {"width": new, "height": float(height) * new / old if height else None}
    try:
        sizes_file().write_text(json.dumps(sizes, indent=2), encoding="utf-8")
    except OSError:
        return False
    return True


def clear_layout(lay) -> None:
    """Alles aus einem Layout entfernen (Widgets verschwinden sofort, gelöscht wird später)."""
    while lay.count():
        item = lay.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


def vertical_pixmap(text: str) -> QPixmap:
    """🌐 eingeklapptes Seitenpanel: ‹ oben, darunter der Text senkrecht (von unten nach oben lesbar)."""
    font = QFont()
    font.setPixelSize(22)
    font.setBold(True)
    fm = QFontMetrics(font)
    tw, th = fm.horizontalAdvance(text), fm.height()
    arrow_h = 40
    pix = QPixmap(th + 4, tw + arrow_h + 8)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(QColor("#5b9bff"))
    big = QFont(font)
    big.setPixelSize(26)
    painter.setFont(big)
    painter.drawText(QRectF(0, 0, pix.width(), arrow_h), Qt.AlignmentFlag.AlignCenter, "‹")
    painter.setFont(font)
    painter.translate(pix.width() / 2 + fm.ascent() / 2 - 2, arrow_h + tw + 4)
    painter.rotate(-90)
    painter.drawText(0, 0, text)
    painter.end()
    return pix


def elide(text: str, width: int, px: int = 20) -> str:
    """Knopf-Text zu lang fürs schmale Seitenpanel → hinten mit … kürzen."""
    font = QFont()
    font.setPixelSize(px)
    font.setBold(True)
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, width)


def wrap_lines(text: str, font: QFont, width: int) -> list[str]:
    """Text so umbrechen, wie das Label es tut → einzelne Zeilen (zum Blättern)."""
    lines = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        layout = QTextLayout(para, font)
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            lines.append(para[line.textStart():line.textStart() + line.textLength()].rstrip())
        layout.endLayout()
    return lines


def paginate(lines: list[str], per_page: int) -> list[str]:
    """Zeilen → Seiten (jede Seite ein Text). Leere Zeilen am Seitenanfang fallen weg."""
    per_page = max(1, per_page)
    pages, cur = [], []
    for line in lines:
        if not cur and not line.strip() and pages:
            continue
        cur.append(line)
        if len(cur) >= per_page:
            pages.append("\n".join(cur))
            cur = []
    if cur or not pages:
        pages.append("\n".join(cur))
    return pages


class ClickBar(QWidget):
    """Schieber für den VR-Laser: Klick irgendwo auf die Leiste = dieser Wert
    (ein normaler QSlider springt bei Klick nur ein Stück)."""

    def __init__(self, lo: int, hi: int, on_change):
        super().__init__()
        self.lo, self.hi, self.value, self.on_change = lo, hi, lo, on_change
        self.setFixedHeight(48)

    def set_value(self, v: int):
        self.value = max(self.lo, min(self.hi, v))
        self.update()

    def paintEvent(self, _ev):  # noqa: N802 – Qt-Name
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad, h = 20, self.height()
        w = self.width() - 2 * pad
        frac = (self.value - self.lo) / max(1, self.hi - self.lo)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2c313c"))
        p.drawRoundedRect(QRectF(pad, h / 2 - 5, w, 10), 5, 5)
        p.setBrush(QColor("#5b8dc9"))
        p.drawRoundedRect(QRectF(pad, h / 2 - 5, w * frac, 10), 5, 5)
        p.setBrush(QColor("#e8ecf2"))
        p.drawEllipse(QPointF(pad + w * frac, h / 2), 14, 14)
        p.end()

    def mousePressEvent(self, ev):  # noqa: N802 – Qt-Name
        pad = 20
        frac = (ev.position().x() - pad) / max(1, self.width() - 2 * pad)
        self.set_value(round(self.lo + max(0.0, min(1.0, frac)) * (self.hi - self.lo)))
        self.on_change(self.value)


def button_file() -> Path:
    """🔘 Position/Größe des Knopfs (legt der Layer an, wie panel_pose.json)."""
    return paths.CONFIG_DIR / "button_pose.json"


def button_cm() -> int | None:
    try:
        return round(float(json.loads(button_file().read_text(encoding="utf-8"))["width"]) * 100)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def set_button_cm(cm: int) -> bool:
    """Knopf-Größe ändern (Durchmesser). False = Knopf war noch nie in VR zu sehen."""
    try:
        data = json.loads(button_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    data["width"] = max(BUTTON_CM[0], min(BUTTON_CM[1], cm)) / 100
    tmp = button_file().with_suffix(".ui-tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, button_file())
    return True


def reset_position() -> None:
    """⟲ Knopf zurück ans Handgelenk (bzw. Standard-Platz), Panel wieder darüber
    (ohne Knopf: 55 cm vor dem Kopf) – der Layer legt beide Dateien neu an."""
    for f in (pose_file(), button_file()):
        try:
            f.unlink()
        except OSError:
            pass


def photo_with_numbers(photo: Path | None, lines: list[dict], width: int) -> QPixmap | None:
    """Foto (verkleinert) mit blauen Nummern ①②③ auf den erkannten Textzeilen."""
    if photo is None or not photo.is_file():
        return None
    img = QImage(str(photo))
    if img.isNull():
        return None
    scale = min(width / img.width(), PHOTO_MAX_H / img.height())
    pix = QPixmap.fromImage(img.scaled(round(img.width() * scale), round(img.height() * scale),
                                       Qt.AspectRatioMode.IgnoreAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
    boxes = [line["box"] for line in lines if line.get("box")]
    if not boxes:
        return pix
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    size = max(18.0, min(30.0, pix.height() / 10))
    font = QFont()
    font.setBold(True)
    font.setPixelSize(round(size * 0.62))
    p.setFont(font)
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        # dünner Rahmen um die Zeile + Nummer links davor
        p.setPen(QColor(70, 150, 255, 200))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x0 * scale, y0 * scale, (x1 - x0) * scale, (y1 - y0) * scale))
        cx = max(size / 2, x0 * scale - size * 0.6)  # links neben die Zeile
        cy = (y0 + y1) / 2 * scale
        circle = QRectF(cx - size / 2, cy - size / 2, size, size)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BADGE)
        p.drawEllipse(circle)
        p.setPen(QColor("white"))
        p.drawText(circle, int(Qt.AlignmentFlag.AlignCenter), str(i + 1))
    p.end()
    return pix


class VRPanel(QWidget):
    """Unsichtbares Fenster → panel.png. `page` = MainPage (Übersetzung, Einstellungen)."""
    upload_finished = pyqtSignal(str, object, str)  # (Foto, Links oder None, Fehler)

    def __init__(self, page):
        # Eltern = Seite: verschwindet mit ihr und hält die App beim Beenden nicht auf
        super().__init__(page, Qt.WindowType.Tool)
        self.page = page
        self.setObjectName("vrpanel")
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)  # nie auf dem Desktop
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE + """
            #vrpanel { background: #07090d; border: 2px solid #1d2a40; border-top: 4px solid #3d7fd9;
                       border-radius: 16px; }
            #vrpanel QStackedWidget, #vrpanel QStackedWidget > QWidget { background: #07090d; }
            #vrpanel QPushButton { font-size: 20px; min-height: 48px; padding: 4px 14px; }
            #vrpanel QPushButton#linkbtn { background: #121a28; color: #e8ecf4; border: 1px solid #24324a;
                                           border-bottom: 2px solid #3d7fd9; border-radius: 6px; }
            #vrpanel QPushButton#sendbtn { background: #1f3a66; color: #ffffff; border: 1px solid #5b9bff;
                                           border-bottom: 2px solid #5b9bff; border-radius: 6px; }
            #vrpanel QLabel { font-size: 20px; color: #e8ecf4; }
            #vrpanel QLabel#vrtitle { font-size: 26px; font-weight: bold; color: #5b9bff; }
            #vrpanel QLabel#vrsubtitle { font-size: 22px; font-weight: bold; color: #5b9bff; }
            #vrpanel QFrame#vrphotobox { background: #0f141d; border: 1px solid #24324a; border-radius: 8px; }
            #vrpanel QFrame#vrresultbox { background: #0f141d; border: 1px solid #24324a;
                                          border-bottom: 3px solid #3d7fd9; border-radius: 8px; }
            #vrpanel QLabel#vrresult { font-size: 22px; background: transparent; border: none; }
            #vrpanel QFrame#vrresultbox QLabel#dim { background: transparent; border: none; }
            #vrpanel QLabel#vrsection { font-size: 17px; color: #aeb4bf; }
            #vrpanel QPushButton#cathead { font-size: 18px; font-weight: bold; color: #aeb4bf; background: transparent;
                                           border: none; text-align: left; padding: 0 6px; min-height: 40px;
                                           max-height: 40px; }
            #vrpanel QLabel#dim { font-size: 16px; color: #9aa6ba; }
            #vrpanel QFrame#vrcard { background: #0f141d; border: 1px solid #1d2a40; border-top: 3px solid #3d7fd9;
                                     border-radius: 10px; }
            #vrpanel QPushButton#cat, #vrpanel QPushButton#catOn {
                text-align: left; padding: 0 14px; min-height: 52px; max-height: 52px; border-radius: 6px;
                font-weight: bold; background: #121a28; color: #e8ecf4; border: 1px solid #24324a;
                border-bottom: 2px solid #3d7fd9; }
            #vrpanel QPushButton#catOn { background: #16233a; color: #8fb6ff; border-bottom-color: #5b9bff; }
            #vrpanel QLabel#catarrow { font-size: 26px; font-weight: bold; color: #5b9bff; background: transparent; }
            #vrpanel QPushButton#tab, #vrpanel QPushButton#tabOn {
                font-size: 20px; font-weight: bold; min-height: 52px; max-height: 52px; border-radius: 8px;
                background: #121a28; color: #c9d3e3; border: 1px solid #24324a; border-top: 3px solid #2c3d5c; }
            #vrpanel QPushButton#tabOn { background: #16233a; color: #8fb6ff; border-top-color: #5b9bff; }
            #vrpanel QPushButton#strip { background: #0f141d; border: 1px solid #1d2a40; border-top: 3px solid #3d7fd9;
                                         border-radius: 10px; padding: 0; }
            #vrpanel QPushButton#linkbtn:disabled { color: #3a4560; border-color: #1a2436; background: #0d121b; }
            #vrpanel QLabel#month { font-size: 18px; font-weight: bold; color: #c7cdd6; }
            #vrpanel QFrame#monthline { background: #24324a; }
            #vrpanel QLabel#vrtoast { font-size: 18px; font-weight: bold; color: #6fae72; }
            #vrpanel QLabel#infokey { font-size: 17px; color: #aeb4bf; }
            #vrpanel QLabel#infoval { font-size: 19px; }
            #vrpanel QPushButton#thumb { padding: 0; min-height: 0; border: 2px solid #24324a;
                                         border-radius: 8px; background: #0f141d; }
            #vrpanel QListWidget { font-size: 22px; }
            #vrpanel QListWidget::item { min-height: 54px; }
        """)
        self.setFixedWidth(PAGE_WIDTH.get(current_page(), WIDE))
        self.last_sig = None
        self.choosing = None     # welches Auswahl-Menü ist offen ("tr_method", …)
        self.result_full = ""    # ganze Übersetzung …
        self.result_page = 0     # … angezeigte Seite (▼ / ▲)
        self.mode = current_page()  # Hauptseite: "translate" / "gallery" / "settings" (wie zuletzt)
        self.set_tab = vr_settings.TABS[0]["id"]  # ⚙ Einstellungen: Tab "shot" / "vr"
        self.set_open = None     # ⚙ gewählte Kategorie (rechts offen) oder None = die erste
        self.set_folded = set()  # ⚙ eingeklappte Überschriften links ("shot" / "vr")
        self.size_page = "translate"  # 🪟 Größe: für welche Seite
        self.old_open = False    # 🟠 Hinweis „Layer veraltet“ aufgeklappt?
        self.gal_page = 0        # Galerie: Seite im Raster
        self.gal_filter = ""     # Galerie-Filter: "" = alle, "text" / "qr" / "image" / "gif_vid"
        self.gal_open = None     # Galerie: Foto in der Einzelansicht (Path) oder None
        self.gal_confirm = False  # 🗑 einmal angetippt → „Wirklich löschen?“
        self.gal_toast = ""      # Rückmeldung in der Einzelansicht („✔ Link kopiert“)
        self.gif_movie = None    # 🎞 GIF groß in der VR-Galerie: läuft als Animation
        self.gif_path = None
        self.gif_written = 0.0   # wann zuletzt ein GIF-Bild ins Panel ging
        self.gal_pages_cache = []  # Raster-Seiten: [[("month", text) | ("row", [Fotos])]]
        self.uploading = set()
        self.thumbs = {}         # (Pfad, Änderungszeit, Breite) → Vorschaubild
        self.upload_finished.connect(self.on_upload_finished)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)  # nimmt den Platz → ◀ ▶ bleiben ganz unten
        # ganz unten: Tab-Leiste [🌐 Übersetzung] [🖼 Galerie] [⚙ Einstellungen] – offene Seite blau
        self.nav = QWidget()
        nrow = QHBoxLayout(self.nav)
        nrow.setContentsMargins(0, 0, 0, 0)
        nrow.setSpacing(8)
        self.nav_tabs = {}
        for name in PAGES:
            btn = self.button(PAGE_ICONS[name] + "  " + self.page_name(name), lambda n=name: self.go_page(n))
            btn.setObjectName("tab")
            nrow.addWidget(btn, 1)
            self.nav_tabs[name] = btn
        lay.addWidget(self.nav)
        # Höhe richtet sich nur nach der sichtbaren Seite
        self.stack.currentChanged.connect(self.shrink_to_page)

        # ---------- Seite 0: Übersetzung (links Foto + Übersetzung, rechts Seitenpanel) ----------
        main = QWidget()
        mrow = QHBoxLayout(main)
        mrow.setContentsMargins(0, 0, 0, 0)
        mrow.setSpacing(COL_GAP)
        self.main_left = QWidget()
        col = QVBoxLayout(self.main_left)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        mrow.addWidget(self.main_left, 1, Qt.AlignmentFlag.AlignTop)
        head = QHBoxLayout()
        title = QLabel("🌐  " + tr("vr_page_translate"))
        title.setObjectName("vrtitle")
        head.addWidget(title, 1)
        # 🟠 i: Layer passt nicht zur App → antippen klappt den Hinweis auf
        self.old_btn = self.button("i", self.toggle_old_note)
        self.old_btn.setFixedWidth(48)
        self.old_btn.setStyleSheet(f"background: {WARN_COLOR}; color: #161a22; border: none; "
                                   "border-radius: 24px; font-weight: bold; font-size: 24px; padding: 0;")
        head.addWidget(self.old_btn)
        # 🖼 ▲ = Foto ausblenden (Übersetzung bekommt die ganze Fläche), 🖼 ▼ = wieder zeigen
        self.pic_btn = self.button("", self.toggle_photo)
        self.pic_btn.setFixedWidth(84)
        self.pic_btn.setStyleSheet("padding: 0;")
        head.addWidget(self.pic_btn)
        # 🎞 GIF / 🎬 VID umschalten (wie auf der Main-Seite)
        self.rec_btn = self.button("", self.toggle_rec)
        self.rec_btn.setMinimumWidth(120)
        head.addWidget(self.rec_btn)
        col.addLayout(head)
        self.old_note = QLabel()
        self.old_note.setWordWrap(True)
        self.old_note.setStyleSheet(f"color: {WARN_COLOR}; font-size: 19px;")
        col.addWidget(self.old_note)

        # ✥ Verschieben an: kurze Anleitung (gelber Rand zeichnet der Layer)
        self.edit_help = QLabel("✥  " + tr("panel_edit_help"))
        self.edit_help.setObjectName("dim")
        self.edit_help.setWordWrap(True)
        col.addWidget(self.edit_help)
        # Foto-Kasten + Übersetzungs-Kasten haben eine feste Größe (fill_pages) – auch mit kleinem
        # Foto, wenig Text oder ohne Foto bleibt das Panel gleich groß (Rest = leerer Kasten)
        self.photo_box = QFrame()
        self.photo_box.setObjectName("vrphotobox")
        pbox = QVBoxLayout(self.photo_box)
        pbox.setContentsMargins(1, 1, 1, 1)
        self.photo = QLabel()
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setStyleSheet("background: transparent; border: none;")
        pbox.addWidget(self.photo)
        col.addWidget(self.photo_box)
        self.photo_pix = None
        self.result_box = QFrame()
        self.result_box.setObjectName("vrresultbox")
        rbox = QVBoxLayout(self.result_box)
        rbox.setContentsMargins(12, 12, 12, 12)
        rbox.setSpacing(8)
        self.result = QLabel()
        self.result.setObjectName("vrresult")
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        self.result.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        rbox.addWidget(self.result)
        rbox.addStretch(1)
        self.status = QLabel()  # Status unten im Kasten
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        rbox.addWidget(self.status)
        col.addWidget(self.result_box)
        # lange Übersetzung: ▲ 2/3 ▼
        self.page_row = QWidget()
        prow = QHBoxLayout(self.page_row)
        prow.setContentsMargins(0, 0, 0, 0)
        self.up_btn = self.button("▲", lambda: self.turn_page(-1))
        prow.addWidget(self.up_btn, 1)
        self.page_label = QLabel()
        self.page_label.setObjectName("dim")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setMinimumWidth(90)
        prow.addWidget(self.page_label)
        self.down_btn = self.button("▼", lambda: self.turn_page(1))
        prow.addWidget(self.down_btn, 1)
        col.addWidget(self.page_row)

        # Seitenpanel rechts: ⚙ Einstellungen [›] · Dienst [↻] · Von · → Nach · Aufgabe · Letzte KI
        self.side = QFrame()
        self.side.setObjectName("vrcard")
        self.side.setFixedWidth(SIDE_W)
        scol = QVBoxLayout(self.side)
        scol.setContentsMargins(14, 14, 14, 14)
        scol.setSpacing(10)
        row = QHBoxLayout()
        side_title = QLabel("⚙  " + tr("panel_settings"))
        side_title.setObjectName("vrsubtitle")
        row.addWidget(side_title, 1)
        fold = self.button("›", self.toggle_side)
        fold.setFixedWidth(48)
        fold.setStyleSheet("padding: 0;")
        row.addWidget(fold)
        scol.addLayout(row)
        row = QHBoxLayout()
        self.method_btn = self.button("", lambda: self.choose("tr_method"))
        row.addWidget(self.method_btn, 1)
        self.redo_btn = self.button("↻", lambda: self.page.start_translation(force=True))
        self.redo_btn.setFixedWidth(48)
        self.redo_btn.setStyleSheet("padding: 0;")
        row.addWidget(self.redo_btn)
        scol.addLayout(row)
        self.src_btn = self.button("", lambda: self.choose("tr_source"))
        scol.addWidget(self.src_btn)
        self.dst_btn = self.button("", lambda: self.choose("tr_target"))
        scol.addWidget(self.dst_btn)
        self.mode_btn = self.button("", lambda: self.choose("tr_llm_mode"))
        scol.addWidget(self.mode_btn)
        self.last_ai = QLabel()  # „Letzte KI: …“ wie auf der Main-Seite
        self.last_ai.setObjectName("dim")
        self.last_ai.setWordWrap(True)
        scol.addWidget(self.last_ai)
        # 🖐 Rahmen-Geste (🔫 Auto = Waffen-Schutz) und 🥽 Overlay – schnell umschalten
        scol.addSpacing(4)
        gesture = QLabel(tr("gesture_mode"))
        gesture.setObjectName("vrsection")
        scol.addWidget(gesture)
        self.gesture_row, self.gesture_btns = self.choice_row(
            [(v, tr(t)) for v, t in vr_settings.find("gesture_mode")["options"]],
            lambda v: self.set_choice("gesture_mode", v))
        scol.addWidget(self.gesture_row)
        self.overlay_btn = self.button("", lambda: self.set_toggle("overlay"))
        scol.addWidget(self.overlay_btn)
        scol.addStretch(1)
        mrow.addWidget(self.side)
        # eingeklappt: schmale Leiste mit ‹ und „Einstellungen“ senkrecht – antippen klappt auf
        self.strip = self.button("", self.toggle_side)
        self.strip.setObjectName("strip")
        self.strip.setFixedWidth(STRIP_W)
        self.strip.setMinimumHeight(260)
        self.strip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        strip_pix = vertical_pixmap(tr("panel_settings"))
        self.strip.setIcon(QIcon(strip_pix))
        self.strip.setIconSize(strip_pix.size())
        mrow.addWidget(self.strip)
        self.stack.addWidget(main)

        # ---------- Seite 1: Auswahl (statt Dropdown) ----------
        pick = QWidget()
        pcol = QVBoxLayout(pick)
        pcol.setContentsMargins(0, 0, 0, 0)
        prow = QHBoxLayout()
        prow.addWidget(self.button("←  " + tr("back"), self.close_chooser))
        self.pick_title = QLabel()
        self.pick_title.setObjectName("vrtitle")
        prow.addWidget(self.pick_title, 1)
        pcol.addLayout(prow)
        # nur beim Dienst: Modus 🤖 Automatisch / ✋ Manuell
        self.route_row, self.route_btns = self.choice_row(
            [(translation.ROUTE_AUTO, tr("tr_route_auto")), (translation.ROUTE_MANUAL, tr("tr_route_manual"))],
            self.set_route)
        pcol.addWidget(self.route_row)
        self.pick_list = QListWidget()
        self.pick_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pick_list.itemClicked.connect(self.picked)
        pcol.addWidget(self.pick_list)
        pcol.addStretch(1)
        self.stack.addWidget(pick)

        # ---------- Seite 2: ⚙ Einstellungen (Tabs + einklappbare Gruppen) ----------
        self.stack.addWidget(self.build_settings())

        # ---------- Seite 3: 🖼 Galerie (Raster) · Seite 4: ein Foto groß ----------
        self.stack.addWidget(self.build_gallery())
        self.stack.addWidget(self.build_single())
        self.stack.addWidget(self.build_share())
        self.stack.addWidget(self.build_info())
        self.stack.setCurrentIndex(self.home_index())

        # Klicks aus VR
        self.udp = QUdpSocket(self)
        self.udp.readyRead.connect(self.read_clicks)
        self.bind_udp()
        self.shrink_to_page(0)
        self.show()  # WA_DontShowOnScreen: nur fürs Layout, nichts erscheint

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(CHECK_MS)

    # ------------------------------------------------------------ ⚙ Einstellungs-Seite
    def build_settings(self) -> QWidget:
        """Links die Kategorien (📸 Shot / 🥽 VR mit ihren Gruppen), rechts das Untermenü der
        gewählten Kategorie – wie die Welt-Menüs in VRChat. Inhalt baut fill_settings() jedes Mal neu."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        title = QLabel("⚙  " + tr("panel_settings"))
        title.setObjectName("vrtitle")
        col.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(COL_GAP)
        cats = QWidget()
        cats.setFixedWidth(CAT_W)
        self.set_cats = QVBoxLayout(cats)
        self.set_cats.setContentsMargins(0, 0, 0, 0)
        self.set_cats.setSpacing(6)
        row.addWidget(cats, 0, Qt.AlignmentFlag.AlignTop)
        card = QFrame()
        card.setObjectName("vrcard")
        ccol = QVBoxLayout(card)
        ccol.setContentsMargins(14, 14, 14, 14)
        ccol.setSpacing(10)
        self.set_sub_title = QLabel()
        self.set_sub_title.setObjectName("vrsubtitle")
        ccol.addWidget(self.set_sub_title)
        self.set_body = QVBoxLayout()
        self.set_body.setSpacing(10)
        ccol.addLayout(self.set_body)
        ccol.addStretch(1)
        row.addWidget(card, 1)
        col.addLayout(row)
        return page

    def chosen_group(self) -> dict:
        """⚙ Gewählte Kategorie (noch keine → die erste)."""
        groups = [g for t in vr_settings.TABS for g in t["groups"]]
        return next((g for g in groups if g["id"] == self.set_open), groups[0])

    def fill_settings(self):
        """Kategorien links (gewählte blau mit ›), Einträge der gewählten rechts."""
        clear_layout(self.set_cats)
        clear_layout(self.set_body)
        lcfg = layer_config.load()
        chosen = self.chosen_group()
        for tab in vr_settings.TABS:
            # Überschrift ▾ 📸 Shot / ▸ 🥽 VR – antippen klappt ihre Kategorien ein/aus
            folded = tab["id"] in self.set_folded
            head = self.button(("▸  " if folded else "▾  ") + tr(tab["label"]), lambda t=tab["id"]: self.fold_tab(t))
            head.setObjectName("cathead")
            self.set_cats.addWidget(head)
            head.show()
            if folded:
                continue
            for group in tab["groups"]:
                on = group["id"] == chosen["id"]
                text = (group["icon"] + "  " if group["icon"] else "") + tr(group["title"]).replace("&", "&&")
                btn = self.button(text, lambda g=group["id"]: self.toggle_group(g))
                btn.setObjectName("catOn" if on else "cat")
                font = QFont(btn.font())
                font.setBold(True)
                size = 20  # zu lang → etwas kleiner statt abschneiden
                font.setPixelSize(size)
                while size > 12 and QFontMetrics(font).horizontalAdvance(text) > CAT_W - 48:
                    size -= 1
                    font.setPixelSize(size)
                btn.setStyleSheet(f"font-size: {size}px;")
                if on:
                    arrow_row = QHBoxLayout(btn)
                    arrow_row.setContentsMargins(0, 0, 14, 0)
                    arrow_row.addStretch(1)
                    arrow = QLabel("›")
                    arrow.setObjectName("catarrow")
                    arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)  # Klick geht an den Knopf
                    arrow_row.addWidget(arrow)
                self.set_cats.addWidget(btn)
                btn.show()  # neu in ein schon sichtbares Fenster → selbst zeigen
            self.set_cats.addSpacing(6)
        self.set_sub_title.setText((chosen["icon"] + "  " if chosen["icon"] else "") + tr(chosen["title"]))
        for item in chosen["items"]:
            w = self.setting_widget(item, lcfg)
            self.set_body.addWidget(w)
            w.show()

    def setting_widget(self, item: dict, lcfg: dict) -> QWidget:
        """Ein Eintrag aus core/vr_settings.py als Knöpfe / Leiste."""
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 8)
        col.setSpacing(4)

        def section(text: str):
            label = QLabel(text)
            label.setObjectName("vrsection")
            label.setWordWrap(True)
            col.addWidget(label)

        kind, key = item["type"], item.get("key", "")
        value = lcfg.get(key, layer_config.DEFAULTS.get(key))
        if kind == "toggle":
            on = bool(value)
            btn = self.button(("✔  " if on else "✕  ") + tr(item["label"]), lambda: self.set_toggle(key))
            self.mark({True: btn}, on)
            col.addWidget(btn)
        elif kind == "choice":
            if item.get("label"):
                section(tr(item["label"]))
            options = [(v, text[1:] if text.startswith("=") else tr(text)) for v, text in item["options"]]
            cols = item.get("cols") or len(options)
            grid = QGridLayout()
            grid.setSpacing(6)
            btns = {}
            for i, (v, text) in enumerate(options):
                btn = self.button(text, lambda v=v: self.set_choice(key, v))
                btn.setStyleSheet("padding: 4px 6px;")
                grid.addWidget(btn, i // cols, i % cols)
                btns[v] = btn
            self.mark(btns, value)
            col.addLayout(grid)
        elif kind == "slider":
            current = button_cm() if key == "@button_cm" else int(value)
            if current is None:
                section(f"{tr(item['label'])}  {tr('panel_size_later')}")
            elif item.get("fmt"):
                section(tr(item["fmt"], v=current, inv=item["min"] + item["max"] - current))
            else:
                section(f"{tr(item['label'])}:  {current}{item.get('unit', '')}")
            bar = ClickBar(item["min"], item["max"], lambda v, it=item: self.set_slider(it, v))
            bar.set_value(current if current is not None else item["min"])
            bar.setEnabled(current is not None)
            col.addWidget(bar)
        elif kind == "size":
            cm = page_width_cm(self.size_page)
            name = tr(dict(vr_settings.SIZE_PAGES)[self.size_page])
            section(f"{tr('panel_size')} · {name}" + (f":  {cm} cm" if cm else f"  {tr('panel_size_later')}"))
            row, btns = self.choice_row([(p, tr(k)) for p, k in vr_settings.SIZE_PAGES], self.set_size_page)
            self.mark(btns, self.size_page)
            col.addWidget(row)
            bar = ClickBar(*SIZE_CM, self.size_changed)
            bar.set_value(cm or round(PAGE_SIZE_DEFAULT[self.size_page] * 100))
            bar.setEnabled(cm is not None)
            col.addWidget(bar)
        elif kind == "actions":
            row = QHBoxLayout()
            for name, label in item["actions"]:
                if name == "move":
                    edit = bool(lcfg.get("panel_edit"))
                    btn = self.button(("✔  " if edit else "✥  ") + tr(label), self.toggle_edit)
                    self.mark({True: btn}, edit)
                else:
                    btn = self.button("⟲  " + tr(label), reset_position)
                row.addWidget(btn, 1)
            col.addLayout(row)
        elif kind == "colors":
            row = QHBoxLayout()
            row.setSpacing(6)
            current = str(value or BUTTON_COLORS[0]).lower()
            for color in BUTTON_COLORS:
                b = self.button("✔" if color == current else "", lambda c=color: self.set_layer(key, c))
                b.setObjectName("swatch")
                b.setStyleSheet(f"QPushButton#swatch {{ background: {color}; border: 3px solid #2b3240; "
                                f"border-radius: 10px; min-height: 44px; font-size: 22px; color: #10131a; }}")
                row.addWidget(b, 1)
            col.addLayout(row)
        elif kind == "list":
            hint = QLabel(tr(item["hint"]))
            hint.setObjectName("dim")
            hint.setWordWrap(True)
            col.addWidget(hint)
            entries = list(value or [])
            if not entries:
                section(tr(item["empty"]))
            for name in entries:
                btn = self.button("✕  " + name, lambda n=name: self.remove_from_list(key, n))
                btn.setStyleSheet("text-align: left; padding-left: 16px;")
                col.addWidget(btn)
        return box

    def go_settings(self):
        """⚙ oben auf jeder Seite: direkt zu den Einstellungen."""
        if self.mode != "settings":
            self.switch_to("settings")

    def fold_tab(self, tab: str):
        """⚙ Überschrift links: Kategorien von 📸 Shot / 🥽 VR ein-/ausklappen."""
        self.set_folded ^= {tab}

    def toggle_group(self, gid: str):
        """⚙ Kategorie links antippen → ihr Untermenü rechts."""
        self.set_open = gid

    def set_size_page(self, page: str):
        self.size_page = page

    # ------------------------------------------------------------ Seiten (◀ ▶ unten) + 🖼 Galerie
    def content_w(self, index: int | None = None) -> int:
        """Breite des Inhalts (ohne Rand) – PAGE_MAIN: nur die linke Spalte neben dem Seitenpanel."""
        inner = PAGE_WIDTH.get(self.mode, WIDE) - 36
        if index == PAGE_MAIN:
            return main_w(side_closed())
        if index == PAGE_GALLERY:
            return main_w(bool(layer_config.load().get("gallery_side_closed")))
        return inner

    def home_index(self) -> int:
        """Stapel-Seite der aktuellen Hauptseite (dahin geht's nach der Auswahl zurück)."""
        if self.mode == "gallery":
            return PAGE_SINGLE if self.gal_open is not None else PAGE_GALLERY
        if self.mode == "settings":
            return PAGE_SETTINGS
        return PAGE_MAIN

    def go_page(self, page: str):
        """Tab unten: andere Seite – mit ihrer eigenen Größe in VR."""
        if page != self.mode:
            self.switch_to(page)

    def switch_to(self, new: str):
        old, self.mode = self.mode, new
        self.gal_open, self.gal_confirm, self.gal_toast = None, False, ""
        self.choosing = None
        switch_page_size(old, self.mode)
        self.stack.setCurrentIndex(self.home_index())

    def page_name(self, page: str) -> str:
        return tr(dict(vr_settings.SIZE_PAGES)[page])

    def fill_nav(self):
        for name, btn in self.nav_tabs.items():
            obj = "tabOn" if name == self.mode else "tab"
            if btn.objectName() != obj:
                btn.setObjectName(obj)
                btn.style().polish(btn)

    def head(self, title: QLabel, extra=()) -> QHBoxLayout:
        """Kopfzeile: Titel … [extra] [⚙] – ⚙ ist auf jeder Seite oben."""
        row = QHBoxLayout()
        title.setObjectName("vrtitle")
        row.addWidget(title, 1)
        for w in extra:
            row.addWidget(w)
        row.addWidget(self.button("⚙", self.go_settings, tip=True))
        return row

    def build_gallery(self) -> QWidget:
        """Links das Raster mit Monats-Trennern, rechts das Seitenpanel (Filter, Spalten, Blättern –
        einklappbar wie bei der Übersetzung)."""
        page = QWidget()
        prow = QHBoxLayout(page)
        prow.setContentsMargins(0, 0, 0, 0)
        prow.setSpacing(COL_GAP)
        left = QWidget()
        col = QVBoxLayout(left)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        title = QLabel("🖼  " + tr("nav_gallery"))
        title.setObjectName("vrtitle")
        title.setMinimumHeight(48)
        col.addWidget(title)
        self.gal_host = QWidget()
        self.gal_grid = QGridLayout(self.gal_host)
        self.gal_grid.setContentsMargins(0, 0, 0, 0)
        self.gal_grid.setHorizontalSpacing(GRID_GAP)
        self.gal_grid.setVerticalSpacing(GRID_GAP)
        col.addWidget(self.gal_host)
        self.gal_empty = QLabel(tr("no_photo"))
        self.gal_empty.setObjectName("dim")
        self.gal_empty.setWordWrap(True)
        col.addWidget(self.gal_empty)
        col.addStretch(1)
        prow.addWidget(left, 1)

        # Seitenpanel: ⚙ Einstellungen [›] · Filter · Spalten 3/4/5 · [▲] 1 / 3 [▼]
        self.gal_side = QFrame()
        self.gal_side.setObjectName("vrcard")
        self.gal_side.setFixedWidth(SIDE_W)
        scol = QVBoxLayout(self.gal_side)
        scol.setContentsMargins(14, 14, 14, 14)
        scol.setSpacing(10)
        row = QHBoxLayout()
        side_title = QLabel("⚙  " + tr("panel_settings"))
        side_title.setObjectName("vrsubtitle")
        row.addWidget(side_title, 1)
        fold = self.button("›", self.toggle_gal_side)
        fold.setFixedWidth(48)
        fold.setStyleSheet("padding: 0;")
        row.addWidget(fold)
        scol.addLayout(row)
        head = QLabel(tr("vr_gallery_filter"))
        head.setObjectName("vrsection")
        scol.addWidget(head)
        # Filter: Alle · 📝 Text · 🔳 QR-Code · 🖼 Bild · 🎞 GIF/VID (wie in der Desktop-Galerie)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.gal_filter_btns = {}
        items = ([("", tr("filter_all"))] + [(k, f"{tags.ICONS[k]} {tr('tag_' + k)}") for k in tags.ALL]
                 + [(tags.GIF_VID, f"{tags.ICONS[tags.GIF_VID]} {tr('tag_gif_vid')}")])
        for i, (value, text) in enumerate(items):
            btn = self.button(text, lambda v=value: self.set_gal_filter(v))
            btn.setStyleSheet("padding: 4px 6px;")
            grid.addWidget(btn, i // 2, i % 2)
            self.gal_filter_btns[value] = btn
        scol.addLayout(grid)
        head = QLabel(tr("vr_gallery_cols"))
        head.setObjectName("vrsection")
        scol.addWidget(head)
        self.gal_cols_row, self.gal_cols_btns = self.choice_row(
            [(str(c), str(c)) for c in GALLERY_COLS], lambda v: self.set_choice("gallery_cols", v))
        scol.addWidget(self.gal_cols_row)
        row = QHBoxLayout()
        self.gal_up = self.button("▲", lambda: self.gal_turn(-1))
        row.addWidget(self.gal_up, 1)
        self.gal_label = QLabel()
        self.gal_label.setObjectName("dim")
        self.gal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gal_label.setMinimumWidth(64)
        row.addWidget(self.gal_label)
        self.gal_down = self.button("▼", lambda: self.gal_turn(1))
        row.addWidget(self.gal_down, 1)
        scol.addLayout(row)
        scol.addStretch(1)
        prow.addWidget(self.gal_side)
        # eingeklappt: schmale Leiste mit ‹ und „Einstellungen“ senkrecht
        self.gal_strip = self.button("", self.toggle_gal_side)
        self.gal_strip.setObjectName("strip")
        self.gal_strip.setFixedWidth(STRIP_W)
        self.gal_strip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        strip_pix = vertical_pixmap(tr("panel_settings"))
        self.gal_strip.setIcon(QIcon(strip_pix))
        self.gal_strip.setIconSize(strip_pix.size())
        prow.addWidget(self.gal_strip)
        return page

    def build_single(self) -> QWidget:
        """Ein Foto groß – mit allen Aktionen wie in der Desktop-Galerie."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        self.single_title = QLabel()
        col.addLayout(self.head(self.single_title))
        self.single_photo = QLabel()
        self.single_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.single_photo)
        self.single_info = QLabel()
        self.single_info.setObjectName("dim")
        self.single_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.single_info)
        self.single_toast = QLabel()
        self.single_toast.setObjectName("vrtoast")
        self.single_toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.single_toast.setWordWrap(True)
        col.addWidget(self.single_toast)

        def row(*buttons):
            r = QHBoxLayout()
            r.setSpacing(8)
            for b in buttons:
                r.addWidget(b, 1)
            col.addLayout(r)

        # [‹]  [← Zurück]  [›]
        self.single_prev = self.button("‹", lambda: self.gal_step(-1))
        self.single_back = self.button("←  " + tr("back"), self.gal_back)
        self.single_next = self.button("›", lambda: self.gal_step(1))
        row(self.single_prev, self.single_back, self.single_next)
        # [📋 Kopieren] [☁ Hochladen + Link] [↗ Teilen]
        self.single_copy = self.button("📋  " + tr("copy"), self.gal_copy)
        self.single_upload = self.button("", self.gal_upload)
        self.single_share = self.button("↗  " + tr("share"), self.gal_share)
        row(self.single_copy, self.single_upload, self.single_share)
        # [🌐 Übersetzen] [ⓘ Info] [🗑 Löschen]
        self.single_translate = self.button("🌐  " + tr("translate_btn"), self.gal_translate)
        self.single_info_btn = self.button("ⓘ  " + tr("info"), self.gal_info)
        self.single_delete = self.button("", self.gal_delete)
        row(self.single_translate, self.single_info_btn, self.single_delete)
        return page

    def build_share(self) -> QWidget:
        """↗ Teilen: Liste der installierten Programme (Discord/Vesktop, Telegram, E-Mail)."""
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(self.button("←  " + tr("back"), self.back_to_single))
        title = QLabel("↗  " + tr("share"))
        title.setObjectName("vrtitle")
        top.addWidget(title, 1)
        col.addLayout(top)
        self.share_box = QVBoxLayout()
        self.share_box.setSpacing(8)
        col.addLayout(self.share_box)
        col.addStretch(1)
        return page

    def build_info(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(self.button("←  " + tr("back"), self.back_to_single))
        title = QLabel("ⓘ  " + tr("info"))
        title.setObjectName("vrtitle")
        top.addWidget(title, 1)
        col.addLayout(top)
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(14)
        self.info_grid.setVerticalSpacing(8)
        col.addLayout(self.info_grid)
        col.addStretch(1)
        return page

    def gallery_photos(self) -> list[Path]:
        """Alle Galerie-Bilder (Foto-Ordner + weitere Ordner), neueste zuerst."""
        return tags.filter_photos(paths.gallery_photos(self.page.cfg), self.gal_filter)

    def thumb(self, photo: Path, w: int, h: int) -> QPixmap:
        """Vorschaubild w × h (Mitte ausgeschnitten, gleich große Kacheln) – gemerkt."""
        key = (str(photo), paths.photo_mtime(photo), w)
        pix = self.thumbs.get(key)
        if pix is None:
            reader = QImageReader(str(paths.preview_of(photo)))
            size = reader.size()
            if size.isValid():  # gleich beim Laden verkleinern – viel schneller
                reader.setScaledSize(size.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
            img = reader.read()
            pix = QPixmap(w, h)
            pix.fill(QColor("#14161c"))
            if not img.isNull():
                painter = QPainter(pix)
                painter.drawImage((w - img.width()) // 2, (h - img.height()) // 2, img)
                if paths.is_video(photo):
                    draw_play_badge(painter, w, h)
                painter.end()
            if len(self.thumbs) > 200:
                self.thumbs.clear()
            self.thumbs[key] = pix
        return pix

    @staticmethod
    def tile_size() -> tuple[int, int]:
        """Kachel-Größe: Breite der linken Spalte (Seitenpanel offen / zu) durch die Spalten."""
        cols = gallery_cols()
        cw = (main_w(bool(layer_config.load().get("gallery_side_closed"))) - (cols - 1) * GRID_GAP) // cols
        return cw, round(cw * THUMB_RATIO)

    def grid_height(self) -> int:
        """So viel Platz hat das Raster: ganze Panel-Höhe minus Rand, Kopf und Tab-Leiste."""
        total = fixed_height_px("gallery") or GALLERY_H
        return max(MONTH_H + self.tile_size()[1], total - 32 - (48 + 10) - (NAV_H + 10))

    def gallery_pages(self, photos: list[Path]) -> list[list[tuple]]:
        """Fotos → Raster-Seiten. Jede Seite: Zeilen ("month", Text) / ("row", [Fotos]),
        so viele, wie in die Höhe passen. Ein Monat, der auf der neuen Seite weitergeht,
        bekommt oben nochmal seinen Trenner."""
        _cw, ch = self.tile_size()
        cols = gallery_cols()
        room = self.grid_height()
        rows = []  # (Monat, Zeile)
        month, cur = None, []
        for photo in photos:
            ym = paths.month_key(photo)
            if ym != month or len(cur) == cols:
                if cur:
                    rows.append((month, cur))
                cur = []
                month = ym
            cur.append(photo)
        if cur:
            rows.append((month, cur))
        pages, page, used, last_month = [], [], 0, None
        for ym, row in rows:
            need = ch + (MONTH_H + GRID_GAP if ym != last_month or not page else 0)
            if page and used + need > room:
                pages.append(page)
                page, used, last_month = [], 0, None
                need = ch + MONTH_H + GRID_GAP
            if ym != last_month:
                page.append(("month", month_title(*ym)))
            page.append(("row", row))
            used += need + GRID_GAP
            last_month = ym
        if page:
            pages.append(page)
        return pages or [[]]

    def month_row(self, text: str) -> QWidget:
        """Trenner „──── 2026 Oktober ────“ über die ganze Breite."""
        box = QWidget()
        box.setFixedHeight(MONTH_H)
        r = QHBoxLayout(box)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(12)
        for i in range(3):
            if i == 1:
                label = QLabel(text)
                label.setObjectName("month")
                r.addWidget(label)
            else:
                line = QFrame()
                line.setObjectName("monthline")
                line.setFixedHeight(2)
                r.addWidget(line, 1)
        return box

    def fill_gallery(self):
        self.mark(self.gal_filter_btns, self.gal_filter)
        cols = gallery_cols()
        self.mark(self.gal_cols_btns, str(cols))
        closed = bool(layer_config.load().get("gallery_side_closed"))
        self.gal_side.setVisible(not closed)
        self.gal_strip.setVisible(closed)
        photos = self.gallery_photos()
        pages = self.gallery_pages(photos)
        self.gal_pages_cache = pages
        self.gal_page = max(0, min(self.gal_page, len(pages) - 1))
        while self.gal_grid.count():  # alte Kacheln weg
            widget = self.gal_grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        cw, ch = self.tile_size()
        for r, (kind, value) in enumerate(pages[self.gal_page]):
            if kind == "month":
                w = self.month_row(value)
                self.gal_grid.addWidget(w, r, 0, 1, cols)
                w.show()
                continue
            for c, photo in enumerate(value):
                btn = QPushButton()
                btn.setObjectName("thumb")
                btn.setFixedSize(cw, ch)
                btn.setIcon(QIcon(self.thumb(photo, cw - 4, ch - 4)))
                btn.setIconSize(QSize(cw - 4, ch - 4))
                btn.clicked.connect(lambda _=False, p=photo: (self.open_photo(p), self.refresh(force=True)))
                self.gal_grid.addWidget(btn, r, c)
                btn.show()  # das Panel ist „offen“ – neue Kacheln sofort sichtbar machen
        for c in range(max(GALLERY_COLS)):  # weniger Spalten → die übrigen ohne Mindestbreite
            self.gal_grid.setColumnMinimumWidth(c, cw if c < cols else 0)
            self.gal_grid.setColumnStretch(c, 0)
        self.gal_grid.setColumnStretch(max(GALLERY_COLS), 1)
        self.gal_host.setVisible(bool(photos))
        self.gal_empty.setVisible(not photos)
        self.gal_up.setEnabled(self.gal_page > 0)
        self.gal_down.setEnabled(self.gal_page < len(pages) - 1)
        self.gal_label.setText(f"{self.gal_page + 1} / {len(pages)}")

    def page_of(self, photo: Path) -> int:
        for i, page in enumerate(self.gal_pages_cache):
            if any(kind == "row" and photo in value for kind, value in page):
                return i
        return self.gal_page

    def fill_single(self):
        photos = self.gallery_photos()
        photo = self.gal_open
        if photo is None:
            return
        if photo not in photos:  # inzwischen gelöscht (z. B. in der Desktop-Galerie)
            self.gal_open, self.gal_confirm = None, False
            if self.stack.currentIndex() in (PAGE_SINGLE, PAGE_SHARE, PAGE_INFO):
                self.stack.setCurrentIndex(PAGE_GALLERY)
            return
        i = photos.index(photo)
        self.single_title.setText(photo.stem.removeprefix("ViewShot_"))
        self.single_info.setText(f"{i + 1} / {len(photos)}   ·   {month_title(*paths.month_key(photo))}")
        pix = self.gif_pixmap(photo) if photo.suffix.lower() == ".gif" else None
        if pix is None:
            self.stop_gif()
            pix = QPixmap(str(paths.preview_of(photo)))
        if not pix.isNull():
            pix = pix.scaled(self.content_w(), SINGLE_MAX_H, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            self.single_photo.setPixmap(pix)
            self.single_photo.setFixedHeight(pix.height())
        self.single_toast.setText(self.gal_toast)
        self.single_toast.setVisible(bool(self.gal_toast))
        self.single_prev.setEnabled(i > 0)
        self.single_next.setEnabled(i < len(photos) - 1)
        busy = photo in self.uploading
        links = uploader.saved_links(photo)
        self.single_upload.setText("⏳  " + tr("uploading") if busy
                                   else ("🔗  " + tr("copy_link") if links else "☁  " + tr("upload_copy_link")))
        self.single_upload.setEnabled(not busy)
        self.single_delete.setText("🗑  " + tr("vr_delete_sure" if self.gal_confirm else "delete"))
        self.mark({True: self.single_delete}, self.gal_confirm)  # blau = nochmal tippen löscht

    # ------------------------------------------------------------ 🎞 GIF animiert
    def gif_pixmap(self, photo: Path) -> QPixmap | None:
        """GIF als Animation: QMovie liefert Bild für Bild, jedes neue Bild → Panel neu malen."""
        if self.gif_movie is None or self.gif_path != photo:
            self.stop_gif()
            movie = QMovie(str(photo))
            if not movie.isValid():
                return None
            movie.frameChanged.connect(self.on_gif_frame)
            self.gif_movie, self.gif_path = movie, photo
        if self.gif_movie.state() != QMovie.MovieState.Running:
            self.gif_movie.start()
        pix = self.gif_movie.currentPixmap()
        return None if pix.isNull() else pix

    def stop_gif(self):
        if self.gif_movie is not None:
            self.gif_movie.stop()
            self.gif_movie.deleteLater()
        self.gif_movie, self.gif_path = None, None

    def on_gif_frame(self, _number: int):
        if self.stack.currentIndex() != PAGE_SINGLE or self.gal_open != self.gif_path:
            self.stop_gif()  # Einzelansicht verlassen / anderes Foto
            return
        now = time.monotonic()
        if not enabled() or not panel_open() or now - self.gif_written < GIF_MIN_FRAME_S:
            return  # Panel zu / zu schnell – dieses Bild auslassen
        self.gif_written = now
        try:
            self.write(self.render())
        except Exception:  # noqa: BLE001 – das Panel darf die App nie stören
            logging.exception("VR-Panel: GIF-Bild konnte nicht gezeichnet werden")

    def open_photo(self, photo: Path):
        self.gal_open, self.gal_confirm, self.gal_toast = photo, False, ""
        self.stack.setCurrentIndex(PAGE_SINGLE)

    def gal_back(self):
        if self.gal_open is not None:
            self.gal_page = self.page_of(self.gal_open)  # Raster dort, wo das Foto steht
        self.gal_open, self.gal_confirm, self.gal_toast = None, False, ""
        self.stack.setCurrentIndex(PAGE_GALLERY)

    def back_to_single(self):
        self.stack.setCurrentIndex(PAGE_SINGLE if self.gal_open is not None else PAGE_GALLERY)

    def gal_turn(self, step: int):
        self.gal_page += step

    def gal_step(self, step: int):
        """Voriges / nächstes Foto in der Einzelansicht."""
        photos = self.gallery_photos()
        if self.gal_open in photos:
            i = photos.index(self.gal_open) + step
            if 0 <= i < len(photos):
                self.gal_open, self.gal_confirm, self.gal_toast = photos[i], False, ""

    def gal_translate(self):
        """🌐 Dieses Foto übersetzen: zurück auf die Übersetzungs-Seite."""
        if self.gal_open is None:
            return
        self.page.set_chosen(self.gal_open)
        self.page.vr_chosen = True  # kommt ein neues Foto, zeigt das Panel wieder das neueste
        p = self.page
        # nicht im Cache + „automatisch übersetzen“ aus → jetzt übersetzen (Knopf heißt ja so)
        if not p.tr_result and not p.translating and p.translate_btn.isEnabled():
            p.start_translation()
        self.gal_open, self.gal_confirm, self.gal_toast = None, False, ""
        self.switch_to(PAGES[0])

    def gal_copy(self):
        """📋 Bild in die Zwischenablage (kommt auch auf dem Desktop an)."""
        if self.gal_open is not None:
            clipboard.set_image(self.gal_open)
            self.gal_toast = tr("vr_copied_image")

    def gal_upload(self):
        """☁ Hochladen + Link kopieren (schon hochgeladen → nur Link kopieren)."""
        photo = self.gal_open
        if photo is None or photo in self.uploading:
            return
        links = uploader.saved_links(photo)
        if links:
            clipboard.set_text(links["view"])
            self.gal_toast = tr("vr_link_copied")
            return
        self.uploading.add(photo)
        self.gal_toast = tr("vr_uploading")

        def work():  # Hintergrund – KEINE Widgets anfassen! (QImage geht)
            try:
                data, mime = photo.read_bytes(), "image/png" if photo.suffix.lower() == ".png" else "image/jpeg"
                if len(data) > uploader.MAX_BYTES:  # über 8 MB → als JPG verkleinern
                    from PyQt6.QtCore import QBuffer, QIODevice
                    buf = QBuffer()
                    buf.open(QIODevice.OpenModeFlag.WriteOnly)
                    QImage(str(photo)).save(buf, "JPG", 92)
                    data, mime = bytes(buf.data()), "image/jpeg"
                self.upload_finished.emit(str(photo), uploader.upload(photo, data, mime), "")
            except Exception as e:  # noqa: BLE001
                self.upload_finished.emit(str(photo), None, str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_upload_finished(self, photo: str, links, error: str):
        self.uploading.discard(Path(photo))
        if links:
            clipboard.set_text(links["view"])
        if self.gal_open == Path(photo):
            self.gal_toast = tr("vr_link_copied") if links else f"{tr('vr_upload_failed')}: {error}"
        self.refresh(force=True)

    def gal_share(self):
        """↗ Teilen: Programme zur Auswahl."""
        while self.share_box.count():
            w = self.share_box.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        targets = share.available()
        if not targets:
            label = QLabel(tr("vr_share_none"))
            label.setObjectName("dim")
            self.share_box.addWidget(label)
        for key, name in targets:
            btn = self.button(name, lambda k=key: self.share_to(k))
            self.share_box.addWidget(btn)
            btn.show()
        self.stack.setCurrentIndex(PAGE_SHARE)

    def share_to(self, key: str):
        photo = self.gal_open
        if photo is None:
            return
        if key == "discord":
            clipboard.set_image(photo)  # Discord / Vesktop: nur Einfügen geht
        try:
            kind = share.share(key, photo)
            self.gal_toast = tr("vr_shared_paste") if kind == "paste" else tr("vr_shared")
        except Exception as e:  # noqa: BLE001
            self.gal_toast = f"{tr('share_failed')}: {e}"
        self.back_to_single()

    def gal_info(self):
        """ⓘ Ordner, Datum, Größe, Typ, Link."""
        photo = self.gal_open
        if photo is None:
            return
        while self.info_grid.count():
            w = self.info_grid.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        reader = QImageReader(str(paths.preview_of(photo)))
        size = reader.size()
        try:
            mb = photo.stat().st_size / 1024 / 1024
        except OSError:
            mb = 0.0
        from datetime import datetime
        when = datetime.fromtimestamp(paths.photo_mtime(photo)).strftime("%d.%m.%Y  %H:%M")
        entry = tags.get(photo)
        kind = "  ".join(f"{tags.ICONS[t]} {tr('tag_' + t)}" for t in entry["tags"]) if entry else "–"
        links = uploader.saved_links(photo)
        rows = [(tr("vr_info_folder"), str(photo.parent)), (tr("vr_info_date"), when),
                (tr("vr_info_size"), f"{size.width()} × {size.height()} px   ·   {mb:.1f} MB"),
                (tr("vr_info_type"), kind), (tr("vr_info_link"), links["view"] if links else "–")]
        for r, (key, value) in enumerate(rows):
            k = QLabel(key)
            k.setObjectName("infokey")
            v = QLabel(value)
            v.setObjectName("infoval")
            v.setWordWrap(True)
            self.info_grid.addWidget(k, r, 0, Qt.AlignmentFlag.AlignTop)
            self.info_grid.addWidget(v, r, 1)
            k.show()
            v.show()
        self.info_grid.setColumnStretch(1, 1)
        self.stack.setCurrentIndex(PAGE_INFO)

    def gal_delete(self):
        """🗑 Erst antippen = „Wirklich löschen?“, nochmal antippen = in den Papierkorb."""
        photo = self.gal_open
        if photo is None:
            return
        if not self.gal_confirm:
            self.gal_confirm = True
            return
        from ui.pages.gallery_page import move_to_trash
        photos = self.gallery_photos()
        index = photos.index(photo) if photo in photos else 0
        self.gal_confirm = False
        if not move_to_trash(photo):
            logging.warning("VR-Panel: %s konnte nicht in den Papierkorb", photo)
            self.gal_toast = tr("delete_failed")
            return
        paths.forget_scan()  # Liste neu lesen
        rest = self.gallery_photos()
        if rest:
            self.gal_open = rest[min(index, len(rest) - 1)]
            self.gal_toast = ""
        else:
            self.gal_open = None
            self.stack.setCurrentIndex(PAGE_GALLERY)
        self.page.refresh()  # war es das gezeigte Foto → die Seite nimmt ein anderes

    def choice_row(self, items: list[tuple[str, str]], on_pick) -> tuple[QWidget, dict]:
        """Nebeneinander liegende Knöpfe, einer ist gewählt (blau)."""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        btns = {}
        for value, text in items:
            btn = self.button(text, lambda v=value: on_pick(v))
            btn.setStyleSheet("padding: 4px 6px;")
            row.addWidget(btn, 1)
            btns[value] = btn
        return box, btns

    @staticmethod
    def mark(btns: dict, chosen):
        for value, btn in btns.items():
            name = "sendbtn" if value == chosen else "linkbtn"
            if btn.objectName() != name:
                btn.setObjectName(name)
                btn.style().polish(btn)

    def set_gal_filter(self, key: str):
        self.gal_filter, self.gal_page = key, 0

    def toggle_gal_side(self):
        """🖼 Seitenpanel der Galerie ein-/ausklappen (eingeklappt → größere Kacheln)."""
        layer_config.update("gallery_side_closed", not layer_config.load().get("gallery_side_closed"))

    def bind_udp(self, tries: int = 0):
        """Port für Klicks aus VR. Hatte ihn gerade noch der ⚙ Hintergrund-Dienst
        (er gibt ihn ab, sobald die App offen ist) → kurz danach nochmal."""
        port = int(layer_config.load().get("panel_port") or 47931)
        # ReuseAddressHint: beim Sprachwechsel gibt es kurz zwei Seiten
        if self.udp.bind(QHostAddress(QHostAddress.SpecialAddress.LocalHost), port,
                         QUdpSocket.BindFlag.ReuseAddressHint | QUdpSocket.BindFlag.ShareAddress):
            return
        if tries < 10:
            QTimer.singleShot(1000, lambda: self.bind_udp(tries + 1))
        else:
            logging.warning("VR-Panel: UDP-Port %s belegt – Klicks aus VR gehen nicht", port)

    def button(self, text: str, slot, tip: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("linkbtn")
        btn.clicked.connect(lambda: (slot(), self.refresh(force=True)))
        if tip:
            btn.setFixedWidth(64)
        return btn

    # ------------------------------------------------------------ Inhalt
    def state(self) -> tuple:
        """Alles, was man sieht – ändert sich etwas, wird neu gezeichnet."""
        p = self.page
        live = getattr(p, "live_shown", False)
        photo = live_photo() if live else p.last_photo
        lcfg = layer_config.load()
        mtime = photo.stat().st_mtime if photo is not None and photo.exists() else 0
        try:
            pose = (pose_file().stat().st_mtime, button_cm())
        except OSError:
            pose = (0, button_cm())
        old = (layer_install.outdated(), self.old_open)
        settings = (self.set_tab, self.set_open, tuple(sorted(self.set_folded)), self.size_page,
                    page_width_cm(self.size_page) if self.mode == "settings" else None)
        return (str(photo), mtime, pose, old, json.dumps(lcfg, sort_keys=True), settings, p.tr_result,
                p.tr_status.text(), p.cfg.get("tr_method"),
                p.cfg.get("tr_source"), p.cfg.get("tr_target"), p.cfg.get("tr_llm_mode"),
                p.cfg.get("tr_explain_method"), p.cfg.get("tr_answer_method"),
                p.cfg.get("tr_route"), p.cfg.get("tr_auto_once"), p.last_ai_label.text(),
                self.choosing, self.stack.currentIndex(), self.result_page,
                tuple(self.lines_for(photo, live)),
                self.mode, self.gal_page, str(self.gal_open), self.gal_confirm, self.gal_toast,
                tuple(sorted(map(str, self.uploading))), fixed_height_px(self.mode),
                tuple(self.gallery_photos()) if self.mode == "gallery" else ())

    def lines_for(self, photo, live: bool) -> list:
        if photo is None:
            return []
        if live:
            return [str(line) for line in getattr(self.page, "live_lines", [])]
        return [str(line) for line in translation.cached_lines(photo)]

    def fill(self):
        p = self.page
        cfg = p.cfg
        live = getattr(p, "live_shown", False)
        photo = live_photo() if live else p.last_photo
        lines = getattr(p, "live_lines", []) if live else (translation.cached_lines(photo) if photo else [])
        lcfg = layer_config.load()
        self.setFixedWidth(PAGE_WIDTH.get(self.mode, WIDE))
        closed = bool(lcfg.get("panel_side_closed"))
        self.side.setVisible(not closed)
        self.strip.setVisible(closed)
        self.edit_help.setVisible(bool(lcfg.get("panel_edit")))
        hide_photo = bool(lcfg.get("panel_hide_photo"))
        self.pic_btn.setText("🖼 ▼" if hide_photo else "🖼 ▲")
        self.mark({True: self.pic_btn}, hide_photo)
        self.mark(self.gesture_btns, lcfg.get("gesture_mode"))
        overlay_on = bool(lcfg.get("overlay"))
        self.overlay_btn.setText(("✔  " if overlay_on else "✕  ") + elide(tr("vr_overlay_short"), SIDE_W - 2 * 14 - 70))
        self.mark({True: self.overlay_btn}, overlay_on)
        self.rec_btn.setText(layer_config.rec_label(bool(lcfg.get("rec_video"))))
        outdated = layer_install.outdated()
        self.old_btn.setVisible(outdated)
        self.old_note.setVisible(outdated and self.old_open)
        if outdated:
            self.old_note.setText(tr("layer_old_vr", old=layer_install.installed_version() or "?", new=VERSION))
        full_w = SIDE_W - 2 * 14 - 2 * 16  # Seitenpanel minus Innenrand minus Knopf-Rand
        self.method_btn.setText(elide(tr("tr_m_" + cfg["tr_method"]), full_w - 48 - 10 - 30) + "  ▸")
        self.src_btn.setText(elide(language_name(cfg.get("tr_source", ""), True), full_w - 30) + "  ▸")
        self.dst_btn.setText("→  " + elide(language_name(cfg["tr_target"], False), full_w - 60) + "  ▸")
        self.mode_btn.setText(elide(p.mode_combo.currentText(), full_w - 30) + "  ▸")
        self.last_ai.setText(tr("tr_last_ai") + ":  " + p.last_ai_label.text())
        self.photo_pix = photo_with_numbers(photo, lines, self.content_w(PAGE_MAIN))  # Kasten: fill_pages
        prefix = "🔁 " + tr("live_title") + " · " if live else ""
        self.status.setText(prefix + p.tr_status.text())
        full = numbered(lines, p.tr_result) or ("…" if p.translating else "")
        if full != self.result_full:
            self.result_full, self.result_page = full, 0
        self.fill_pages()
        self.route_row.setVisible(self.choosing == "tr_method" and llm.is_llm(cfg["tr_method"]))
        self.mark(self.route_btns, translation.route_mode(cfg))
        if self.mode == "settings":
            self.fill_settings()
        self.fill_nav()
        if self.mode == "gallery":
            self.fill_gallery()
            self.fill_single()

    def fill_pages(self):
        """Foto-Kasten + Übersetzungs-Kasten auf ihre feste Größe bringen, lange Übersetzung in
        Seiten teilen, die in den Kasten passen (▼ / ▲ darunter)."""
        self.result.ensurePolished()
        self.status.ensurePolished()
        font = self.result.font()
        text_w = self.content_w(PAGE_MAIN) - 26  # Innenrand des Kastens
        lines = wrap_lines(self.result_full, font, text_w)
        line_h = max(1, QFontMetrics(font).lineSpacing())
        hide_photo = bool(layer_config.load().get("panel_hide_photo"))
        fixed = fixed_height_px(self.mode)
        area = PHOTO_MAX_H + 10 + RESULT_MAX_H + 48 + 10  # Foto + Übersetzung + ▲ ▼-Zeile
        if fixed is not None:
            # Höhe von Hand gezogen: Platz = was über den Kästen übrig bleibt
            self.photo_box.hide()
            self.result_box.hide()
            self.page_row.hide()
            pl = self.main_left.layout()
            pl.activate()
            used = pl.heightForWidth(self.content_w(PAGE_MAIN)) if pl.hasHeightForWidth() else pl.totalSizeHint().height()
            area = max(2 * 48, fixed - 32 - used - 10 - (NAV_H + 10))
        photo_h = 0 if hide_photo else min(PHOTO_MAX_H, int((area - 10) * 0.55))
        self.photo_box.setVisible(not hide_photo)
        self.photo_box.setFixedHeight(max(photo_h, 1))
        pix = self.photo_pix
        if pix is not None and pix.height() > photo_h - 2:  # von Hand kleiner gezogen → Foto kleiner
            pix = pix.scaledToHeight(max(1, photo_h - 2), Qt.TransformationMode.SmoothTransformation)
        self.photo.setPixmap(pix if pix is not None else QPixmap())
        box_h = area - (photo_h + 10 if not hide_photo else 0)
        status = self.status.text()
        status_h = 0
        if status:
            fm = QFontMetrics(self.status.font())
            status_h = fm.boundingRect(0, 0, text_w, 10000, Qt.TextFlag.TextWordWrap, status).height() + 8
        self.status.setVisible(bool(status))

        def per_page(h: int) -> int:
            return max(1, (h - 24 - 3 - status_h) // line_h)

        pages = paginate(lines, per_page(box_h))
        if len(pages) > 1:
            box_h -= 48 + 10
            pages = paginate(lines, per_page(box_h))
        self.result_box.setVisible(True)
        self.result_box.setFixedHeight(box_h)
        self.result_page = max(0, min(self.result_page, len(pages) - 1))
        self.result.setText(pages[self.result_page])
        self.result.setMinimumHeight(self.result.sizeHint().height())  # im festen Kasten nie zusammendrücken
        self.page_row.setVisible(len(pages) > 1)
        self.up_btn.setEnabled(self.result_page > 0)
        self.down_btn.setEnabled(self.result_page < len(pages) - 1)
        self.up_btn.setText("▲" if self.result_page > 0 else "")
        self.down_btn.setText("▼" if self.result_page < len(pages) - 1 else "")
        self.page_label.setText(f"{self.result_page + 1} / {len(pages)}")

    def turn_page(self, step: int):
        self.result_page += step

    def refresh(self, force: bool = False):
        if not enabled():
            if panel_file().exists():
                try:
                    panel_file().unlink()  # aus → aus VR verschwinden
                except OSError:
                    pass
            self.last_sig = None
            return
        sig = self.state()
        if sig == self.last_sig and not force:
            return
        self.last_sig = sig
        try:
            self.write(self.render())
        except Exception:  # noqa: BLE001 – das Panel darf die App nie stören
            logging.exception("VR-Panel konnte nicht gezeichnet werden")

    def render(self) -> QImage:
        """Inhalt füllen, Höhe anpassen, als Bild holen (mit Deckkraft)."""
        self.fill()
        # ⚙ Einstellungen: immer so hoch wie der Inhalt (Gruppen klappen auf und zu)
        fixed = None if self.stack.currentIndex() == PAGE_SETTINGS else fixed_height_px(self.mode)
        if fixed is None:
            self.fit_height()  # automatisch: so hoch wie der Inhalt
        else:
            self.setFixedHeight(fixed)  # in VR von Hand gezogen (Ecke oben links)
            self.layout().activate()
        # Foto / Seitenpanel gerade ein- oder ausgeblendet → Spalten neu verteilen, bevor das Bild entsteht
        for lay in (self.main_left.layout(), self.stack.currentWidget().layout(), self.layout()):
            lay.invalidate()
            lay.activate()
        img = self.grab().toImage()
        alpha = opacity()
        if alpha < 1.0:  # Deckkraft: ganzes Bild durchsichtiger
            faded = QImage(img.size(), QImage.Format.Format_ARGB32)
            faded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(faded)
            painter.setOpacity(alpha)
            painter.drawImage(0, 0, img)
            painter.end()
            img = faded
        return img

    def shrink_to_page(self, index: int):
        self.nav.setVisible(index in NAV_PAGES)  # Tabs nur auf den Hauptseiten
        for i in range(self.stack.count()):
            pol = QSizePolicy.Policy.Preferred if i == index else QSizePolicy.Policy.Ignored
            self.stack.widget(i).setSizePolicy(QSizePolicy.Policy.Preferred, pol)

    def fit_height(self):
        """Höhe passend zum Inhalt – mit Zeilenumbruch. QStackedWidget gibt die Höhe
        nicht weiter → direkt an der sichtbaren Seite messen."""
        page = self.stack.currentWidget()
        margins = self.layout().contentsMargins()
        inner = self.content_w()
        if self.stack.currentIndex() == PAGE_GALLERY:
            self.setFixedHeight(GALLERY_H)  # Galerie nutzt die ganze Fläche (Raster ist darauf gebaut)
            self.layout().activate()
            return
        pl = page.layout()
        pl.activate()
        h = pl.heightForWidth(inner) if pl.hasHeightForWidth() else pl.totalSizeHint().height()
        if self.nav.isVisible():
            h += NAV_H + self.layout().spacing()
        self.setFixedHeight(max(200, h + margins.top() + margins.bottom()))
        self.layout().activate()

    def write(self, img: QImage):
        target = panel_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(".panel.png.part")
        if img.save(str(tmp), "PNG"):
            os.replace(tmp, target)

    # ------------------------------------------------------------ Klicks
    def read_clicks(self):
        while self.udp.hasPendingDatagrams():
            data = bytes(self.udp.receiveDatagram().data()).decode("ascii", "replace").split()
            if len(data) == 3 and data[0] == "click":
                try:
                    self.click(float(data[1]), float(data[2]))
                except ValueError:
                    pass

    def click(self, u: float, v: float):
        """Klick an Stelle u/v (0..1) → echter Maus-Klick ins Fenster."""
        pos = QPointF(u * self.width(), v * self.height())
        target = self.childAt(pos.toPoint())
        if target is None:
            return
        local = target.mapFrom(self, pos.toPoint()).toPointF()
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            ev = QMouseEvent(kind, local, target.mapToGlobal(local), Qt.MouseButton.LeftButton,
                             Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress
                             else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
            QApplicationSend(target, ev)
        QTimer.singleShot(50, lambda: self.refresh(force=True))

    # ------------------------------------------------------------ Einstellungen
    def size_changed(self, cm: int):
        set_page_width_cm(self.size_page, cm)
        self.refresh(force=True)

    def set_toggle(self, key: str):
        """An/aus-Schalter in layer.json."""
        layer_config.update(key, not bool(layer_config.load().get(key, layer_config.DEFAULTS.get(key, True))))
        self.page.layer_changed.emit()

    def toggle_photo(self):
        """🖼 ▲ / ▼: Foto aus-/einblenden – ohne Foto nutzt die Übersetzung die ganze Fläche."""
        layer_config.update("panel_hide_photo", not layer_config.load().get("panel_hide_photo"))

    def toggle_side(self):
        """🌐 Seitenpanel rechts ein-/ausklappen (layer.json, gilt auch für den ⚙ Dienst)."""
        layer_config.update("panel_side_closed", not side_closed())

    def set_choice(self, key: str, value: str):
        if key == "panel_anchor":
            self.set_anchor(value)
        else:
            self.set_layer(key, value)

    def set_slider(self, item: dict, value: int):
        v = vr_settings.snap(item, value)
        if item["key"] == "@button_cm":
            set_button_cm(v)
        else:
            layer_config.update(item["key"], v)
            self.page.layer_changed.emit()
        self.refresh(force=True)

    def remove_from_list(self, key: str, name: str):
        """🚫 Ausnahme antippen = entfernen."""
        layer_config.update(key, [a for a in layer_config.load().get(key, []) if a != name])
        self.page.layer_changed.emit()

    def toggle_old_note(self):
        self.old_open = not self.old_open

    def toggle_rec(self):
        """🎞 GIF ↔ 🎬 VID aus VR."""
        layer_config.toggle_rec_video()
        self.page.layer_changed.emit()

    def set_anchor(self, anchor: str):
        if layer_config.load().get("panel_anchor") != anchor:
            layer_config.update("panel_anchor", anchor)
            reset_position()  # anderer Anker → Position passt nicht mehr: neu vor dem Kopf
            self.page.layer_changed.emit()

    def set_layer(self, key: str, value: str):
        layer_config.update(key, value)  # Auslöser ≠ Typ-Taste regelt update()
        self.page.layer_changed.emit()

    def toggle_edit(self):
        edit = bool(layer_config.load().get("panel_edit"))
        layer_config.update("panel_edit", not edit)
        self.page.layer_changed.emit()

    def set_route(self, route: str):
        """Dienst-Auswahl: Modus 🤖 Automatisch / ✋ Manuell (wie Optionen → Übersetzung)."""
        p = self.page
        translation.set_route(p.cfg, route)
        config.save(p.cfg)
        p.sync_model()
        p.settings_changed.emit()
        p.clear_translation()
        p.start_translation()

    def choose(self, key: str):
        """Auswahl-Liste im Panel öffnen (statt Dropdown)."""
        p = self.page
        combo = {"tr_method": p.method_combo, "tr_source": p.src_combo, "tr_target": p.dst_combo,
                 "tr_llm_mode": p.mode_combo}[key]
        self.choosing = key
        self.pick_title.setText({"tr_method": tr("tr_service"), "tr_source": tr("tr_source"),
                                 "tr_target": tr("tr_target"), "tr_llm_mode": tr("tr_task")}[key])
        self.pick_list.clear()
        from ui.widgets import is_header
        for i in range(combo.count()):
            if is_header(combo, i):  # ── KI-Übersetzung ── : nur Gliederung, nicht wählbar
                item = QListWidgetItem(combo.itemText(i))
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setForeground(QColor("#7a8290"))
                item.setData(Qt.ItemDataRole.UserRole, -1)
            else:
                item = QListWidgetItem(("✔  " if i == combo.currentIndex() else "     ") + combo.itemText(i))
                item.setData(Qt.ItemDataRole.UserRole, i)
            self.pick_list.addItem(item)
        rows = combo.count()
        self.pick_list.setFixedHeight(sum(self.pick_list.sizeHintForRow(i) for i in range(rows))
                                      + 2 * self.pick_list.frameWidth() + 6)
        self.stack.setCurrentIndex(PAGE_PICK)

    def picked(self, item):
        p = self.page
        combo = {"tr_method": p.method_combo, "tr_source": p.src_combo, "tr_target": p.dst_combo,
                 "tr_llm_mode": p.mode_combo}[self.choosing]
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None or index < 0:
            return  # Überschrift
        combo.setCurrentIndex(index)  # löst alles Weitere aus
        self.close_chooser()

    def close_chooser(self):
        self.choosing = None
        self.stack.setCurrentIndex(self.home_index())


def QApplicationSend(target, event):  # noqa: N802 – kurz und lesbar
    from PyQt6.QtWidgets import QApplication
    QApplication.sendEvent(target, event)


def live_photo() -> Path:
    from ui.pages.main_live import live_file
    return live_file()


def language_name(code: str, source: bool) -> str:
    from core import i18n
    for c, de, en in ([translation.AUTO] if source else []) + translation.LANGUAGES:
        if c == code:
            return de if i18n._lang == "de" else en
    return code or "auto"


def numbered(lines: list[dict], translated: str) -> str:
    """Übersetzung passend zu den Nummern im Foto: „① …“ je Zeile – sonst der Text so."""
    pairs = overlay.pair_lines(lines, translated) if translated else None
    if pairs is None:
        # KI-Antwort „➜ 4) …“ → „➜ ④ …“ (wie die Nummer am Foto)
        return re.sub(r"^(\s*➜\s*)(\d{1,2})[).:]\s*",
                      lambda m: m.group(1) + number(int(m.group(2)) - 1) + " ", translated.strip(), flags=re.M)
    return "\n".join(f"{number(i)}  {text}" for i, (_box, text) in enumerate(pairs))
