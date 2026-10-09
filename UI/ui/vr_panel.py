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
Fenster und nicht im Bild) · ↻ · ⚙ klappt wie beim Handy von oben die
Einstellungen auf: Größe, Deckkraft, Hängt an, ✥ Verschieben, ⟲ Position,
Erkennung & Tasten.

Seiten: 🌐 Übersetzung und 🖼 Galerie. Unten eine Zeile: ◀ links, ▶ rechts wechseln
die Seite, ⚙ bleibt oben. Jede Seite hat ihre eigene Größe in VR (panel_sizes.json) –
die Galerie ist standardmäßig größer. Galerie = Raster mit Vorschaubildern über die
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

from core import clipboard, config, layer_config, overlay, paths, share, tags, translation, uploader
from core import llm_translator as llm
from core.i18n import month_title, tr
from ui.style import STYLE

WIDTH = 720              # Pixel-Breite des Panel-Bilds (Höhe ergibt sich aus dem Inhalt)
PHOTO_MAX_H = 360        # so hoch darf das Foto im Panel höchstens werden
CHECK_MS = 400           # so oft schauen, ob sich etwas geändert hat
RESULT_MAX_H = 300       # Übersetzung höher → blättern (▼ / ▲)
SLIDE_STEPS = 4          # ⚙ Einstellungen gleiten in so vielen Bildern herein …
SLIDE_MS = 80            # … je so lange (der Layer schaut alle 80 ms nach)
SIZE_CM = (15, 80)       # Panel-Breite in VR (Schieber „Größe“)
BUTTON_CM = (2, 20)      # 🔘 Knopf-Durchmesser in VR (Schieber „Knopf-Größe“)
# 🔘 Knopf-Farben zum Antippen in VR (passend zu Hand-Overlays wie WayVR)
BUTTON_COLORS = ("#5b8dc9", "#9b6bd6", "#4caf7a", "#e0913a", "#d05a5a", "#6b7280", "#e5e9ef")
NAV_H = 52               # Zeile ganz unten: ◀ links, ▶ rechts (Seite wechseln)
GRID_COLS = 4            # Galerie: Vorschaubilder nebeneinander
GRID_GAP = 8
THUMB_RATIO = 0.75       # Höhe/Breite einer Kachel
MONTH_H = 34             # Höhe eines Monats-Trenners im Raster
GALLERY_H = 760          # Galerie ohne von Hand gezogene Höhe: so hoch wird das Panel
SINGLE_MAX_H = 360       # Einzelansicht: so hoch darf das Foto höchstens werden
GIF_MIN_FRAME_S = 0.125  # 🎞 GIF in VR: höchstens so oft ein neues Panel-Bild (der Layer schaut alle 80 ms)
PAGES = ("translate", "gallery")
PAGE_SIZE_DEFAULT = {"translate": 0.32, "gallery": 0.48}  # Breite in VR (m) je Seite
# Stapel-Seiten im Panel
PAGE_MAIN, PAGE_PICK, PAGE_SHEET, PAGE_GALLERY, PAGE_SINGLE, PAGE_SHARE, PAGE_INFO = range(7)
NAV_PAGES = (PAGE_MAIN, PAGE_GALLERY)  # nur hier ist die ◀ ▶-Zeile unten zu sehen
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


def fixed_height_px() -> int | None:
    """Höhe von Hand gezogen (Ecke oben links in VR)? → Pixel-Höhe passend dazu."""
    try:
        data = json.loads(pose_file().read_text(encoding="utf-8"))
        width, height = float(data["width"]), data.get("height")
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not height or width <= 0:
        return None
    return max(160, round(WIDTH * float(height) / width))


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
            #vrpanel { background: #161a22; border: 2px solid #2b3240; border-radius: 16px; }
            #vrpanel QPushButton { font-size: 20px; min-height: 48px; padding: 4px 14px; }
            #vrpanel QLabel { font-size: 20px; }
            #vrpanel QLabel#vrtitle { font-size: 24px; font-weight: bold; }
            #vrpanel QLabel#vrresult { font-size: 22px; }
            #vrpanel QLabel#vrsection { font-size: 17px; color: #aeb4bf; }
            #vrpanel QLabel#dim { font-size: 16px; }
            #vrpanel QPushButton#navbtn { font-size: 21px; font-weight: bold; min-height: 52px; max-height: 52px;
                                          border-radius: 12px; background: #232833; border: 1px solid #3a4252;
                                          color: #e5e9ef; padding: 0 18px; }
            #vrpanel QPushButton#navbtn:hover { background: #2f3542; border-color: #5b8dc9; }
            #vrpanel QPushButton#linkbtn:disabled { color: #3a4050; border-color: #262b35; background: #1b1f28; }
            #vrpanel QLabel#navdots { font-size: 18px; color: #5b8dc9; }
            #vrpanel QLabel#month { font-size: 18px; font-weight: bold; color: #c7cdd6; }
            #vrpanel QFrame#monthline { background: #333947; }
            #vrpanel QLabel#vrtoast { font-size: 18px; font-weight: bold; color: #6fae72; }
            #vrpanel QLabel#infokey { font-size: 17px; color: #aeb4bf; }
            #vrpanel QLabel#infoval { font-size: 19px; }
            #vrpanel QPushButton#thumb { padding: 0; min-height: 0; border: 2px solid #2b3240;
                                         border-radius: 8px; background: #14161c; }
            #vrpanel QListWidget { font-size: 22px; }
            #vrpanel QListWidget::item { min-height: 54px; }
        """)
        self.setFixedWidth(WIDTH)
        self.last_sig = None
        self.choosing = None     # welches Auswahl-Menü ist offen ("tr_method", …)
        self.result_full = ""    # ganze Übersetzung …
        self.result_page = 0     # … angezeigte Seite (▼ / ▲)
        self.slide = []          # ⚙ auf-/zuklappen: noch zu zeigende Bilder
        self.slide_timer = QTimer(self)
        self.slide_timer.timeout.connect(self.next_slide)
        self.mode = current_page()  # Hauptseite: "translate" / "gallery" (wie zuletzt)
        self.gal_page = 0        # Galerie: Seite im Raster
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
        # ganz unten: [◀ Galerie]   ● ○   [Galerie ▶] – Seite wechseln
        self.nav = QWidget()
        nrow = QHBoxLayout(self.nav)
        nrow.setContentsMargins(0, 0, 0, 0)
        nrow.setSpacing(10)
        self.nav_prev = self.button("", lambda: self.step_page(-1))
        self.nav_prev.setObjectName("navbtn")
        self.nav_prev.setMinimumWidth(230)
        nrow.addWidget(self.nav_prev)
        self.nav_dots = QLabel()
        self.nav_dots.setObjectName("navdots")
        self.nav_dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nrow.addWidget(self.nav_dots, 1)
        self.nav_next = self.button("", lambda: self.step_page(1))
        self.nav_next.setObjectName("navbtn")
        self.nav_next.setMinimumWidth(230)
        nrow.addWidget(self.nav_next)
        lay.addWidget(self.nav)
        # Höhe richtet sich nur nach der sichtbaren Seite
        self.stack.currentChanged.connect(self.shrink_to_page)

        # ---------- Seite 0: Übersetzung ----------
        main = QWidget()
        col = QVBoxLayout(main)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        head = QHBoxLayout()
        title = QLabel("🌐  ViewShot")
        title.setObjectName("vrtitle")
        head.addWidget(title, 1)
        head.addWidget(self.button("⚙", self.toggle_sheet, tip=True))
        col.addLayout(head)

        row = QHBoxLayout()
        self.method_btn = self.button("", lambda: self.choose("tr_method"))
        row.addWidget(self.method_btn, 1)
        self.redo_btn = self.button("↻", lambda: self.page.start_translation(force=True))
        row.addWidget(self.redo_btn)
        col.addLayout(row)
        row = QHBoxLayout()
        self.src_btn = self.button("", lambda: self.choose("tr_source"))
        row.addWidget(self.src_btn, 1)
        row.addWidget(QLabel("→"))
        self.dst_btn = self.button("", lambda: self.choose("tr_target"))
        row.addWidget(self.dst_btn, 1)
        col.addLayout(row)
        self.mode_btn = self.button("", lambda: self.choose("tr_llm_mode"))
        col.addWidget(self.mode_btn)
        self.last_ai = QLabel()  # „Letzte KI: …“ wie auf der Main-Seite
        self.last_ai.setObjectName("dim")
        col.addWidget(self.last_ai)
        # ✥ Verschieben an: kurze Anleitung (gelber Rand zeichnet der Layer)
        self.edit_help = QLabel("✥  " + tr("panel_edit_help"))
        self.edit_help.setObjectName("dim")
        self.edit_help.setWordWrap(True)
        col.addWidget(self.edit_help)

        self.photo = QLabel()
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.photo)
        self.result = QLabel()
        self.result.setObjectName("vrresult")
        self.result.setTextFormat(Qt.TextFormat.PlainText)
        col.addWidget(self.result)
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
        self.status = QLabel()
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        col.addWidget(self.status)
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

        # ---------- Seite 2: ⚙ Einstellungen (klappt von oben herunter) ----------
        self.stack.addWidget(self.build_sheet())

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

    def build_sheet(self) -> QWidget:
        sheet = QWidget()
        col = QVBoxLayout(sheet)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("⚙  " + tr("panel_settings"))
        title.setObjectName("vrtitle")
        head.addWidget(title, 1)
        head.addWidget(self.button("▲", self.toggle_sheet, tip=True))
        col.addLayout(head)

        def section(text: str) -> QLabel:
            label = QLabel(text)
            label.setObjectName("vrsection")
            return label

        # Größe (Breite in VR) + Deckkraft: Laser auf die Leiste = dieser Wert
        self.size_label = section("")
        col.addWidget(self.size_label)
        self.size_bar = ClickBar(*SIZE_CM, self.size_changed)
        col.addWidget(self.size_bar)
        self.opacity_label = section("")
        col.addWidget(self.opacity_label)
        self.opacity_bar = ClickBar(30, 100, self.opacity_changed)
        col.addWidget(self.opacity_bar)

        col.addWidget(section(tr("panel_anchor")))
        row, self.anchor_btns = self.choice_row(
            [(a, tr("panel_anchor_short_" + a)) for a in ("left", "right", "head", "world")], self.set_anchor)
        col.addWidget(row)
        row = QHBoxLayout()
        self.move_btn = self.button("", self.toggle_edit)
        row.addWidget(self.move_btn, 1)
        row.addWidget(self.button("⟲  " + tr("panel_reset"), reset_position))
        col.addLayout(row)

        # 🔘 Knopf: an/aus, nach Foto öffnen, Größe, Farbe
        col.addWidget(section(tr("panel_button")))
        row = QHBoxLayout()
        self.btn_on = self.button("", lambda: self.toggle_layer("panel_button"))
        row.addWidget(self.btn_on, 1)
        self.btn_auto = self.button("", lambda: self.toggle_layer("panel_open_on_shot"))
        row.addWidget(self.btn_auto, 1)
        col.addLayout(row)
        self.btn_size_label = section("")
        col.addWidget(self.btn_size_label)
        self.btn_size_bar = ClickBar(*BUTTON_CM, self.button_size_changed)
        col.addWidget(self.btn_size_bar)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.color_btns = {}
        for color in BUTTON_COLORS:
            b = self.button("", lambda c=color: self.set_layer("panel_button_color", c))
            b.setObjectName("swatch")
            b.setStyleSheet(f"QPushButton#swatch {{ background: {color}; border: 3px solid #2b3240; "
                            f"border-radius: 10px; min-height: 44px; font-size: 22px; color: #10131a; }}")
            row.addWidget(b, 1)
            self.color_btns[color] = b
        col.addLayout(row)

        # Erkennung & Tasten (wie Optionen → Shot)
        col.addWidget(section(tr("buttons_title")))
        row, self.detect_btns = self.choice_row(
            [("auto", tr("detect_short_auto")), ("manual", tr("detect_short_manual"))],
            lambda v: self.set_layer("detect_mode", v))
        col.addWidget(row)
        col.addWidget(section(tr("shutter")))
        row, self.shutter_btns = self.choice_row(
            [(c, tr("combo_short_" + c)) for c in layer_config.COMBOS], lambda v: self.set_layer("shutter", v))
        col.addWidget(row)
        col.addWidget(section(tr("mode_button")))
        row, self.mode_button_btns = self.choice_row(
            [(c, tr("combo_short_" + c)) for c in layer_config.COMBOS], lambda v: self.set_layer("mode_button", v))
        col.addWidget(row)
        return sheet

    # ------------------------------------------------------------ Seiten (◀ ▶ unten) + 🖼 Galerie
    def content_w(self, _index: int | None = None) -> int:
        """Breite des Inhalts (ohne Rand)."""
        return WIDTH - 36

    def home_index(self) -> int:
        """Stapel-Seite der aktuellen Hauptseite (dahin geht's nach ⚙ / Auswahl zurück)."""
        if self.mode == "gallery":
            return PAGE_SINGLE if self.gal_open is not None else PAGE_GALLERY
        return PAGE_MAIN

    def step_page(self, step: int):
        """◀ / ▶: andere Seite – mit ihrer eigenen Größe in VR."""
        old = self.mode
        self.mode = PAGES[(PAGES.index(self.mode) + step) % len(PAGES)]
        self.gal_open, self.gal_confirm, self.gal_toast = None, False, ""
        switch_page_size(old, self.mode)
        self.stack.setCurrentIndex(self.home_index())

    def page_name(self, page: str) -> str:
        return tr("vr_page_translate") if page == "translate" else tr("nav_gallery")

    def fill_nav(self):
        i = PAGES.index(self.mode)
        prev, nxt = PAGES[(i - 1) % len(PAGES)], PAGES[(i + 1) % len(PAGES)]
        self.nav_prev.setText("◀  " + self.page_name(prev))
        self.nav_next.setText(self.page_name(nxt) + "  ▶")
        self.nav_dots.setText("   ".join("●" if p == self.mode else "○" for p in PAGES))

    def head(self, title: QLabel, extra=()) -> QHBoxLayout:
        """Kopfzeile: Titel … [extra] [⚙] – ⚙ ist auf jeder Seite oben."""
        row = QHBoxLayout()
        title.setObjectName("vrtitle")
        row.addWidget(title, 1)
        for w in extra:
            row.addWidget(w)
        row.addWidget(self.button("⚙", self.toggle_sheet, tip=True))
        return row

    def build_gallery(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        # Kopf: 🖼 Galerie   [▲] 1 / 3 [▼]   [⚙]  – Blättern oben, ◀ ▶ bleiben unten frei
        self.gal_up = self.button("▲", lambda: self.gal_turn(-1), tip=True)
        self.gal_label = QLabel()
        self.gal_label.setObjectName("dim")
        self.gal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gal_label.setMinimumWidth(70)
        self.gal_down = self.button("▼", lambda: self.gal_turn(1), tip=True)
        col.addLayout(self.head(QLabel("🖼  " + tr("nav_gallery")), (self.gal_up, self.gal_label, self.gal_down)))
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
        return paths.gallery_photos(self.page.cfg)

    def thumb(self, photo: Path, w: int, h: int) -> QPixmap:
        """Vorschaubild w × h (Mitte ausgeschnitten, gleich große Kacheln) – gemerkt."""
        key = (str(photo), paths.photo_mtime(photo), w)
        pix = self.thumbs.get(key)
        if pix is None:
            reader = QImageReader(str(photo))
            size = reader.size()
            if size.isValid():  # gleich beim Laden verkleinern – viel schneller
                reader.setScaledSize(size.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
            img = reader.read()
            pix = QPixmap(w, h)
            pix.fill(QColor("#14161c"))
            if not img.isNull():
                painter = QPainter(pix)
                painter.drawImage((w - img.width()) // 2, (h - img.height()) // 2, img)
                painter.end()
            if len(self.thumbs) > 200:
                self.thumbs.clear()
            self.thumbs[key] = pix
        return pix

    @staticmethod
    def tile_size() -> tuple[int, int]:
        cw = (WIDTH - 36 - (GRID_COLS - 1) * GRID_GAP) // GRID_COLS
        return cw, round(cw * THUMB_RATIO)

    def grid_height(self) -> int:
        """So viel Platz hat das Raster: ganze Panel-Höhe minus Rand, Kopf und ◀ ▶-Zeile."""
        total = fixed_height_px() or GALLERY_H
        return max(MONTH_H + self.tile_size()[1], total - 32 - (48 + 10) - (NAV_H + 10))

    def gallery_pages(self, photos: list[Path]) -> list[list[tuple]]:
        """Fotos → Raster-Seiten. Jede Seite: Zeilen ("month", Text) / ("row", [Fotos]),
        so viele, wie in die Höhe passen. Ein Monat, der auf der neuen Seite weitergeht,
        bekommt oben nochmal seinen Trenner."""
        _cw, ch = self.tile_size()
        room = self.grid_height()
        rows = []  # (Monat, Zeile)
        month, cur = None, []
        for photo in photos:
            ym = paths.month_key(photo)
            if ym != month or len(cur) == GRID_COLS:
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
                self.gal_grid.addWidget(w, r, 0, 1, GRID_COLS)
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
        for c in range(GRID_COLS):
            self.gal_grid.setColumnMinimumWidth(c, cw)
        self.gal_host.setVisible(bool(photos))
        self.gal_empty.setVisible(not photos)
        many = len(pages) > 1
        for w in (self.gal_up, self.gal_label, self.gal_down):
            w.setVisible(many)
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
            pix = QPixmap(str(photo))
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
        if self.slide or not enabled() or not panel_open() or now - self.gif_written < GIF_MIN_FRAME_S:
            return  # ⚙ klappt gerade / Panel zu / zu schnell – dieses Bild auslassen
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
        old, self.mode = self.mode, PAGES[0]
        switch_page_size(old, self.mode)
        self.stack.setCurrentIndex(PAGE_MAIN)

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
        reader = QImageReader(str(photo))
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
        layer_keys = ("panel_opacity", "panel_edit", "panel_anchor", "detect_mode", "shutter", "mode_button",
                      "panel_button", "panel_open_on_shot", "panel_button_color")
        return (str(photo), mtime, pose, tuple(lcfg.get(k) for k in layer_keys), p.tr_result,
                p.tr_status.text(), p.cfg.get("tr_method"),
                p.cfg.get("tr_source"), p.cfg.get("tr_target"), p.cfg.get("tr_llm_mode"),
                p.cfg.get("tr_explain_method"), p.cfg.get("tr_answer_method"),
                p.cfg.get("tr_route"), p.cfg.get("tr_auto_once"), p.last_ai_label.text(),
                self.choosing, self.stack.currentIndex(), self.result_page,
                tuple(self.lines_for(photo, live)),
                self.mode, self.gal_page, str(self.gal_open), self.gal_confirm, self.gal_toast,
                tuple(sorted(map(str, self.uploading))), fixed_height_px(),
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
        self.edit_help.setVisible(bool(layer_config.load().get("panel_edit")))
        self.method_btn.setText(tr("tr_m_" + cfg["tr_method"]) + "  ▸")
        self.src_btn.setText(language_name(cfg.get("tr_source", ""), True) + "  ▸")
        self.dst_btn.setText(language_name(cfg["tr_target"], False) + "  ▸")
        self.mode_btn.setVisible(llm.has_tasks(cfg))  # 🤖 Auto / Aufgabe wählen
        self.mode_btn.setText(p.mode_combo.currentText() + "  ▸")
        self.last_ai.setText(tr("tr_last_ai") + ":  " + p.last_ai_label.text())
        pix = photo_with_numbers(photo, lines, self.content_w(PAGE_MAIN))
        self.photo.setVisible(pix is not None)
        if pix is not None:
            self.photo.setPixmap(pix)
            self.photo.setFixedHeight(pix.height())  # nie zusammendrücken
        prefix = "🔁 " + tr("live_title") + " · " if live else ""
        self.status.setText(prefix + p.tr_status.text())
        full = numbered(lines, p.tr_result) or ("…" if p.translating else "")
        if full != self.result_full:
            self.result_full, self.result_page = full, 0
        self.fill_pages()
        self.route_row.setVisible(self.choosing == "tr_method" and llm.is_llm(cfg["tr_method"]))
        self.mark(self.route_btns, translation.route_mode(cfg))
        self.fill_sheet()
        self.fill_nav()
        if self.mode == "gallery":
            self.fill_gallery()
            self.fill_single()

    def fill_pages(self):
        """Lange Übersetzung in Seiten teilen, die ins Panel passen (▼ / ▲)."""
        self.result.ensurePolished()
        font = self.result.font()
        lines = wrap_lines(self.result_full, font, self.content_w(PAGE_MAIN))
        line_h = max(1, QFontMetrics(font).lineSpacing())
        fixed = fixed_height_px()
        max_h = RESULT_MAX_H
        if fixed is not None:
            # Höhe von Hand gezogen: Platz = was übrig bleibt
            self.result.setText("")
            self.page_row.hide()
            pl = self.stack.widget(0).layout()
            pl.activate()
            used = pl.heightForWidth(self.content_w(PAGE_MAIN)) if pl.hasHeightForWidth() else pl.totalSizeHint().height()
            max_h = max(line_h * 2, fixed - 32 - used - 58 - (NAV_H + 10))  # ◀ ▶-Zeile unten
        pages = paginate(lines, max_h // line_h)
        self.result_page = max(0, min(self.result_page, len(pages) - 1))
        self.result.setText(pages[self.result_page])
        self.page_row.setVisible(len(pages) > 1)
        self.up_btn.setEnabled(self.result_page > 0)
        self.down_btn.setEnabled(self.result_page < len(pages) - 1)
        self.up_btn.setText("▲" if self.result_page > 0 else "")
        self.down_btn.setText("▼" if self.result_page < len(pages) - 1 else "")
        self.page_label.setText(f"{self.result_page + 1} / {len(pages)}")

    def turn_page(self, step: int):
        self.result_page += step

    def fill_sheet(self):
        lcfg = layer_config.load()
        cm = width_cm()
        # Größe gilt für die aktuelle Seite (Übersetzung / Galerie haben je ihre eigene)
        self.size_label.setText(f"{tr('panel_size')} · {self.page_name(self.mode)}" + (f":  {cm} cm" if cm else ""))
        self.size_bar.set_value(cm or round(0.32 * 100))
        self.size_bar.setEnabled(cm is not None)
        self.opacity_label.setText(f"{tr('panel_opacity')}:  {round(opacity() * 100)} %")
        self.opacity_bar.set_value(round(opacity() * 100))
        self.mark(self.anchor_btns, lcfg.get("panel_anchor", "left"))
        edit = bool(lcfg.get("panel_edit"))
        self.move_btn.setText(("✔  " if edit else "✥  ") + tr("panel_move"))
        self.mark({True: self.move_btn}, edit)
        on = bool(lcfg.get("panel_button", True))
        self.btn_on.setText(("✔  " if on else "✕  ") + tr("panel_button_short"))
        self.mark({True: self.btn_on}, on)
        auto = bool(lcfg.get("panel_open_on_shot", True))
        self.btn_auto.setText(("✔  " if auto else "✕  ") + tr("panel_open_on_shot_short"))
        self.mark({True: self.btn_auto}, auto)
        bcm = button_cm()
        self.btn_size_label.setText(tr("panel_button_size") + (f":  {bcm} cm" if bcm else f"  {tr('panel_size_later')}"))
        self.btn_size_bar.set_value(bcm or 3)
        self.btn_size_bar.setEnabled(bcm is not None)
        current = str(lcfg.get("panel_button_color", BUTTON_COLORS[0])).lower()
        for color, b in self.color_btns.items():
            b.setText("✔" if color == current else "")
        self.mark(self.detect_btns, lcfg.get("detect_mode"))
        self.mark(self.shutter_btns, lcfg.get("shutter"))
        self.mark(self.mode_button_btns, lcfg.get("mode_button"))

    def refresh(self, force: bool = False):
        if self.slide:
            return  # ⚙ klappt gerade auf/zu
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
        fixed = fixed_height_px()
        if fixed is None:
            self.fit_height()  # automatisch: so hoch wie der Inhalt
        else:
            self.setFixedHeight(fixed)  # in VR von Hand gezogen (Ecke oben links)
            self.layout().activate()
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
        self.nav.setVisible(index in NAV_PAGES)  # ◀ ▶ nur auf den Hauptseiten
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

    # ------------------------------------------------------------ ⚙ auf-/zuklappen
    def toggle_sheet(self):
        """⚙ Einstellungen gleiten wie beim Handy von oben herein (bzw. wieder hoch)."""
        if self.slide:
            return
        opening = self.stack.currentIndex() != PAGE_SHEET
        before = self.render()
        self.stack.setCurrentIndex(PAGE_SHEET if opening else self.home_index())
        after = self.render()
        sheet, base = (after, before) if opening else (before, after)
        size = after.size()
        frames = []
        for k in range(1, SLIDE_STEPS):
            t = k / SLIDE_STEPS
            shown = t if opening else 1 - t  # wie weit die Einstellungen schon unten sind
            frame = QImage(size, QImage.Format.Format_ARGB32)
            frame.fill(QColor("#161a22"))  # Panel-Hintergrund (Seiten sind verschieden hoch)
            p = QPainter(frame)
            p.drawImage(0, 0, base)
            p.drawImage(0, round(-(1 - shown) * sheet.height()), sheet)
            p.end()
            frames.append(frame)
        self.slide = frames + [after]
        self.last_sig = None
        self.next_slide()
        self.slide_timer.start(SLIDE_MS)

    def next_slide(self):
        if not self.slide:
            self.slide_timer.stop()
            return
        self.write(self.slide.pop(0))
        if not self.slide:
            self.slide_timer.stop()
            self.last_sig = self.state()

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
        if self.slide:
            return
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
        set_width_cm(cm)
        self.refresh(force=True)

    def button_size_changed(self, cm: int):
        set_button_cm(cm)
        self.refresh(force=True)

    def toggle_layer(self, key: str):
        """An/aus-Schalter in layer.json (🔘 Knopf, Nach Foto öffnen) – Standard an."""
        layer_config.update(key, not bool(layer_config.load().get(key, True)))
        self.page.layer_changed.emit()

    def opacity_changed(self, value: int):
        layer_config.update("panel_opacity", max(30, min(100, round(value / 10) * 10)))
        self.refresh(force=True)

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
