"""
ui/pages/main_page.py – Startseite: Status (+ Layer installieren),
letztes Foto (links) mit Übersetzung des Textes darin (rechts), Anleitung.

Die Übersetzung und der Verlauf können per ⧉ in ein eigenes Fenster (in VR: eigenes Panel).
QR-Codes im Foto stehen als anklickbare Links mit in der Übersetzung.

Aufgeteilt (damit die Datei überschaubar bleibt):
    main_page.py         Aufbau der Seite, Foto wählen, QR-Codes, Erkennung
    main_translation.py  🌐 Übersetzung      (TranslationMixin)
    main_history.py      🕘 Verlauf          (HistoryMixin)
    main_install.py      Layer installieren  (InstallMixin)
    main_live.py         🔁 Live-Modus       (LiveMixin)
"""

import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFontDatabase
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout,
                             QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from core import clipboard, layer_config, layer_install, paths, qr
from core.i18n import tr
from ui.pages.main_history import HistoryMixin
from ui.pages.main_install import InstallMixin
from ui.pages.main_live import LiveMixin
from ui.pages.main_translation import TranslationMixin
from ui.widgets import make_card, page_title


class MainPage(TranslationMixin, HistoryMixin, InstallMixin, LiveMixin, QWidget):
    # Ergebnis der Übersetzung aus dem Hintergrund-Thread:
    # (Foto-Pfad, erkannter Text, Übersetzung, Fehlertext)
    # (…, benutzter Dienst) – anders als gewählt, wenn z. B. Claude Code ausfiel
    _translated = pyqtSignal(str, str, str, str, str)
    # QR-Codes aus dem Hintergrund-Thread: (Foto-Pfad, gefundene Texte)
    _qr_found = pyqtSignal(str, list)
    # Zwischenstand der Übersetzung: (Foto-Pfad, Schritt, Dienst) → Statuszeile
    _progress = pyqtSignal(str, str, str)
    # korrigierter Text eines Verlauf-Eintrags übersetzt: (Text, Übersetzung, Fehler, Dienst)
    _text_translated = pyqtSignal(str, str, str, str)
    # Live-Modus: (erkannter Text, Übersetzung, Fehler, Dienst) / (Schritt, Wert)
    _live_done = pyqtSignal(str, str, str, str)
    _live_progress = pyqtSignal(str, str)
    # Von/Nach/Dienst hier geändert → Optionen-Seite passt sich an
    settings_changed = pyqtSignal()
    # Erkennung auto/manuell hier geändert → Optionen-Seite passt sich an
    layer_changed = pyqtSignal()

    def __init__(self, cfg: dict, tagger=None):
        super().__init__()
        self.cfg = cfg
        self.tagger = tagger  # Bild-Erkennung (für das Info-Fenster)
        self.last_photo = None       # Pfad des angezeigten Fotos
        self.chosen = None           # per 📁/🖼 gewähltes Foto (None = immer das neueste)
        self._not_ready = 0          # wie oft ein neues Foto noch nicht fertig war
        self.translating = None      # Foto, das gerade übersetzt wird
        self.tr_result = ""          # angezeigte Übersetzung
        self.qr_codes = []           # QR-Inhalte des Fotos (stehen mit in der Übersetzung)
        self.tr_window = None        # eigenes Fenster, wenn die Übersetzung "ausgeklinkt" ist
        self.history_window = None   # dasselbe für den Verlauf
        self._translated.connect(self.on_translated)
        self._qr_found.connect(self.on_qr_found)
        self._progress.connect(self.on_progress)
        self._text_translated.connect(self.on_text_translated)
        self.history_entry = None    # angezeigter Verlauf-Eintrag (None = aktuelles Foto)
        self._setting_ocr = False    # True, während die App den Text selbst setzt
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(page_title(tr("nav_main")))

        # --- Status: EINE kompakte Zeile -------------------------------
        #   ✔ Layer ist installiert · Fotos: 50      [📁] [🔧 Neu bauen] [🗑 Entfernen]
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(18, 10, 18, 10)
        box.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.layer_label = QLabel()
        row.addWidget(self.layer_label)
        dot = QLabel("·")
        dot.setObjectName("dim")
        row.addWidget(dot)
        self.count_label = QLabel()
        row.addWidget(self.count_label)
        row.addStretch()
        folder_btn = self.make_status_btn("📁  " + tr("open_folder"), self.open_folder)
        row.addWidget(folder_btn)
        self.install_btn = self.make_status_btn("", self.run_install)
        row.addWidget(self.install_btn)
        self.uninstall_btn = self.make_status_btn("🗑  " + tr("uninstall"), self.run_uninstall, "dangerbtn")
        self.uninstall_btn.setStyleSheet("padding: 6px 16px; min-height: 26px; font-size: 14px;")
        row.addWidget(self.uninstall_btn)
        box.addLayout(row)

        # Ausgabe des Skripts + Ergebnis (erst sichtbar, wenn es läuft).
        # Oben rechts ✕ → alles wieder ausblenden (das Bauen läuft trotzdem weiter).
        self.install_panel = QWidget()
        panel = QVBoxLayout(self.install_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.install_result = QLabel()
        self.install_result.setWordWrap(True)
        self.install_result.hide()
        top.addWidget(self.install_result, 1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("linkbtn")
        close_btn.setToolTip(tr("close"))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(32, 28)
        close_btn.setStyleSheet("padding: 0; font-size: 14px;")
        close_btn.clicked.connect(self.install_panel.hide)
        top.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        panel.addLayout(top)
        self.install_log = QPlainTextEdit()
        self.install_log.setReadOnly(True)
        self.install_log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.install_log.setFixedHeight(180)
        self.install_log.hide()
        panel.addWidget(self.install_log)
        self.install_panel.hide()
        box.addWidget(self.install_panel)
        self.process = None
        layout.addWidget(card)

        # --- Karte: Letztes Foto -------------------------------------
        # links das Foto, rechts die Übersetzung
        card, box = make_card(tr("last_photo"))
        # Überschrift aus der Karte holen und in eine Zeile mit Knöpfen setzen:
        #   Letztes Foto  [📁] [🖼]            (bzw. Ausgewähltes Foto … [✕])
        self.photo_title = box.itemAt(0).widget()
        box.removeWidget(self.photo_title)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.photo_title)
        self.file_btn = self.make_icon_btn("📁", tr("pick_file"), self.pick_from_file)
        head.addWidget(self.file_btn)
        self.gallery_btn = self.make_icon_btn("🖼", tr("pick_gallery"), self.pick_from_gallery)
        head.addWidget(self.gallery_btn)
        # ⓘ = gleiches Info-Fenster wie in der Galerie (Tags Text/QR/Bild ändern)
        self.info_btn = self.make_icon_btn("ⓘ", tr("info"), self.show_info)
        head.addWidget(self.info_btn)
        # Erkennung: automatisch (App) oder manuell (in VR per Taste wählen)
        self.detect_combo = QComboBox()
        self.detect_combo.addItem(tr("detect_auto"), "auto")
        self.detect_combo.addItem(tr("detect_manual"), "manual")
        self.detect_combo.setToolTip(tr("detect_tip"))
        self.detect_combo.setMinimumHeight(40)
        # breit genug für den längsten Eintrag (+ Platz für Padding und Pfeil)
        longest = max(self.detect_combo.itemText(i) for i in range(self.detect_combo.count()))
        self.detect_combo.setMinimumWidth(self.detect_combo.fontMetrics().horizontalAdvance(longest) + 70)
        self.detect_combo.currentIndexChanged.connect(self.detect_changed)
        head.addWidget(self.detect_combo)
        self.reset_btn = QPushButton("✕  " + tr("use_last_photo"))
        self.reset_btn.setObjectName("linkbtn")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setMinimumHeight(40)
        self.reset_btn.clicked.connect(lambda: self.set_chosen(None))
        head.addWidget(self.reset_btn)
        head.addStretch()
        box.insertLayout(0, head)

        row = QHBoxLayout()
        row.setSpacing(16)
        # PhotoView (aus der Galerie) passt das Foto an seine Größe an –
        # großes Fenster = großes Foto
        from ui.pages.gallery_page import PhotoView
        self.photo_label = PhotoView()
        self.photo_label.placeholder = tr("no_photo")
        self.photo_label.setMinimumSize(360, 340)
        row.addWidget(self.photo_label, 1)
        # Übersetzung in einem eigenen Widget → kann in ein eigenes Fenster wandern
        self.tr_panel = QWidget()
        self.tr_panel.setLayout(self.build_translation_panel())
        row.addWidget(self.tr_panel, 1)
        # Platzhalter, solange die Übersetzung im eigenen Fenster ist
        self.tr_placeholder = QWidget()
        ph = QVBoxLayout(self.tr_placeholder)
        ph.addStretch()
        ph.addWidget(QLabel(tr("tr_popped_out")), alignment=Qt.AlignmentFlag.AlignCenter)
        dock_btn = QPushButton("⧉  " + tr("tr_dock"))
        dock_btn.setObjectName("linkbtn")
        dock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dock_btn.setMinimumHeight(40)
        dock_btn.clicked.connect(self.dock_translation)
        ph.addWidget(dock_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        ph.addStretch()
        self.tr_placeholder.hide()
        row.addWidget(self.tr_placeholder, 1)
        self.photo_row = row
        box.addLayout(row, 1)
        # Stretch 1: die Karte bekommt den freien Platz, wenn das Fenster wächst
        layout.addWidget(card, 1)

        # --- Karte: Verlauf (nur wenn in den Optionen eingeschaltet) ---
        self.build_history_card(layout)

        # --- Karte: So geht's ----------------------------------------
        card, box = make_card(tr("howto"))
        for key in ("howto_1", "howto_2", "howto_3"):
            box.addWidget(QLabel(tr(key)))
        # nur im manuellen Modus sichtbar (sync_detect)
        # Punkt 4 hängt vom Modus ab (auto: 🪄↔🔁, manuell: 🖼📝🔳🔁) – siehe sync_detect
        self.howto_manual = QLabel(tr("howto_4"))
        self.howto_manual.setWordWrap(True)  # sonst wird die Seite zu breit
        box.addWidget(self.howto_manual)
        howto_lens = QLabel(tr("howto_5"))
        howto_lens.setWordWrap(True)
        box.addWidget(howto_lens)
        self.sync_detect()
        layout.addWidget(card)

        self.setup_live()  # 🔁 Live-Modus: schaut nach neuen Live-Bildern
        self.refresh()
        # AppImage aktualisiert? → den Layer in ~/.local gleich mitziehen
        if layer_install.needs_update():
            self.install_bundled(updated=True)

    def refresh(self):
        """Alles neu einlesen – wird auch aufgerufen, wenn ein neues Foto kommt."""
        installed = paths.layer_installed()
        if installed:
            self.layer_label.setText(tr("layer_ok"))
            self.layer_label.setObjectName("ok")
        else:
            self.layer_label.setText(tr("layer_missing"))
            self.layer_label.setObjectName("bad")
        # Alte Paket-Version (≤ 0.4.1) hat den Layer systemweit registriert:
        # Proton-Spiele sehen den nicht, native Spiele laden ihn evtl. doppelt
        tip = tr("layer_packaged") if paths.packaged() else ""
        if paths.legacy_system_layer():
            self.layer_label.setText(self.layer_label.text() + "   " + tr("layer_legacy"))
            self.layer_label.setObjectName("bad")
            tip = tr("layer_legacy_tip")
        self.layer_label.setToolTip(tip)
        # Nach setObjectName muss Qt den Stil neu anwenden
        self.layer_label.style().polish(self.layer_label)
        if self.process is None:  # nicht während des Bauens umbenennen
            if paths.copies_layer():
                # AppImage / AUR-Paket: nichts bauen, fertigen Layer nur kopieren
                if not installed:
                    text = "🔧  " + tr("install")
                elif layer_install.needs_update():
                    text = "⬆  " + tr("layer_update")
                else:
                    text = "🔧  " + tr("layer_reinstall")
            else:
                key = "reinstall" if installed else "install"
                text = "🔧  " + tr(key).replace("&", "&&")
            self.install_btn.setText(text)
            # nach dem Bauen (run_install) wieder anklickbar machen
            can_install = paths.copies_layer() or paths.INSTALL_SCRIPT.is_file()
            self.install_btn.setVisible(can_install)
            self.install_btn.setEnabled(can_install)
            self.uninstall_btn.setVisible(installed)
        photos = paths.list_photos()
        self.count_label.setText(tr("photo_count", n=len(photos)))

        # gewähltes Foto inzwischen gelöscht? → wieder das neueste nehmen
        if self.chosen is not None and not self.chosen.is_file():
            self.chosen = None
        # nichts gewählt → das neueste Foto
        shown = self.chosen or (photos[0] if photos else None)

        self.photo_title.setText(tr("chosen_photo") if self.chosen else tr("last_photo"))
        self.reset_btn.setVisible(self.chosen is not None)
        self.info_btn.setEnabled(shown is not None)
        self.photo_label.setToolTip(str(shown) if shown else "")

        # Neues Foto noch nicht fertig geschrieben? (ältere Layer schreiben die
        # Datei direkt – der Ordner meldet sie, bevor sie vollständig ist.)
        # Dann das bisherige Foto stehen lassen und gleich nochmal schauen,
        # statt "Noch kein Foto" zu zeigen – und OCR/QR nicht auf eine halbe
        # Datei loslassen (das Ergebnis würde im Cache hängen bleiben).
        if shown is not None and not paths.photo_ready(shown):
            self._not_ready += 1
            if self._not_ready <= 40:          # max. ~10 s
                QTimer.singleShot(250, self.refresh)
            return
        self._not_ready = 0

        # anderes Foto → neu laden, Übersetzung (Cache/automatisch), QR-Codes suchen
        if shown != self.last_photo or self.photo_label._full.isNull():
            self.photo_label.set_photo(shown)
        if shown != self.last_photo:
            self.last_photo = shown
            self.update_translation()
            self.scan_qr()

    # ------------------------------------------------------------------
    # QR-Codes im Foto: stehen als Links mit im Übersetzungs-Feld
    # (kein extra Kasten – in VR ist so alles an einer Stelle)
    # ------------------------------------------------------------------
    def scan_qr(self):
        self.show_qr([])
        photo = self.last_photo
        if photo is None or not qr.available():
            return

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                codes = qr.find_codes(photo)
            except Exception:  # noqa: BLE001 – QR ist nur ein Extra
                codes = []
            self._qr_found.emit(str(photo), codes)

        threading.Thread(target=work, daemon=True).start()

    def on_qr_found(self, photo: str, codes: list):
        if Path(photo) == self.last_photo:  # sonst ist es schon ein anderes Foto
            self.show_qr(codes)

    def show_qr(self, codes: list):
        self.qr_codes = list(codes)
        self.render_translation()

    def on_link(self, url: QUrl):
        """Klick auf einen Link im Übersetzungs-Feld."""
        if url.scheme() == "copy":  # copy:<Nummer> → QR-Inhalt kopieren
            try:
                text = self.qr_codes[int(url.path())]
            except (ValueError, IndexError):
                return
            clipboard.set_text(text)
            self.tr_status.setText(tr("qr_copied"))
            return
        QDesktopServices.openUrl(url)

    # ------------------------------------------------------------------
    # Foto auswählen: 📁 Dateiauswahl  ·  🖼 kleine Galerie
    # ------------------------------------------------------------------
    def make_icon_btn(self, icon: str, tip: str, slot) -> QPushButton:
        btn = QPushButton(icon)
        btn.setObjectName("linkbtn")
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(52, 40)  # groß genug, um in VR zu treffen
        btn.setStyleSheet("font-size: 20px; padding: 0;")
        btn.clicked.connect(slot)
        return btn

    def pick_from_file(self):
        start = self.last_photo.parent if self.last_photo else paths.photo_dir()
        name, _ = QFileDialog.getOpenFileName(
            self, tr("pick_file"), str(start),
            tr("image_files") + " (*.png *.jpg *.jpeg *.webp *.bmp)")
        if name:
            self.set_chosen(Path(name))

    def pick_from_gallery(self):
        from ui.photo_picker import pick_photo
        photo = pick_photo(self)
        if photo is not None:
            self.set_chosen(photo)

    def detect_changed(self):
        layer_config.update("detect_mode", self.detect_combo.currentData())
        self.sync_detect()
        self.layer_changed.emit()

    def sync_detect(self):
        """Dropdown an layer.json anpassen (auch nach Änderung in den Optionen)."""
        mode = layer_config.load()["detect_mode"]
        self.detect_combo.blockSignals(True)
        self.detect_combo.setCurrentIndex(max(0, self.detect_combo.findData(mode)))
        self.detect_combo.blockSignals(False)
        self.howto_manual.setText(tr("howto_4") if mode == "manual" else tr("howto_4_auto"))

    def show_info(self):
        if self.last_photo is None:
            return
        from ui.pages.gallery_page import InfoDialog
        InfoDialog(self.last_photo, self.tagger, self).exec()

    def set_chosen(self, photo):
        """photo = Path → dieses Foto zeigen/übersetzen,  None → wieder das neueste."""
        self.chosen = photo
        self.refresh()
