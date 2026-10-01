"""
ui/pages/gallery_page.py – Alle Fotos als gleich große Kacheln.

Klick auf ein Foto → große Ansicht mit ‹ › zum Blättern.
Über den Kacheln steht pro Monat ein Trenner („──── 2026 Oktober ────“).
⚙ oben: welche Ordner die Galerie zeigt (Foto-Ordner + z. B. ~/Bilder/VRChat),
je mit oder ohne Unterordner. Vorschaubilder laden im Hintergrund (viele Fotos!).
Tastatur in der großen Ansicht:  ← →  blättern,  Esc  zurück.

Die Seite hat zwei "Unterseiten" in einem QStackedWidget:
    0 = Raster (alle Fotos)
    1 = große Ansicht (ein Foto) mit Knopfleiste unten:
        Kopieren · Teilen · Hochladen & Link kopieren · Info
"""

import queue
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QBuffer, QEvent, QFile, QIODevice, QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QImage, QImageReader, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                             QSizePolicy, QSlider, QStackedWidget, QVBoxLayout, QWidget)

from core import clipboard, config, paths, share, tags, uploader
from core.i18n import month_title, tr
from ui.widgets import open_path, page_title

THUMB_MIN, THUMB_MAX = 120, 400  # Bereich des Größen-Sliders (Pixel)
TILE_BG = "#14161c"  # Hintergrund der Kachel (gleiche Farbe wie #photo)


def thumbnail_image(path, thumb: int) -> QImage:
    """Foto verkleinert, MITTIG in einem festen Quadrat (thumb × thumb) – alle Kacheln
    gleich groß, egal ob hoch oder breit. Nur QImage → geht auch im Hintergrund-Thread."""
    reader = QImageReader(str(path))
    size = reader.size()
    if size.isValid():
        # gleich beim Laden verkleinern – viel schneller als erst groß laden
        reader.setScaledSize(size.scaled(thumb, thumb, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    tile = QImage(thumb, thumb, QImage.Format.Format_ARGB32_Premultiplied)
    tile.fill(QColor(TILE_BG))
    painter = QPainter(tile)
    painter.drawImage((thumb - image.width()) // 2, (thumb - image.height()) // 2, image)
    painter.end()
    return tile


def load_thumbnail(path, thumb: int) -> QPixmap:
    return QPixmap.fromImage(thumbnail_image(path, thumb))


class ThumbLoader(QObject):
    """Lädt Vorschaubilder in einem Hintergrund-Thread (neueste zuerst) – die Galerie
    friert auch mit tausenden VRChat-Screenshots nicht ein."""
    loaded = pyqtSignal(object, object)  # (Schlüssel, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = queue.Queue()
        self.generation = 0
        threading.Thread(target=self._work, daemon=True).start()

    def request(self, keys: list):
        """Neue Liste → alte, noch nicht geladene Aufträge verfallen."""
        self.generation += 1
        for key in keys:
            self.jobs.put((self.generation, key))

    def _work(self):  # Hintergrund – KEINE Widgets anfassen!
        while True:
            gen, key = self.jobs.get()
            if gen != self.generation:
                continue
            path, _mtime, thumb = key
            try:
                image = thumbnail_image(path, thumb)
            except Exception:  # noqa: BLE001 – kaputtes Bild: Kachel bleibt leer
                continue
            self.loaded.emit(key, image)


def month_header(text: str) -> QWidget:
    """Trenner „──────── 2026 Oktober ────────“ über den Kacheln eines Monats."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(4, 10, 4, 2)
    row.setSpacing(14)
    def line() -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background: #333947;")
        return f

    label = QLabel(text)
    label.setObjectName("cardtitle")
    row.addWidget(line(), 1)
    row.addWidget(label)
    row.addWidget(line(), 1)
    return box


class FoldersDialog(QDialog):
    """⚙ Galerie-Ordner: Foto-Ordner (fest) + weitere Ordner, je „Unterordner einbeziehen“."""

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(tr("gallery_settings"))
        self.setMinimumWidth(640)
        self.folders = [dict(f) for f in (cfg.get("gallery_folders") or []) if isinstance(f, dict)]
        self.main_sub = bool(cfg.get("gallery_main_subfolders"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        title = QLabel("⚙  " + tr("gallery_folders"))
        title.setObjectName("cardtitle")
        lay.addWidget(title)
        hint = QLabel(tr("gallery_folders_hint"))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(8)
        lay.addLayout(self.list_box)
        row = QHBoxLayout()
        add = QPushButton("＋  " + tr("gallery_add_folder"))
        add.setObjectName("linkbtn")
        add.clicked.connect(self.add_folder)
        row.addWidget(add)
        row.addStretch()
        close = QPushButton(tr("close"))
        close.setObjectName("sendbtn")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.rebuild()

    def rebuild(self):
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        rows = [(None, paths.photo_dir(), self.main_sub)] + \
               [(i, Path(f["path"]), bool(f.get("subfolders"))) for i, f in enumerate(self.folders)]
        for n, (index, folder, sub) in enumerate(rows):
            card = QFrame()
            card.setObjectName("card")
            grid = QGridLayout(card)
            grid.setContentsMargins(14, 10, 14, 10)
            grid.setHorizontalSpacing(10)
            name = QLabel(f"{n + 1}:  {folder}")
            name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(name, 0, 0, 1, 3)
            if index is None:
                note = QLabel(tr("gallery_main_folder"))
                note.setObjectName("dim")
                grid.addWidget(note, 1, 0)
            check = QCheckBox(tr("gallery_subfolders"))
            check.setChecked(sub)
            check.toggled.connect(lambda on, i=index: self.set_sub(i, on))
            grid.addWidget(check, 1, 1 if index is None else 0)
            if index is not None:
                change = QPushButton(tr("gallery_change_folder"))
                change.setObjectName("linkbtn")
                change.clicked.connect(lambda _=False, i=index: self.change_folder(i))
                grid.addWidget(change, 1, 1)
                remove = QPushButton("✕  " + tr("gallery_remove_folder"))
                remove.setObjectName("dangerbtn")
                remove.clicked.connect(lambda _=False, i=index: self.remove_folder(i))
                grid.addWidget(remove, 1, 2)
            grid.setColumnStretch(0, 1)
            self.list_box.addWidget(card)

    def save(self):
        self.cfg["gallery_folders"] = self.folders
        self.cfg["gallery_main_subfolders"] = self.main_sub
        config.save(self.cfg)
        paths.forget_scan()

    def set_sub(self, index, on: bool):
        if index is None:
            self.main_sub = on
        else:
            self.folders[index]["subfolders"] = on
        self.save()

    def pick(self, start) -> str:
        return QFileDialog.getExistingDirectory(self, tr("gallery_add_folder"), str(start))

    def add_folder(self):
        folder = self.pick(Path.home() / "Bilder" if (Path.home() / "Bilder").is_dir() else Path.home())
        if folder and all(Path(f["path"]) != Path(folder) for f in self.folders) \
                and Path(folder) != paths.photo_dir():
            self.folders.append({"path": folder, "subfolders": True})
            self.save()
            self.rebuild()

    def change_folder(self, index: int):
        folder = self.pick(self.folders[index]["path"])
        if folder:
            self.folders[index]["path"] = folder
            self.save()
            self.rebuild()

    def remove_folder(self, index: int):
        del self.folders[index]
        self.save()
        self.rebuild()


class PhotoView(QLabel):
    """Zeigt EIN Foto so groß wie möglich und passt es bei Größenänderung an."""

    def __init__(self):
        super().__init__()
        self.setObjectName("photo")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # darf kleiner werden als das Bild, sonst wächst das Fenster mit
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._full = QPixmap()
        self.placeholder = ""  # Text, wenn kein Foto da ist

    def set_photo(self, path):
        """path = None → kein Foto (zeigt self.placeholder)."""
        self._full = QPixmap(str(path)) if path else QPixmap()
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._full.isNull():
            self.clear()
            self.setText(self.placeholder)
            return
        self.setPixmap(self._full.scaled(
            self.size() - QSize(16, 16), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))


def move_to_trash(path: Path) -> bool:
    """In den Papierkorb. Erst Qt, sonst gio (GNOME) bzw. kioclient (KDE)."""
    ok, _trash_path = QFile.moveToTrash(str(path))  # PyQt6 gibt (bool, Pfad) zurück!
    if ok:
        return True
    for cmd in (["gio", "trash", str(path)], ["kioclient", "move", str(path), "trash:/"]):
        if shutil.which(cmd[0]) and subprocess.run(cmd, capture_output=True).returncode == 0:
            return not path.exists()
    return False


class UploadSignals(QObject):
    """Brücke vom Hintergrund-Thread zur UI. Qt-Signale sind thread-sicher –
    Widgets dürfen NUR im Haupt-Thread angefasst werden."""
    done = pyqtSignal(str, dict)    # Foto-Pfad, Links
    failed = pyqtSignal(str, str)   # Foto-Pfad, Fehlertext
    checked = pyqtSignal(str, bool)       # Foto-Pfad, noch online?
    trashed = pyqtSignal(str, bool)       # Foto-Pfad, im Papierkorb?
    check_failed = pyqtSignal(str, str)   # Foto-Pfad, Fehlertext


def photo_taken(photo: Path) -> datetime:
    """Aufnahmezeit aus dem Dateinamen (ViewShot_2026-09-26_19-10-00.994.png),
    sonst Änderungsdatum der Datei."""
    try:
        return datetime.strptime(photo.stem.removeprefix("ViewShot_"), "%Y-%m-%d_%H-%M-%S.%f")
    except ValueError:
        return datetime.fromtimestamp(photo.stat().st_mtime)


class InfoDialog(QDialog):
    """Info zum Foto + Tags der Bild-Erkennung (anklicken = ändern)."""

    tags_changed = pyqtSignal(str)

    def __init__(self, photo: Path, tagger, parent=None):
        super().__init__(parent)
        self.photo = photo
        self.tagger = tagger
        self.setWindowTitle(tr("info"))
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        size = QImageReader(str(photo)).size()
        mb = photo.stat().st_size / 1024 / 1024
        taken = photo_taken(photo).strftime("%d.%m.%Y  %H:%M:%S")
        info = QLabel(
            f"<b>{tr('info_taken')}:</b> {taken}<br>"
            f"<b>{tr('info_resolution')}:</b> {size.width()} × {size.height()} px<br>"
            f"<b>{tr('info_size')}:</b> {mb:.2f} MB<br><br>"
            f"<span style='color:#7a8290'>{photo}</span>")
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(info)

        title = QLabel(tr("tags_title"))
        title.setObjectName("cardtitle")
        layout.addWidget(title)
        hint = QLabel(tr("tags_hint"))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # drei große Umschalt-Knöpfe (VR-freundlich)
        row = QHBoxLayout()
        self.tag_btns = {}
        for tag in tags.ALL:
            btn = QPushButton(f"{tags.ICONS[tag]}  {tr('tag_' + tag)}")
            btn.setObjectName("tabbtn")
            btn.setCheckable(True)
            btn.setMinimumHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(self.on_toggled)
            row.addWidget(btn)
            self.tag_btns[tag] = btn
        layout.addLayout(row)

        self.status = QLabel()
        self.status.setObjectName("dim")
        layout.addWidget(self.status)

        bottom = QHBoxLayout()
        self.redo_btn = QPushButton("↻  " + tr("tags_redo"))
        self.redo_btn.setObjectName("linkbtn")
        self.redo_btn.setMinimumHeight(40)
        self.redo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.redo_btn.clicked.connect(self.redo)
        self.redo_btn.setEnabled(tagger is not None)
        bottom.addWidget(self.redo_btn)
        bottom.addStretch()
        close = QPushButton(tr("close"))
        close.setObjectName("sendbtn")
        close.setMinimumHeight(40)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.load_tags()

    def load_tags(self):
        entry = tags.get(self.photo)
        for tag, btn in self.tag_btns.items():
            btn.setEnabled(entry is not None)
            btn.setChecked(bool(entry) and tag in entry["tags"])
        if entry is None:
            self.status.setText("⏳  " + tr("tags_pending"))
            # noch nicht dran? → nach vorne holen
            if self.tagger is not None:
                self.tagger.scan([self.photo])
        else:
            self.status.setText(tr("tags_manual") if entry["manual"] else tr("tags_auto"))

    def on_toggled(self):
        chosen = [t for t, b in self.tag_btns.items() if b.isChecked()]
        tags.set_tags(self.photo, chosen, manual=True)
        self.load_tags()
        self.tags_changed.emit(str(self.photo))
        if self.tagger is not None:
            self.tagger.tagged.emit(str(self.photo))  # Galerie-Kacheln/Filter anpassen

    def redo(self):
        self.tagger.redo(self.photo)
        self.load_tags()
        self.tags_changed.emit(str(self.photo))


class GalleryPage(QWidget):
    folders_changed = pyqtSignal()  # ⚙ Galerie-Ordner geändert → Hauptfenster beobachtet neue Ordner

    def __init__(self, cfg: dict, tagger=None):
        super().__init__()
        self.cfg = cfg
        # Bild-Erkennung im Hintergrund (gehört dem Hauptfenster, siehe core/tags.py)
        self.tagger = tagger
        self.info_dialog = None  # offenes Info-Fenster (für Live-Update der Tags)
        self.tag_filter = None   # None = alle, sonst "text" / "qr" / "image"
        self.selecting = False   # Auswahl-Modus für Mehrfach-Löschen
        self.checked = set()     # angehakte Fotos (Pfade)
        if tagger is not None:
            tagger.tagged.connect(self.on_tagged)
        self.thumb = max(THUMB_MIN, min(THUMB_MAX, int(cfg.get("thumb_size", 180))))
        self.photos = []     # Liste der Pfade, neueste zuerst
        self.items = {}      # Foto → Kachel im Raster (Trenner-Zeilen haben keine)
        self.current = 0     # welches Foto gerade groß angezeigt wird
        self.loader = ThumbLoader(self)  # Vorschaubilder im Hintergrund
        self.loader.loaded.connect(self.on_thumb_loaded)
        self.placeholder = None
        self.uploading = set()  # Fotos, die gerade hochgeladen werden

        self.signals = UploadSignals()
        self.signals.done.connect(self.on_upload_done)
        self.signals.failed.connect(self.on_upload_failed)
        self.signals.checked.connect(self.on_check_done)
        self.signals.check_failed.connect(self.on_check_failed)
        self.signals.trashed.connect(self.on_trashed)
        # fertige Vorschaubilder merken → Aktualisieren ist fast sofort fertig
        self.thumb_cache = {}  # (Pfad, Änderungszeit, Größe) → QIcon
        self.checking = set()  # Fotos, deren Upload gerade geprüft wird

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.stack.addWidget(self.build_grid())    # Index 0
        self.stack.addWidget(self.build_viewer())  # Index 1

        # Tastatur-Kürzel (nur aktiv, wenn die große Ansicht offen ist)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.step(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.step(+1))
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.show_grid)

        self.refresh()

    # ------------------------------------------------------------------
    # Unterseite 0: Raster
    # ------------------------------------------------------------------
    def build_grid(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(page_title(tr("nav_gallery")))
        head.addStretch()

        # Slider für die Kachelgröße – größer = in VR leichter zu treffen
        head.addWidget(QLabel("🔍 " + tr("tile_size")))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(THUMB_MIN, THUMB_MAX)
        self.size_slider.setSingleStep(20)
        self.size_slider.setPageStep(40)
        self.size_slider.setValue(self.thumb)
        self.size_slider.setFixedWidth(260)
        head.addWidget(self.size_slider)
        # erst neu laden, wenn der Slider kurz stillsteht (sonst ruckelt es beim Ziehen)
        self.resize_timer = QTimer(self, singleShot=True, interval=250, timeout=self.apply_thumb_size)
        self.size_slider.valueChanged.connect(lambda _: self.resize_timer.start())

        btn = QPushButton(tr("refresh"))
        btn.setObjectName("linkbtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.refresh)
        head.addWidget(btn)
        # ⚙ Welche Ordner zeigt die Galerie? (+ Unterordner)
        gear = QPushButton("⚙")
        gear.setObjectName("linkbtn")
        gear.setToolTip(tr("gallery_settings"))
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.clicked.connect(self.edit_folders)
        head.addWidget(gear)
        layout.addLayout(head)

        hint = QLabel(tr("gallery_hint"))
        hint.setObjectName("dim")
        layout.addWidget(hint)
        layout.addLayout(self.build_filter_bar())

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.set_grid_sizes()
        # kein festes Gitter: Monats-Trenner nehmen eine ganze Zeile ein
        self.grid.setFlow(QListWidget.Flow.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setSpacing(6)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.viewport().installEventFilter(self)  # Breite ändert sich → Trenner anpassen
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setWordWrap(False)
        self.grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.grid.itemClicked.connect(self.on_tile_clicked)
        layout.addWidget(self.grid, 1)

        # Rückmeldung unter den Kacheln (z. B. nach Mehrfach-Löschen)
        self.grid_toast = QLabel()
        self.grid_toast.setObjectName("toast")
        self.grid_toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.grid_toast)
        return page

    # ------------------------------------------------------------------
    # Filter (Alle / Text / QR / Bild) + Auswahl für Mehrfach-Löschen
    # ------------------------------------------------------------------
    def build_filter_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.filter_btns = {}
        for key, text in ((None, tr("filter_all")),
                          ("text", f"{tags.ICONS['text']}  {tr('tag_text')}"),
                          ("qr", f"{tags.ICONS['qr']}  {tr('tag_qr')}"),
                          ("image", f"{tags.ICONS['image']}  {tr('tag_image')}")):
            btn = QPushButton(text)
            btn.setObjectName("tabbtn")
            btn.setCheckable(True)
            btn.setChecked(key is None)
            btn.setMinimumHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self.set_filter(k))
            row.addWidget(btn)
            self.filter_btns[key] = btn
        row.addStretch()

        # normal:  [☑ Auswählen]
        # Auswahl: 3 ausgewählt  [Alle]  [🗑 Löschen (3)]  [Abbrechen]
        self.select_btn = self.make_bar_btn("☑  " + tr("select"), lambda: self.set_selecting(True))
        self.count_label = QLabel()
        self.all_btn = self.make_bar_btn(tr("select_all"), self.check_all)
        # 🏷 Typ ▾  → alle angehakten auf Text / QR-Code / Bild setzen
        self.type_btn = self.make_bar_btn("", None)
        type_menu = QMenu(self.type_btn)
        for tag in tags.ALL:
            type_menu.addAction(f"{tags.ICONS[tag]}  {tr('tag_' + tag)}",
                                lambda t=tag: self.set_type_checked(t))
        self.type_btn.setMenu(type_menu)
        self.mass_delete_btn = self.make_bar_btn("", self.delete_checked, "dangerbtn")
        self.mass_delete_btn.setStyleSheet("padding: 6px 16px; min-height: 26px; font-size: 14px;")
        self.cancel_btn = self.make_bar_btn(tr("cancel"), lambda: self.set_selecting(False))
        for w in (self.select_btn, self.count_label, self.all_btn, self.type_btn,
                  self.mass_delete_btn, self.cancel_btn):
            row.addWidget(w)
        return row

    def make_bar_btn(self, text: str, slot, style: str = "linkbtn") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(style)
        btn.setMinimumHeight(40)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if slot is not None:
            btn.clicked.connect(slot)
        return btn

    def set_filter(self, key):
        self.tag_filter = key
        for k, btn in self.filter_btns.items():
            btn.setChecked(k == key)
        self.refresh()

    def set_selecting(self, on: bool):
        self.selecting = on
        self.refresh()

    def on_tile_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return  # Monats-Trenner
        photo = Path(data)
        if self.selecting:
            # Klick irgendwo auf die Kachel = Häkchen an/aus (leichter in VR)
            self.checked ^= {photo}  # an ↔ aus
            item.setIcon(self.tile_icon(photo))
            self.update_select_bar()
        elif photo in self.photos:
            self.show_photo(self.photos.index(photo))

    def checked_photos(self) -> list[Path]:
        return [p for p in self.photos if p in self.checked]

    def check_all(self):
        # alle schon an? → alle aus, sonst alle an
        if len(self.checked_photos()) == len(self.photos):
            self.checked.clear()
        else:
            self.checked |= set(self.photos)
        for photo, item in self.items.items():
            item.setIcon(self.tile_icon(photo))
        self.update_select_bar()

    def tile_icon(self, photo: Path, key=None) -> QIcon:
        """Vorschaubild – angehakt mit rotem Rahmen und ✓ (groß, gut in VR zu sehen)."""
        if key is None:
            key = self.thumb_key(photo)
        icon = self.thumb_cache.get(key) or self.placeholder_icon()
        if not (self.selecting and photo in self.checked):
            return icon
        pix = icon.pixmap(self.thumb, self.thumb).copy()
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        red = QColor("#c95b5b")
        pen = painter.pen()
        pen.setColor(red)
        pen.setWidth(8)
        painter.setPen(pen)
        painter.drawRect(4, 4, pix.width() - 8, pix.height() - 8)
        size = max(34, self.thumb // 5)
        painter.setBrush(red)
        painter.drawEllipse(10, 10, size, size)
        pen.setColor(QColor("white"))
        painter.setPen(pen)
        font = painter.font()
        font.setPixelSize(int(size * 0.7))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(10, 10, size, size, Qt.AlignmentFlag.AlignCenter, "✓")
        painter.end()
        return QIcon(pix)

    def update_select_bar(self):
        n = len(self.checked_photos()) if self.selecting else 0
        self.select_btn.setVisible(not self.selecting)
        for w in (self.count_label, self.all_btn, self.type_btn,
                  self.mass_delete_btn, self.cancel_btn):
            w.setVisible(self.selecting)
        self.type_btn.setText(f"🏷  {tr('set_type')} ({n})  ▾")
        self.type_btn.setEnabled(n > 0)
        self.count_label.setText(tr("selected_count", n=n))
        self.mass_delete_btn.setText(f"🗑  {tr('delete')} ({n})")
        self.mass_delete_btn.setEnabled(n > 0)

    def set_type_checked(self, tag: str):
        """Alle angehakten Fotos bekommen genau diesen Typ (wie von Hand im Info-Fenster)."""
        photos = self.checked_photos()
        for photo in photos:
            tags.set_tags(photo, [tag], manual=True)
        # Auswahl bleibt, Kacheln/Filter neu (bei Filter können Fotos rausfallen)
        self.refresh()
        self.notify(tr("type_set", n=len(photos), tag=f"{tags.ICONS[tag]} {tr('tag_' + tag)}"))

    def delete_checked(self):
        photos = self.checked_photos()
        if not photos:
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("delete_title"))
        box.setText(tr("delete_many_question", n=len(photos)))
        yes = box.addButton(tr("yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(tr("no"), QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        # sofort aus der Anzeige, Papierkorb im Hintergrund (wie beim Einzel-Löschen)
        self.selecting = False
        self.checked.clear()
        # Liste ohne die gelöschten neu aufbauen (Dateien verschwinden im Hintergrund)
        self.refresh()
        self.photos = [p for p in self.photos if p not in photos]
        self.rebuild_grid()
        self.notify(tr("deleted_many", n=len(photos)))

        def work():  # Hintergrund – KEINE Widgets anfassen!
            for photo in photos:
                self.signals.trashed.emit(str(photo), move_to_trash(photo))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------
    # Unterseite 1: große Ansicht
    # ------------------------------------------------------------------
    def build_viewer(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Kopfzeile: Zurück | Name + "3 / 42" | Öffnen
        head = QHBoxLayout()
        back = QPushButton("←  " + tr("back"))
        back.setObjectName("linkbtn")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.show_grid)
        head.addWidget(back)
        head.addStretch()
        self.viewer_title = QLabel()
        self.viewer_title.setObjectName("cardtitle")
        head.addWidget(self.viewer_title)
        head.addStretch()
        ext = QPushButton(tr("open_external"))
        ext.setObjectName("linkbtn")
        ext.setCursor(Qt.CursorShape.PointingHandCursor)
        ext.clicked.connect(lambda: open_path(self.photos[self.current]))
        head.addWidget(ext)
        layout.addLayout(head)

        # Mitte: ‹  Foto  ›
        row = QHBoxLayout()
        row.setSpacing(12)
        self.prev_btn = self.make_arrow("‹", -1)
        self.next_btn = self.make_arrow("›", +1)
        self.view = PhotoView()
        row.addWidget(self.prev_btn)
        row.addWidget(self.view, 1)
        row.addWidget(self.next_btn)
        layout.addLayout(row, 1)

        # Unten: große Knöpfe (gut mit dem VR-Laser zu treffen)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addStretch()
        copy_btn = self.make_action("📋  " + tr("copy"), self.copy_photo)
        self.share_btn = self.make_action("↗  " + tr("share"), None)
        self.share_btn.setMenu(QMenu(self.share_btn))
        self.share_btn.menu().aboutToShow.connect(self.fill_share_menu)
        self.upload_btn = self.make_action("☁  " + tr("upload"), self.upload_photo)
        info_btn = self.make_action("ⓘ  " + tr("info"), self.show_info)
        delete_btn = self.make_action("🗑  " + tr("delete"), self.delete_photo)
        delete_btn.setObjectName("dangerbtn")  # wird beim Drüberfahren rot
        # nur sichtbar, wenn das Foto hochgeladen wurde
        self.check_btn = self.make_action("↻  " + tr("check_upload"), self.check_upload)
        for b in (copy_btn, self.share_btn, self.upload_btn, info_btn, delete_btn, self.check_btn):
            bar.addWidget(b)
        bar.addStretch()
        layout.addLayout(bar)

        # Rückmeldung ("Kopiert!" usw.), verschwindet nach 3 s
        self.toast = QLabel()
        self.toast.setObjectName("toast")
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_timer = QTimer(self, singleShot=True,
                                  timeout=lambda: (self.toast.clear(), self.grid_toast.clear()))
        layout.addWidget(self.toast)

        layout.addWidget(self.build_link_panel())
        return page

    def make_action(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text.replace("&", "&&"))  # "&" wäre sonst ein Tastenkürzel-Unterstrich
        btn.setObjectName("actionbtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # nie schmaler als der Text → Beschriftung wird nicht abgeschnitten
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        if slot:
            btn.clicked.connect(slot)
        return btn

    def build_link_panel(self) -> QFrame:
        """Kasten mit Bild-Link und Lösch-Link (nur sichtbar nach dem Upload)."""
        self.link_panel = QFrame()
        self.link_panel.setObjectName("card")
        grid = QGridLayout(self.link_panel)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(10)
        self.link_fields = {}
        for row, (key, label) in enumerate([("view", tr("link_view")), ("delete", tr("link_delete"))]):
            grid.addWidget(QLabel(label), row, 0)
            field = QLineEdit()
            field.setReadOnly(True)
            grid.addWidget(field, row, 1)
            btn = QPushButton(tr("copy"))
            btn.setObjectName("linkbtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.clicked.connect(lambda _, f=field: self.copy_text(f.text()))
            grid.addWidget(btn, row, 2)
            self.link_fields[key] = field
        grid.setColumnStretch(1, 1)
        self.link_panel.hide()
        return self.link_panel

    def set_grid_sizes(self):
        # jede Kachel gleich groß (sizeHint) → saubere Reihen; Trenner = ganze Breite
        self.grid.setIconSize(QSize(self.thumb, self.thumb))
        self.placeholder = None

    def placeholder_icon(self) -> QIcon:
        """Leere Kachel, bis das Vorschaubild im Hintergrund fertig ist."""
        if self.placeholder is None:
            pix = QPixmap(self.thumb, self.thumb)
            pix.fill(QColor(TILE_BG))
            self.placeholder = QIcon(pix)
        return self.placeholder

    def thumb_key(self, photo: Path):
        return (str(photo), paths.photo_mtime(photo), self.thumb)

    def on_thumb_loaded(self, key, image: QImage):
        self.thumb_cache[key] = QIcon(QPixmap.fromImage(image))
        photo = Path(key[0])
        item = self.items.get(photo)
        if item is not None and key[2] == self.thumb:
            item.setIcon(self.tile_icon(photo, key))

    def header_width(self) -> int:
        return max(200, self.grid.viewport().width() - 2 * self.grid.spacing() - 4)

    def eventFilter(self, obj, event):  # noqa: N802 – Qt-Name
        if obj is self.grid.viewport() and event.type() == QEvent.Type.Resize:
            w = self.header_width()
            for i in range(self.grid.count()):
                item = self.grid.item(i)
                if not item.data(Qt.ItemDataRole.UserRole):
                    item.setSizeHint(QSize(w, 46))
        return super().eventFilter(obj, event)

    def edit_folders(self):
        FoldersDialog(self.cfg, self).exec()
        self.folders_changed.emit()
        self.refresh()

    def apply_thumb_size(self):
        self.thumb = self.size_slider.value()
        self.cfg["thumb_size"] = self.thumb
        config.save(self.cfg)
        self.set_grid_sizes()
        self.refresh()

    def make_arrow(self, text: str, direction: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("arrowbtn")
        btn.setFixedWidth(52)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.step(direction))
        return btn

    # ------------------------------------------------------------------
    # Logik
    # ------------------------------------------------------------------
    def refresh(self):
        if not self.selecting:
            self.checked.clear()
        self.photos = paths.gallery_photos(self.cfg, fresh=True)
        if self.tag_filter is not None:
            wanted = self.tag_filter
            self.photos = [p for p in self.photos
                           if wanted in (tags.get(p) or {}).get("tags", [])]
        self.rebuild_grid()
        # große Ansicht offen, aber Foto weg (gelöscht)? → zurück zum Raster
        if self.stack.currentIndex() == 1:
            if not self.photos:
                self.show_grid()
            else:
                self.show_photo(min(self.current, len(self.photos) - 1))

    def rebuild_grid(self):
        """Kacheln aus self.photos – mit Monats-Trenner, Vorschaubilder im Hintergrund."""
        scroll = self.grid.verticalScrollBar().value()
        self.grid.clear()
        self.items = {}
        missing = []
        month = None
        for photo in self.photos:
            ym = paths.month_key(photo)
            if ym != month:  # neuer Monat → Trenner über die ganze Breite
                month = ym
                head = QListWidgetItem()
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                head.setSizeHint(QSize(self.header_width(), 46))
                self.grid.addItem(head)
                self.grid.setItemWidget(head, month_header(month_title(*ym)))
            key = self.thumb_key(photo)
            if key not in self.thumb_cache:
                missing.append(key)
            item = QListWidgetItem(self.tile_icon(photo, key), self.tile_text(photo))
            item.setData(Qt.ItemDataRole.UserRole, str(photo))
            item.setToolTip(str(photo))
            item.setSizeHint(QSize(self.thumb + 20, self.thumb + 36))
            self.grid.addItem(item)
            self.items[photo] = item
        self.loader.request(missing)
        self.grid.verticalScrollBar().setValue(scroll)
        self.update_select_bar()

    def show_photo(self, index: int):
        if not self.photos:
            return
        self.current = index
        photo = self.photos[index]
        self.view.set_photo(photo)
        name = photo.stem.removeprefix("ViewShot_")
        self.viewer_title.setText(f"{name}    {index + 1} / {len(self.photos)}    ·  {month_title(*paths.month_key(photo))}")
        # am Anfang/Ende den jeweiligen Pfeil ausgrauen
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < len(self.photos) - 1)
        self.update_upload_state()
        self.stack.setCurrentIndex(1)

    def step(self, direction: int):
        """Ein Foto weiter (+1) oder zurück (-1) – nur in der großen Ansicht."""
        if self.stack.currentIndex() != 1:
            return
        new = self.current + direction
        if 0 <= new < len(self.photos):
            self.show_photo(new)

    def show_grid(self):
        self.stack.setCurrentIndex(0)
        # das zuletzt angesehene Foto im Raster markieren
        if self.photos:
            item = self.items.get(self.photos[min(self.current, len(self.photos) - 1)])
            if item is not None:
                self.grid.setCurrentItem(item)

    # ------------------------------------------------------------------
    # Knopfleiste
    # ------------------------------------------------------------------
    def photo(self) -> Path:
        return self.photos[self.current]

    def notify(self, text: str):
        self.toast.setText(text)
        self.grid_toast.setText(text)
        self.toast_timer.start(3000)

    def copy_text(self, text: str):
        clipboard.set_text(text)
        self.notify(tr("copied_link"))

    def copy_photo(self):
        """Bild in die Zwischenablage – als Bild UND als Datei (für Dolphin).
        clipboard gibt es zusätzlich an den Desktop (wichtig in WayVR)."""
        clipboard.set_image(self.photo())
        self.notify(tr("copied_image"))

    def fill_share_menu(self):
        """Menü wird bei jedem Öffnen neu gebaut → neu installierte Programme erscheinen."""
        menu = self.share_btn.menu()
        menu.clear()
        targets = share.available()
        if not targets:
            menu.addAction(tr("share_none")).setEnabled(False)
        for key, name in targets:
            menu.addAction(name, lambda k=key: self.share_to(k))

    def share_to(self, key: str):
        if key == "discord":
            self.copy_photo()  # Discord kann nur einfügen
        try:
            kind = share.share(key, self.photo())
        except Exception as e:  # noqa: BLE001 – Fehler nur anzeigen
            self.notify(f"{tr('share_failed')}: {e}")
            return
        self.notify(tr("share_paste") if kind == "paste" else tr("share_opened"))

    def upload_photo(self):
        photo = self.photo()
        links = uploader.saved_links(photo)
        if links:  # schon hochgeladen → nur Link kopieren
            self.copy_text(links["view"])
            return
        if photo in self.uploading:
            return

        # Bild laden; über 8 MB → als JPG verkleinern (Limit der Seite)
        data, mime = photo.read_bytes(), "image/png"
        if len(data) > uploader.MAX_BYTES:
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            QImage(str(photo)).save(buf, "JPG", 92)
            data, mime = bytes(buf.data()), "image/jpeg"

        self.uploading.add(photo)
        self.update_upload_state()

        def work():  # läuft im Hintergrund, KEINE Widgets anfassen!
            try:
                links = uploader.upload(photo, data, mime)
                self.signals.done.emit(str(photo), links)
            except Exception as e:  # noqa: BLE001
                self.signals.failed.emit(str(photo), str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_upload_done(self, photo: str, links: dict):
        self.uploading.discard(Path(photo))
        if self.photos and str(self.photo()) == photo:
            clipboard.set_text(links["view"])
            self.notify(tr("upload_done"))
        self.update_upload_state()

    def on_upload_failed(self, photo: str, error: str):
        self.uploading.discard(Path(photo))
        self.update_upload_state()
        self.notify(f"{tr('upload_failed')}: {error}")

    def update_upload_state(self):
        """Upload-Knopf und Link-Kasten passend zum aktuellen Foto."""
        if not self.photos:
            return
        photo = self.photo()
        busy = photo in self.uploading
        links = uploader.saved_links(photo)
        self.upload_btn.setEnabled(not busy)
        if busy:
            self.upload_btn.setText("⏳  " + tr("uploading"))
        elif links:
            self.upload_btn.setText("🔗  " + tr("copy_link"))
        else:
            self.upload_btn.setText("☁  " + tr("upload").replace("&", "&&"))
        self.link_panel.setVisible(bool(links))
        self.check_btn.setVisible(bool(links))
        busy_check = photo in self.checking
        self.check_btn.setEnabled(not busy_check)
        self.check_btn.setText("⏳  " + tr("checking") if busy_check else "↻  " + tr("check_upload"))
        if links:
            self.link_fields["view"].setText(links["view"])
            self.link_fields["delete"].setText(links["delete"])

    def show_info(self):
        photo = self.photo()
        self.info_dialog = InfoDialog(photo, self.tagger, self)
        self.info_dialog.exec()
        self.info_dialog = None

    # ------------------------------------------------------------------
    # Tags (Bild-Erkennung): Symbole auf den Kacheln
    # ------------------------------------------------------------------
    @staticmethod
    def tile_text(photo: Path) -> str:
        """Name unter der Kachel, davor die Tag-Symbole (📝 🔳 🖼)."""
        name = photo.stem.removeprefix("ViewShot_")
        entry = tags.get(photo)
        if not entry:
            return name
        return " ".join(tags.ICONS[t] for t in entry["tags"]) + "  " + name

    def update_tile(self, photo: Path):
        item = self.items.get(photo)
        if item is not None:
            item.setText(self.tile_text(photo))

    def on_tagged(self, photo: str):
        if self.tag_filter is not None and self.stack.currentIndex() == 0:
            self.refresh()  # passt das Foto noch (nicht mehr) zum Filter?
        else:
            self.update_tile(Path(photo))
        if self.info_dialog is not None and self.info_dialog.photo == Path(photo):
            self.info_dialog.load_tags()

    def delete_photo(self):
        """Foto in den Papierkorb (nicht endgültig) – vorher nachfragen."""
        photo = self.photo()
        box = QMessageBox(self)
        box.setWindowTitle(tr("delete_title"))
        box.setText(tr("delete_question", name=photo.name))
        yes = box.addButton(tr("yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(tr("no"), QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is not yes:
            return

        # SOFORT aus der Anzeige nehmen und zum nächsten Foto springen –
        # das eigentliche Verschieben in den Papierkorb läuft im Hintergrund.
        index = self.current
        del self.photos[index]
        self.rebuild_grid()  # Trenner eines leer gewordenen Monats fällt mit weg
        paths.forget_scan()
        if self.photos:
            self.show_photo(min(index, len(self.photos) - 1))
        else:
            self.show_grid()
        self.notify(tr("deleted", name=photo.stem.removeprefix("ViewShot_")))

        def work():  # Hintergrund – KEINE Widgets anfassen!
            self.signals.trashed.emit(str(photo), move_to_trash(photo))

        threading.Thread(target=work, daemon=True).start()

    def on_trashed(self, photo: str, ok: bool):
        if not ok:
            # hat nicht geklappt → Foto kommt zurück in die Liste
            self.notify(tr("delete_failed"))
            self.refresh()

    def check_upload(self):
        """Prüft online, ob das hochgeladene Bild noch existiert (im Hintergrund)."""
        photo = self.photo()
        links = uploader.saved_links(photo)
        if not links or photo in self.checking:
            return
        self.checking.add(photo)
        self.update_upload_state()

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                self.signals.checked.emit(str(photo), uploader.is_online(links["view"]))
            except Exception as e:  # noqa: BLE001
                self.signals.check_failed.emit(str(photo), str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_check_done(self, photo: str, online: bool):
        self.checking.discard(Path(photo))
        if online:
            self.notify(tr("still_online"))
        else:
            # online gelöscht → Links vergessen, Upload-Knopf kommt zurück
            uploader.forget(Path(photo))
            self.notify(tr("was_deleted"))
        self.update_upload_state()

    def on_check_failed(self, photo: str, error: str):
        self.checking.discard(Path(photo))
        self.update_upload_state()
        self.notify(f"{tr('check_failed')}: {error}")
