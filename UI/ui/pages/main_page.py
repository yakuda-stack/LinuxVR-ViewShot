"""
ui/pages/main_page.py – Startseite: Status (+ Layer installieren),
letztes Foto (links) mit Übersetzung des Textes darin (rechts), Anleitung.
"""

import os
import threading
from pathlib import Path

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFontDatabase
from PyQt6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from core import config, layer_config, ocr, paths, qr, translation
from core.i18n import tr
from ui.widgets import make_card, open_path, page_title


class MainPage(QWidget):
    # Ergebnis der Übersetzung aus dem Hintergrund-Thread:
    # (Foto-Pfad, erkannter Text, Übersetzung, Fehlertext)
    _translated = pyqtSignal(str, str, str, str)
    # QR-Codes aus dem Hintergrund-Thread: (Foto-Pfad, gefundene Texte)
    _qr_found = pyqtSignal(str, list)
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
        self.translating = None      # Foto, das gerade übersetzt wird
        self._translated.connect(self.on_translated)
        self._qr_found.connect(self.on_qr_found)
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

        # Ausgabe des Skripts (erst sichtbar, wenn es läuft)
        self.install_log = QPlainTextEdit()
        self.install_log.setReadOnly(True)
        self.install_log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.install_log.setFixedHeight(180)
        self.install_log.hide()
        box.addWidget(self.install_log)
        self.install_result = QLabel()
        self.install_result.setWordWrap(True)
        self.install_result.hide()
        box.addWidget(self.install_result)
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
        row.addLayout(self.build_translation_panel(), 1)
        box.addLayout(row, 1)
        # Stretch 1: die Karte bekommt den freien Platz, wenn das Fenster wächst
        layout.addWidget(card, 1)

        # --- Karte: QR-Code (nur sichtbar, wenn im Foto einer ist) -----
        self.qr_card, self.qr_box = make_card("🔳  " + tr("qr_title"))
        self.qr_rows = []  # Widgets der Zeilen (werden bei neuem Foto ersetzt)
        self.qr_card.hide()
        layout.addWidget(self.qr_card)

        # --- Karte: So geht's ----------------------------------------
        card, box = make_card(tr("howto"))
        for key in ("howto_1", "howto_2", "howto_3"):
            box.addWidget(QLabel(tr(key)))
        # nur im manuellen Modus sichtbar (sync_detect)
        self.howto_manual = QLabel(tr("howto_4"))
        self.howto_manual.setWordWrap(True)  # sonst wird die Seite zu breit
        box.addWidget(self.howto_manual)
        self.sync_detect()
        layout.addWidget(card)

        self.refresh()

    def refresh(self):
        """Alles neu einlesen – wird auch aufgerufen, wenn ein neues Foto kommt."""
        packaged = paths.packaged()
        if paths.layer_twice():
            self.layer_label.setText(tr("layer_twice"))
            self.layer_label.setObjectName("bad")
        elif paths.layer_installed():
            self.layer_label.setText(tr("layer_ok"))
            self.layer_label.setObjectName("ok")
        else:
            self.layer_label.setText(tr("layer_missing"))
            self.layer_label.setObjectName("bad")
        self.layer_label.setToolTip(tr("layer_packaged") if packaged else "")
        # Nach setObjectName muss Qt den Stil neu anwenden
        self.layer_label.style().polish(self.layer_label)
        if self.process is None:  # nicht während des Bauens umbenennen
            key = "reinstall" if paths.MANIFEST.is_file() else "install"
            self.install_btn.setText("🔧  " + tr(key).replace("&", "&&"))
            # Paket (AUR): pacman kümmert sich um den Layer → kein Bauen
            self.install_btn.setVisible(not packaged)
            # Entfernen nur für den Layer in ~/.local (Skript) – auch im
            # Paket-Modus, falls er zusätzlich doppelt da ist
            self.uninstall_btn.setVisible(paths.MANIFEST.is_file())
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

        # anderes Foto → neu laden, Übersetzung (Cache/automatisch), QR-Codes suchen
        if shown != self.last_photo or self.photo_label._full.isNull():
            self.photo_label.set_photo(shown)
        if shown != self.last_photo:
            self.last_photo = shown
            self.update_translation()
            self.scan_qr()

    # ------------------------------------------------------------------
    # QR-Codes im Foto: Zeile mit Inhalt + Knopf "Öffnen" / "Kopieren"
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
        for widget in self.qr_rows:
            widget.deleteLater()
        self.qr_rows = []
        for text in codes:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            line.addWidget(label, 1)
            if qr.is_link(text):
                btn = QPushButton("🔗  " + tr("qr_open"))
                url = text if "://" in text else "https://" + text
                btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            else:
                btn = QPushButton("📋  " + tr("copy"))
                btn.clicked.connect(lambda _, t=text: QApplication.clipboard().setText(t))
            btn.setObjectName("sendbtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(40)
            line.addWidget(btn)
            self.qr_box.addWidget(row)
            self.qr_rows.append(row)
        self.qr_card.setVisible(bool(codes))

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
        self.howto_manual.setVisible(mode == "manual")

    def show_info(self):
        if self.last_photo is None:
            return
        from ui.pages.gallery_page import InfoDialog
        InfoDialog(self.last_photo, self.tagger, self).exec()

    def set_chosen(self, photo):
        """photo = Path → dieses Foto zeigen/übersetzen,  None → wieder das neueste."""
        self.chosen = photo
        self.refresh()

    def make_status_btn(self, text: str, slot, style: str = "linkbtn") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(40)
        btn.clicked.connect(slot)
        return btn

    def run_uninstall(self):
        """Layer aus ~/.local entfernen (vorher fragen). App + Fotos bleiben."""
        if self.process is not None:
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("uninstall"))
        box.setText(tr("uninstall_question"))
        yes = box.addButton(tr("yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(tr("no"), QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self.install_log.hide()
        try:
            paths.uninstall_user_layer()
            ok = True
        except OSError:
            ok = False
        self.install_result.setText(tr("uninstall_ok") if ok else tr("uninstall_failed"))
        self.install_result.setObjectName("ok" if ok else "bad")
        self.install_result.style().polish(self.install_result)
        self.install_result.show()
        self.refresh()

    def open_folder(self):
        folder = paths.photo_dir()
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    # ------------------------------------------------------------------
    # Layer bauen + installieren (scripts/install-layer.sh)
    # ------------------------------------------------------------------
    def run_install(self):
        if self.process is not None:
            return
        self.install_log.clear()
        self.install_log.show()
        self.install_result.hide()
        self.install_btn.setEnabled(False)
        self.install_btn.setText("⏳  " + tr("installing"))

        # QProcess läuft im Hintergrund – die UI friert nicht ein
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        # rustup legt cargo nach ~/.cargo/bin – beim Start aus dem Menü fehlt das oft im PATH
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        env.insert("PATH", cargo_bin + ":" + env.value("PATH", "/usr/bin:/bin"))
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(paths.PROJECT_DIR))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_install_output)
        self.process.finished.connect(self.on_install_finished)
        self.process.start("bash", [str(paths.INSTALL_SCRIPT)])

    def on_install_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        self.install_log.insertPlainText(text)
        self.install_log.ensureCursorVisible()  # immer ans Ende scrollen

    def on_install_finished(self, exit_code: int, _status):
        ok = exit_code == 0
        self.install_result.setText(tr("install_ok") if ok else tr("install_failed"))
        self.install_result.setObjectName("ok" if ok else "bad")
        self.install_result.style().polish(self.install_result)
        self.install_result.show()
        self.process = None
        self.refresh()

    # ------------------------------------------------------------------
    # Übersetzung des letzten Fotos (rechts neben dem Bild)
    # ------------------------------------------------------------------
    def build_translation_panel(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("🌐  " + tr("translation"))
        title.setObjectName("cardtitle")
        head.addWidget(title)
        head.addStretch()
        self.translate_btn = QPushButton(tr("translate_btn"))
        self.translate_btn.setObjectName("sendbtn")
        self.translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translate_btn.setMinimumHeight(36)
        self.translate_btn.clicked.connect(lambda: self.start_translation(force=True))
        head.addWidget(self.translate_btn)
        col.addLayout(head)

        # Von / Nach / Dienst – die Einstellungen des Dienstes (Keys, Server …)
        # kommen aus Optionen → Übersetzung
        from ui.pages.options_page import language_combo  # gleiche Sprachliste wie dort
        self.src_combo = language_combo(with_auto=True)
        self.dst_combo = language_combo(with_auto=False)
        self.method_combo = QComboBox()
        for m in translation.METHODS:
            self.method_combo.addItem(tr("tr_m_" + m), m)

        # Zeile 1:  Von [Automatisch ▾]  →  [Deutsch ▾]
        # Zeile 2:  Dienst [Lingva ▾]
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.addWidget(QLabel(tr("tr_from")), 0, 0)
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.src_combo, 1)
        arrow = QLabel("→")
        arrow.setObjectName("cardtitle")
        lang_row.addWidget(arrow)
        lang_row.addWidget(self.dst_combo, 1)
        grid.addLayout(lang_row, 0, 1)
        grid.addWidget(QLabel(tr("tr_via")), 1, 0)
        grid.addWidget(self.method_combo, 1, 1)
        grid.setColumnStretch(1, 1)
        col.addLayout(grid)

        for combo, key in ((self.src_combo, "tr_source"), (self.dst_combo, "tr_target"),
                           (self.method_combo, "tr_method")):
            # k=key, c=combo: merkt sich die Werte DIESES Dropdowns
            combo.currentIndexChanged.connect(lambda _, k=key, c=combo: self.combo_changed(k, c))
        self.sync_combos()

        self.tr_status = QLabel()
        self.tr_status.setObjectName("dim")
        self.tr_status.setWordWrap(True)
        col.addWidget(self.tr_status)

        # Übersetzung groß, erkannter Text klein darunter
        self.tr_text = QPlainTextEdit()
        self.tr_text.setObjectName("translation")
        self.tr_text.setReadOnly(True)
        col.addWidget(self.tr_text, 3)
        self.ocr_title = QLabel(tr("recognized"))
        self.ocr_title.setObjectName("dim")
        col.addWidget(self.ocr_title)
        self.ocr_text = QPlainTextEdit()
        self.ocr_text.setReadOnly(True)
        col.addWidget(self.ocr_text, 2)
        return col

    def sync_combos(self):
        """Dropdowns an ui.json anpassen (z. B. nach Änderung in den Optionen)."""
        for combo, key in ((self.src_combo, "tr_source"), (self.dst_combo, "tr_target"),
                           (self.method_combo, "tr_method")):
            combo.blockSignals(True)  # sonst meldet das Setzen selbst "geändert"
            combo.setCurrentIndex(max(0, combo.findData(self.cfg[key])))
            combo.blockSignals(False)

    def combo_changed(self, key: str, combo: QComboBox):
        self.cfg[key] = combo.currentData()
        config.save(self.cfg)
        self.settings_changed.emit()
        # direkt neu übersetzen (Cache wird benutzt, falls schon mal gemacht)
        self.show_translation("", "")
        self.start_translation()

    def on_options_changed(self):
        """Optionen → Übersetzung wurde geändert."""
        self.sync_combos()
        self.update_translation()

    def show_translation(self, original: str, translated: str):
        self.tr_text.setPlainText(translated)
        self.ocr_text.setPlainText(original)
        has_text = bool(original)
        self.ocr_title.setVisible(has_text)
        self.ocr_text.setVisible(has_text)
        self.tr_status.setText("" if has_text else tr("no_text"))

    def update_translation(self):
        """Aufgerufen bei neuem Foto oder geänderten Einstellungen."""
        self.show_translation("", "")
        self.tr_status.clear()
        photo = self.last_photo
        self.translate_btn.setEnabled(photo is not None)
        if photo is None:
            return
        if not ocr.available():
            self.tr_status.setText(tr("ocr_missing", cmd=ocr.INSTALL_HINT))
            self.tr_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.translate_btn.setEnabled(False)
            return
        hit = translation.cached(photo, self.cfg)
        if hit is not None:
            self.show_translation(*hit)
        elif self.cfg["tr_auto"]:
            self.start_translation()

    def start_translation(self, force: bool = False):
        photo = self.last_photo
        if photo is None or self.translating is not None:
            return
        hit = None if force else translation.cached(photo, self.cfg)
        if hit is not None:
            self.show_translation(*hit)
            return
        self.translating = photo
        self.translate_btn.setEnabled(False)
        self.tr_status.setText("⏳  " + tr("translating"))
        cfg = dict(self.cfg)
        self.translating_key = translation._key(cfg)  # mit welchen Einstellungen?
        errors = []

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                original, translated = translation.translate_photo(photo, cfg, log=errors.append)
                self._translated.emit(str(photo), original, translated, "")
            except Exception as e:  # noqa: BLE001
                self._translated.emit(str(photo), "", "", "; ".join(errors) or str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_translated(self, photo: str, original: str, translated: str, error: str):
        self.translating = None
        self.translate_btn.setEnabled(True)
        if Path(photo) != self.last_photo:
            self.update_translation()  # inzwischen kam ein neueres Foto
            return
        if self.translating_key != translation._key(self.cfg):
            # während des Übersetzens wurde Von/Nach/Dienst geändert → nochmal
            self.start_translation()
            return
        if error:
            self.tr_status.setText(f"{tr('tr_failed')}: {error}")
            return
        self.show_translation(original, translated)
