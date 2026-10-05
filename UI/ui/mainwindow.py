"""
ui/mainwindow.py – Hauptfenster: Seitenleiste links, Seiten rechts daneben.

    ┌──────────┬──────────────────────────┐
    │ Main     │                          │
    │ Galerie  │   aktuelle Seite         │
    │ Optionen │   (QStackedWidget)       │
    └──────────┴──────────────────────────┘

Neue Seite? 1) Datei in ui/pages/ anlegen  2) unten in PAGES eintragen
            3) Text für den Knopf in core/i18n.py eintragen.
"""

import os

from PyQt6.QtCore import QFileSystemWatcher, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                             QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from core import config, i18n, paths, tags
from core.i18n import tr
from ui.pages.gallery_page import GalleryPage
from ui.pages.main_page import MainPage
from core.version import VERSION
from ui.pages.options_page import OptionsPage
from ui.style import STYLE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        i18n.set_language(self.cfg["language"])

        self.setWindowTitle("LinuxVR-ViewShot")
        self.resize(1200, 780)
        self.setMinimumSize(760, 520)
        self.setStyleSheet(STYLE)

        # Foto-Ordner beobachten → neue Fotos erscheinen sofort in der UI
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.on_photos_changed)
        self._waits = 0  # wie oft auf ein halb geschriebenes Foto gewartet wurde
        folder = paths.photo_dir()
        folder.mkdir(parents=True, exist_ok=True)
        self.watcher.addPath(str(folder))

        # Bild-Erkennung (Text / QR / Bild) im Hintergrund – überlebt den
        # Neuaufbau beim Sprachwechsel, darum hier und nicht in der Galerie
        self.tagger = tags.Tagger(self)

        self.build_ui()
        self.tagger.scan(paths.list_photos())
        # 👋 erster Start: kurz erklären, installieren lassen, zu den Übersetzern führen
        from ui import welcome
        welcome.maybe_start(self)

    # ------------------------------------------------------------------
    def build_ui(self, page_index: int = 0, options_tab: int = 0):
        """Baut alles auf. Wird beim Sprachwechsel nochmal aufgerufen."""
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ===== Seitenleiste (links) =====
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)  # breit genug für große Knöpfe (VR)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 20, 12, 12)
        side.setSpacing(10)

        # Icon + Name (auf zwei Zeilen, damit er in die schmale Leiste passt)
        head = QHBoxLayout()
        head.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QIcon(str(paths.APP_ICON)).pixmap(52, 52))
        logo.setFixedSize(52, 52)
        head.addWidget(logo, alignment=Qt.AlignmentFlag.AlignTop)
        title = QLabel('LinuxVR<br><span style="color:#5b8dc9">ViewShot</span>')
        title.setObjectName("apptitle")
        head.addWidget(title, 1)
        side.addLayout(head)

        # ===== Seiten (rechts daneben) =====
        self.main_page = MainPage(self.cfg, self.tagger)
        self.gallery_page = GalleryPage(self.cfg, self.tagger)
        self.gallery_page.folders_changed.connect(self.watch_gallery_folders)
        self.watch_gallery_folders()
        self.options_page = OptionsPage(self.cfg, options_tab)
        self.options_page.language_changed.connect(self.on_language_changed)
        self.options_page.translation_changed.connect(self.main_page.on_options_changed)
        self.main_page.settings_changed.connect(self.options_page.sync_translation)
        self.main_page.layer_changed.connect(self.options_page.sync_layer)
        self.options_page.layer_changed.connect(self.main_page.sync_detect)

        # (Text-Schlüssel, Seite) – Reihenfolge = Reihenfolge der Knöpfe
        PAGES = [
            ("nav_main", self.main_page),
            ("nav_gallery", self.gallery_page),
            ("nav_options", self.options_page),
        ]

        self.pages = QStackedWidget()
        self.nav_buttons = []
        for i, (key, page) in enumerate(PAGES):
            btn = QPushButton(tr(key))
            btn.setObjectName("navbtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # idx=i merkt sich die Nummer DIESES Knopfs
            btn.clicked.connect(lambda _, idx=i: self.switch_page(idx))
            side.addWidget(btn)
            self.nav_buttons.append(btn)

            # Die Galerie scrollt selbst, die anderen Seiten brauchen eine ScrollArea
            if page is self.gallery_page:
                self.pages.addWidget(page)
            else:
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setWidget(page)
                self.pages.addWidget(scroll)

        side.addStretch()
        version = QLabel(f"v{VERSION}")
        version.setObjectName("dim")
        side.addWidget(version)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)  # altes Widget wird dabei automatisch gelöscht
        self.switch_page(page_index)

    def switch_page(self, index: int):
        # Klick auf "Galerie" (auch wenn man schon dort ist) → zurück zu den Kacheln.
        # Praktisch in VR: kein Esc nötig.
        if self.pages.widget(index) is self.gallery_page:
            self.gallery_page.show_grid()
        self.pages.setCurrentIndex(index)
        # nur der aktive Knopf ist "gedrückt"
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    # ------------------------------------------------------------------
    def watch_gallery_folders(self):
        """Weitere Galerie-Ordner (⚙ in der Galerie) auch beobachten – mit Unterordnern
        alle Ordner darin (z. B. VRChat/2026-10), damit neue Bilder sofort erscheinen."""
        keep = {str(paths.photo_dir())}
        for folder, sub in paths.gallery_folders(self.cfg)[1:]:
            if not folder.is_dir():
                continue
            keep.add(str(folder))
            if sub:
                for root, dirs, _files in os.walk(folder):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    if root.count(os.sep) - str(folder).count(os.sep) >= paths.MAX_DEPTH:
                        dirs[:] = []
                    keep.add(root)
                    if len(keep) > 500:  # Grenze: Beobachten kostet je Ordner ein Handle
                        break
        old = set(self.watcher.directories())
        if old - keep:
            self.watcher.removePaths(list(old - keep))
        if keep - old:
            self.watcher.addPaths(sorted(keep - old))

    def on_photos_changed(self, _path=None):
        # Der Ordner meldet ein neues Foto schon beim Anlegen. Ist es noch nicht
        # fertig geschrieben (ältere Layer), kurz warten und nochmal – sonst
        # blieben leere Vorschaubilder hängen (danach meldet der Ordner nichts mehr).
        photos = paths.list_photos()
        if photos and not paths.photo_ready(photos[0]) and self._waits < 40:
            self._waits += 1
            QTimer.singleShot(250, self.on_photos_changed)
            return
        self._waits = 0
        self.main_page.refresh()
        self.gallery_page.refresh()
        self.tagger.scan(paths.list_photos())  # neue Fotos erkennen

    def closeEvent(self, event):
        """Beim Beenden: QR-/Text-Fotos aufräumen, wenn in den Optionen an."""
        wanted = {t for t, key in (("qr", "cleanup_qr"), ("text", "cleanup_text"))
                  if self.cfg.get(key)}
        if wanted:
            from ui.pages.gallery_page import move_to_trash
            for photo in paths.list_photos():
                found = set((tags.get(photo) or {}).get("tags", []))
                # zusätzlich als 🖼 Bild getaggt = behalten
                if found & wanted and "image" not in found:
                    move_to_trash(photo)
        super().closeEvent(event)

    def on_language_changed(self, lang: str):
        self.cfg["language"] = lang
        config.save(self.cfg)
        i18n.set_language(lang)
        # UI neu bauen, auf der Optionen-Seite bleiben
        self.build_ui(page_index=self.pages.currentIndex(), options_tab=self.options_page.current_tab)
