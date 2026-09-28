"""
ui/pages/main_page.py – Startseite: Status (+ Layer installieren),
letztes Foto (links) mit Übersetzung des Textes darin (rechts), Anleitung.

Die Übersetzung und der Verlauf können per ⧉ in ein eigenes Fenster (in VR: eigenes Panel).
QR-Codes im Foto stehen als anklickbare Links mit in der Übersetzung.
"""

import html
from datetime import datetime
import os
import threading
from pathlib import Path

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFontDatabase
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser,
                             QVBoxLayout, QWidget)

from core import llm_translator as llm
from core import clipboard, config, history, layer_config, layer_install, ocr, paths, qr, translation
from core.i18n import tr
from core.version import VERSION
from ui.widgets import make_card, open_path, page_title


class MainPage(QWidget):
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
        self.howto_manual = QLabel(tr("howto_4"))
        self.howto_manual.setWordWrap(True)  # sonst wird die Seite zu breit
        box.addWidget(self.howto_manual)
        self.sync_detect()
        layout.addWidget(card)

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
        self.install_panel.show()
        self.refresh()

    def open_folder(self):
        folder = paths.photo_dir()
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    # ------------------------------------------------------------------
    # Layer bauen + installieren (scripts/install-layer.sh)
    # ------------------------------------------------------------------
    def install_bundled(self, updated: bool = False):
        """AppImage: mitgelieferten Layer nach ~/.local kopieren (dauert < 1 s)."""
        self.install_log.hide()
        try:
            layer_install.install_bundled()
            ok = True
        except OSError:
            ok = False
        if not ok:
            text = tr("install_failed_copy")
        elif updated:
            text = tr("layer_updated", v=VERSION)
        else:
            text = tr("install_ok")
        self.install_result.setText(text)
        self.install_result.setObjectName("ok" if ok else "bad")
        self.install_result.style().polish(self.install_result)
        self.install_result.show()
        self.install_panel.show()
        self.refresh()

    def run_install(self):
        if self.process is not None:
            return
        if paths.copies_layer():
            self.install_bundled()
            return
        self.install_log.clear()
        self.install_log.show()
        self.install_panel.show()
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
        self.install_panel.show()
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
        # ⧉ Übersetzung in eigenes Fenster (in VR: eigenes Panel, frei platzierbar)
        self.popout_btn = QPushButton("⧉")
        self.popout_btn.setObjectName("linkbtn")
        self.popout_btn.setToolTip(tr("tr_popout"))
        self.popout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.popout_btn.setFixedSize(52, 36)
        self.popout_btn.setStyleSheet("font-size: 20px; padding: 0;")
        self.popout_btn.clicked.connect(self.toggle_popout)
        head.addWidget(self.popout_btn)
        # ↻ nochmal senden (ohne gespeichertes Ergebnis) – z. B. wenn die KI Unsinn schrieb
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("linkbtn")
        self.refresh_btn.setToolTip(tr("tr_refresh"))
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setFixedSize(52, 36)
        self.refresh_btn.setStyleSheet("font-size: 20px; padding: 0;")
        self.refresh_btn.clicked.connect(lambda: self.start_translation(force=True))
        head.addWidget(self.refresh_btn)
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
        self.fill_method_combo()

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
        # Dienst [Claude Code ▾] [sonnet ▾]  – Modell nur bei KI-Vorlagen sichtbar
        from ui.pages.options_page import model_combo
        service_row = QHBoxLayout()
        service_row.addWidget(self.method_combo, 1)
        self.model_combo = model_combo("", "", self.model_changed)
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setToolTip(tr("tr_model"))
        service_row.addWidget(self.model_combo)
        grid.addLayout(service_row, 1, 1)
        # Aufgabe [Übersetzen ▾]  – nur bei KI: übersetzen / Kontext erklären / Frage beantworten
        self.mode_label = QLabel(tr("tr_task"))
        grid.addWidget(self.mode_label, 2, 0)
        self.mode_combo = QComboBox()
        for mode in llm.MODES:
            self.mode_combo.addItem(tr("tr_mode_" + mode), mode)
        self.mode_combo.currentIndexChanged.connect(lambda _: self.mode_changed())
        grid.addWidget(self.mode_combo, 2, 1)
        grid.setColumnStretch(1, 1)
        col.addLayout(grid)

        for combo, key in ((self.src_combo, "tr_source"), (self.dst_combo, "tr_target"),
                           (self.method_combo, "tr_method")):
            # k=key, c=combo: merkt sich die Werte DIESES Dropdowns
            combo.currentIndexChanged.connect(lambda _, k=key, c=combo: self.combo_changed(k, c))
        self.sync_combos()

        # Statuszeile links, 📋 Kopieren rechts (direkt über dem Übersetzungs-Feld)
        status_row = QHBoxLayout()
        self.tr_status = QLabel()
        self.tr_status.setObjectName("dim")
        self.tr_status.setWordWrap(True)
        status_row.addWidget(self.tr_status, 1)
        self.copy_btn = QPushButton("📋  " + tr("copy"))
        self.copy_btn.setObjectName("linkbtn")
        self.copy_btn.setToolTip(tr("tr_copy_tip"))
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setMinimumHeight(36)
        self.copy_btn.clicked.connect(self.copy_translation)
        self.copy_btn.setEnabled(False)
        status_row.addWidget(self.copy_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        col.addLayout(status_row)

        # Übersetzung groß (+ QR-Links), erkannter Text klein darunter
        self.tr_text = QTextBrowser()
        self.tr_text.setObjectName("translation")
        self.tr_text.setOpenLinks(False)  # Klicks selbst behandeln (on_link)
        self.tr_text.document().setDefaultStyleSheet(
            "a { color: #7fb0ea; text-decoration: underline; }")
        self.tr_text.anchorClicked.connect(self.on_link)
        col.addWidget(self.tr_text, 3)
        # "▸ Erkannter Text" – einklappbar, Standard zu (in VR am Handgelenk ist Platz knapp)
        self.ocr_title = QPushButton()
        self.ocr_title.setObjectName("foldbtn")
        self.ocr_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ocr_title.setMinimumHeight(32)
        self.ocr_title.clicked.connect(self.toggle_ocr)
        col.addWidget(self.ocr_title, alignment=Qt.AlignmentFlag.AlignLeft)
        # selbst korrigierbar – falls die Texterkennung sich verlesen hat
        self.ocr_text = QPlainTextEdit()
        self.ocr_text.setPlaceholderText(tr("ocr_edit_hint"))
        self.ocr_text.textChanged.connect(self.ocr_edited)
        col.addWidget(self.ocr_text, 2)
        self.retranslate_btn = QPushButton("🌐  " + tr("ocr_retranslate"))
        self.retranslate_btn.setObjectName("sendbtn")
        self.retranslate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retranslate_btn.setMinimumHeight(36)
        self.retranslate_btn.clicked.connect(self.translate_corrected)
        col.addWidget(self.retranslate_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.has_ocr_text = False
        self.ocr_dirty = False       # Text von Hand geändert, noch nicht übersetzt
        return col

    def fill_method_combo(self):
        """Nur eingerichtete Dienste (Key da / Programm installiert) anbieten."""
        self.method_combo.blockSignals(True)
        self.method_combo.clear()
        for m in translation.menu_methods(self.cfg):
            self.method_combo.addItem(tr("tr_m_" + m), m)
        self.method_combo.blockSignals(False)

    def sync_combos(self):
        """Dropdowns an ui.json anpassen (z. B. nach Änderung in den Optionen)."""
        for combo, key in ((self.src_combo, "tr_source"), (self.dst_combo, "tr_target"),
                           (self.method_combo, "tr_method")):
            combo.blockSignals(True)  # sonst meldet das Setzen selbst "geändert"
            combo.setCurrentIndex(max(0, combo.findData(self.cfg[key])))
            combo.blockSignals(False)
        self.sync_model()

    def sync_model(self):
        """Modell-Dropdown passend zum Dienst (nur bei Claude Code / Gemini / ChatGPT)."""
        from ui.pages.options_page import fill_model_combo
        method = self.cfg["tr_method"]
        key = llm.MODEL_KEYS.get(method)
        self.model_combo.setVisible(key is not None)
        is_ai = llm.is_llm(method)
        self.mode_label.setVisible(is_ai)
        self.mode_combo.setVisible(is_ai)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(
            self.cfg.get("tr_llm_mode") or llm.MODE_TRANSLATE)))
        self.mode_combo.blockSignals(False)
        if key is not None:
            fill_model_combo(self.model_combo, method, self.cfg.get(key, ""))

    def mode_changed(self):
        """Aufgabe der KI geändert (Übersetzen / Kontext / Antworten) → neu fragen."""
        self.cfg["tr_llm_mode"] = self.mode_combo.currentData()
        config.save(self.cfg)
        self.settings_changed.emit()
        self.clear_translation()
        self.start_translation()

    def model_changed(self, model: str):
        key = llm.MODEL_KEYS.get(self.cfg["tr_method"])
        if key is None or model == self.cfg.get(key):
            return
        self.cfg[key] = model
        config.save(self.cfg)
        self.settings_changed.emit()
        self.clear_translation()
        self.start_translation()

    def combo_changed(self, key: str, combo: QComboBox):
        self.cfg[key] = combo.currentData()
        config.save(self.cfg)
        if key == "tr_method":
            self.sync_model()
        self.settings_changed.emit()
        # direkt neu übersetzen (Cache wird benutzt, falls schon mal gemacht)
        self.clear_translation()
        self.start_translation()

    def on_options_changed(self):
        """Optionen → Übersetzung wurde geändert."""
        self.fill_method_combo()  # z. B. Key eingetragen → Dienst taucht auf
        self.sync_combos()
        self.sync_history()
        self.update_translation()

    def clear_translation(self):
        """Feld leeren (neues Foto / andere Einstellung). NICHT "Kein Text gefunden"
        zeigen – das weiß man erst, wenn die Texterkennung wirklich gelaufen ist."""
        self.tr_result = ""
        self.history_entry = None
        self.render_translation()
        self.set_ocr_text("")
        self.has_ocr_text = False
        self.sync_ocr()
        busy = self.translating is not None
        self.tr_status.setText("⏳  " + tr("translating") if busy else "")

    def show_translation(self, original: str, translated: str):
        self.tr_result = translated
        self.render_translation()
        self.set_ocr_text(original)
        has_text = bool(original)
        # Feld auch ohne erkannten Text zeigen – dann kann man den Text selbst eintippen
        self.has_ocr_text = True
        self.sync_ocr()
        self.tr_status.setText("" if has_text else tr("no_text"))

    # ------------------------------------------------------------------
    # Erkannten Text von Hand korrigieren → neu übersetzen
    # ------------------------------------------------------------------
    def set_ocr_text(self, text: str):
        self._setting_ocr = True
        self.ocr_text.setPlainText(text)
        self._setting_ocr = False
        self.ocr_dirty = False
        self.sync_ocr()

    def ocr_edited(self):
        if self._setting_ocr:
            return
        self.ocr_dirty = True
        self.sync_ocr()

    def translate_corrected(self):
        """Den (korrigierten) Text übersetzen statt nochmal das Foto zu lesen."""
        text = self.ocr_text.toPlainText().strip()
        if not text or self.translating is not None:
            return
        entry = self.history_entry
        photo = self.last_photo
        if entry is None and photo is not None:
            # fürs aktuelle Foto merken: ab jetzt gilt der korrigierte Text
            translation.set_ocr(photo, text)
            self.start_translation(force=True)
            return
        # Verlauf-Eintrag (Foto evtl. gelöscht): nur den Text übersetzen
        self.translating = "text"
        self.translate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.tr_status.setText("⏳  " + tr("translating"))
        cfg = dict(self.cfg)
        errors = []

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                out, used = translation.translate_text_used(text, cfg, log=errors.append)
                self._text_translated.emit(text, out, "; ".join(errors), used)
            except Exception as e:  # noqa: BLE001
                self._text_translated.emit(text, "", "; ".join(errors) or str(e), "")

        threading.Thread(target=work, daemon=True).start()

    def on_text_translated(self, text: str, translated: str, error: str, used: str):
        self.translating = None
        self.translate_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        if not used:
            self.tr_status.setText(f"{tr('tr_failed')}: {error}")
            return
        photo = self.history_entry.get("photo", "") if self.history_entry else ""
        entry = self.history_entry
        self.show_translation(text, translated)
        self.history_entry = entry  # bleibt im Verlauf-Modus
        self.add_history(photo, text, translated, used)

    # ------------------------------------------------------------------
    # Verlauf: Liste der letzten Übersetzungen (nur Text, kein Bild)
    # ------------------------------------------------------------------
    def build_history_card(self, layout: QVBoxLayout):
        from PyQt6.QtWidgets import QListWidget
        self.history_card, box = make_card("🕘  " + tr("history"))
        head = QHBoxLayout()
        hint = QLabel(tr("history_hint"))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        head.addWidget(hint, 1)
        # ⧉ Verlauf in eigenes Fenster (wie bei der Übersetzung)
        self.history_popout_btn = QPushButton("⧉")
        self.history_popout_btn.setObjectName("linkbtn")
        self.history_popout_btn.setToolTip(tr("history_popout"))
        self.history_popout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_popout_btn.setFixedSize(52, 36)
        self.history_popout_btn.setStyleSheet("font-size: 20px; padding: 0;")
        self.history_popout_btn.clicked.connect(self.toggle_history_popout)
        head.addWidget(self.history_popout_btn)
        box.addLayout(head)

        # Liste + Leeren in einem eigenen Widget → kann in ein eigenes Fenster wandern
        self.history_panel = QWidget()
        panel = QVBoxLayout(self.history_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        self.history_list = QListWidget()
        self.history_list.setFixedHeight(190)  # scrollt, statt die Seite zu verlängern
        self.history_list.setWordWrap(True)
        self.history_list.itemClicked.connect(self.show_history)
        panel.addWidget(self.history_list)
        clear_btn = QPushButton("🗑  " + tr("history_clear"))
        clear_btn.setObjectName("linkbtn")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setMinimumHeight(36)
        clear_btn.clicked.connect(self.clear_history)
        panel.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        box.addWidget(self.history_panel)

        # Platzhalter, solange der Verlauf im eigenen Fenster ist
        self.history_placeholder = QWidget()
        ph = QHBoxLayout(self.history_placeholder)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addWidget(QLabel(tr("history_popped_out")), 1)
        dock_btn = QPushButton("⧉  " + tr("tr_dock"))
        dock_btn.setObjectName("linkbtn")
        dock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dock_btn.setMinimumHeight(36)
        dock_btn.clicked.connect(self.dock_history)
        ph.addWidget(dock_btn)
        self.history_placeholder.hide()
        box.addWidget(self.history_placeholder)
        self.history_box = box
        layout.addWidget(self.history_card)
        self.sync_history()

    def toggle_history_popout(self):
        if self.history_window is None:
            self.popout_history()
        else:
            self.dock_history()

    def popout_history(self):
        win = PanelWindow(self, tr("history"), self.dock_history, (520, 560))
        self.history_box.removeWidget(self.history_panel)
        win.layout().addWidget(self.history_panel)
        # im eigenen Fenster darf die Liste mitwachsen
        self.history_list.setMinimumHeight(190)
        self.history_list.setMaximumHeight(16777215)
        self.history_panel.show()
        self.history_placeholder.show()
        self.history_popout_btn.setToolTip(tr("tr_dock"))
        self.history_window = win
        win.show()

    def dock_history(self):
        win, self.history_window = self.history_window, None
        if win is None:
            return
        win.layout().removeWidget(self.history_panel)
        self.history_placeholder.hide()
        self.history_box.insertWidget(self.history_box.indexOf(self.history_placeholder),
                                      self.history_panel)
        self.history_list.setFixedHeight(190)
        self.history_panel.show()
        self.history_popout_btn.setToolTip(tr("history_popout"))
        win.docking = True
        win.close()
        win.deleteLater()

    def sync_history(self):
        """Karte zeigen/verstecken und Liste neu füllen."""
        from PyQt6.QtWidgets import QListWidgetItem
        on = bool(self.cfg.get("history"))
        if not on and self.history_window is not None:
            self.dock_history()  # Verlauf aus → eigenes Fenster schließen
        self.history_card.setVisible(on)
        self.history_list.clear()
        if not on:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        for entry in history.load():
            when = entry.get("time", "")
            when = when[11:] if when.startswith(today) else when
            first = (entry.get("tr") or "").strip().splitlines()
            preview = first[0] if first else ""
            if len(preview) > 90:
                preview = preview[:90] + " …"
            item = QListWidgetItem(f"{when}   {preview}")
            item.setToolTip(entry.get("tr", ""))
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.history_list.addItem(item)

    def add_history(self, photo: str, ocr: str, translated: str, method: str):
        if self.cfg.get("history") and history.add(Path(photo).name if photo else "",
                                                   ocr, translated, method):
            self.sync_history()

    def show_history(self, item):
        """Eintrag anklicken → erkannter Text + Übersetzung ins Feld (ohne Bild)."""
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not entry or self.translating is not None:
            return
        self.show_translation(entry.get("ocr", ""), entry.get("tr", ""))
        self.history_entry = entry
        self.render_translation()  # ohne die QR-Codes des aktuellen Fotos
        method = entry.get("method", "")
        name = tr("tr_m_" + method) if method else ""
        self.tr_status.setText(tr("history_showing", time=entry.get("time", ""), service=name))

    def clear_history(self):
        history.clear()
        self.sync_history()

    def toggle_ocr(self):
        """▸/▾ Erkannter Text auf-/zuklappen (wird gemerkt)."""
        self.cfg["ocr_expanded"] = not self.cfg.get("ocr_expanded", False)
        config.save(self.cfg)
        self.sync_ocr()

    def sync_ocr(self):
        expanded = bool(self.cfg.get("ocr_expanded", False))
        self.ocr_title.setText(("▾  " if expanded else "▸  ") + tr("recognized"))
        self.ocr_title.setVisible(self.has_ocr_text)
        self.ocr_text.setVisible(self.has_ocr_text and expanded)
        self.retranslate_btn.setVisible(self.has_ocr_text and expanded and self.ocr_dirty)

    def copy_translation(self):
        """📋 Übersetzung/Antwort in die Zwischenablage (auch an den Desktop, falls WayVR)."""
        if self.tr_result:
            clipboard.set_text(self.tr_result)
            self.tr_status.setText(tr("tr_copied"))

    def render_translation(self):
        """Übersetzung + darunter die QR-Codes als anklickbare Links."""
        self.copy_btn.setEnabled(bool(self.tr_result))
        parts = []
        if self.tr_result:
            parts.append(html.escape(self.tr_result).replace("\n", "<br>"))
        codes = [] if self.history_entry is not None else self.qr_codes
        for i, text in enumerate(codes):
            label = html.escape(text)
            if qr.is_link(text):
                url = text if "://" in text else "https://" + text
                line = f'<a href="{html.escape(url, quote=True)}">{label}</a>'
            else:
                line = label
            # 📋 = kopieren (groß genug für den VR-Laser)
            line += f'&nbsp;&nbsp;<a href="copy:{i}">📋&nbsp;{html.escape(tr("copy"))}</a>'
            parts.append(f"🔳&nbsp;<b>{html.escape(tr('qr_in_text'))}:</b> {line}")
        self.tr_text.setHtml("<br><br>".join(parts))

    # ------------------------------------------------------------------
    # Übersetzung in eigenem Fenster (⧉) – schließen = zurück
    # ------------------------------------------------------------------
    def toggle_popout(self):
        if self.tr_window is None:
            self.popout_translation()
        else:
            self.dock_translation()

    def popout_translation(self):
        win = PanelWindow(self, tr("translation"), self.dock_translation)
        self.photo_row.removeWidget(self.tr_panel)
        win.layout().addWidget(self.tr_panel)
        self.tr_panel.show()
        self.tr_placeholder.show()
        self.popout_btn.setToolTip(tr("tr_dock"))
        self.tr_window = win
        win.show()

    def dock_translation(self):
        win, self.tr_window = self.tr_window, None
        if win is None:
            return
        win.layout().removeWidget(self.tr_panel)
        self.tr_placeholder.hide()
        # gleiche Stelle wie vorher: direkt neben das Foto
        self.photo_row.insertWidget(self.photo_row.indexOf(self.tr_placeholder), self.tr_panel, 1)
        self.tr_panel.show()
        self.popout_btn.setToolTip(tr("tr_popout"))
        win.docking = True
        win.close()
        win.deleteLater()

    def update_translation(self):
        """Aufgerufen bei neuem Foto oder geänderten Einstellungen."""
        self.clear_translation()
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
            # auch gespeicherte Ergebnisse in den Verlauf – sonst fehlen z. B. Fotos,
            # deren Text schon vorher gelesen/übersetzt wurde (doppelte fliegen raus)
            self.add_history(str(photo), hit[0], hit[1], self.cfg["tr_method"])
        elif self.cfg["tr_auto"]:
            self.start_translation()

    def start_translation(self, force: bool = False):
        photo = self.last_photo
        if photo is None:
            return
        self.history_entry = None  # zurück vom Verlauf zum aktuellen Foto
        if self.translating is not None:
            # läuft schon – on_translated fängt neues Foto / neue Einstellung ab
            self.tr_status.setText("⏳  " + tr("translating"))
            return
        hit = None if force else translation.cached(photo, self.cfg)
        if hit is not None:
            self.show_translation(*hit)
            # auch gespeicherte Ergebnisse in den Verlauf – sonst fehlen z. B. Fotos,
            # deren Text schon vorher gelesen/übersetzt wurde (doppelte fliegen raus)
            self.add_history(str(photo), hit[0], hit[1], self.cfg["tr_method"])
            return
        self.translating = photo
        self.translate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.tr_status.setText("⏳  " + tr("translating"))
        cfg = dict(self.cfg)
        self.translating_key = translation._key(cfg)  # mit welchen Einstellungen?
        errors = []

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                original, translated, used = translation.translate_photo(
                    photo, cfg, log=errors.append,
                    progress=lambda step, arg="": self._progress.emit(str(photo), step, arg))
                self._translated.emit(str(photo), original, translated, "; ".join(errors), used)
            except Exception as e:  # noqa: BLE001
                self._translated.emit(str(photo), "", "", "; ".join(errors) or str(e), "")

        threading.Thread(target=work, daemon=True).start()

    def on_progress(self, photo: str, step: str, arg: str):
        """Zeigt, was gerade passiert: Text lesen / auf Texterkennung warten / Dienst X."""
        if self.translating is None or Path(photo) != self.translating:
            return
        if step == "service":
            text = tr("tr_step_service", name=tr("tr_m_" + arg))
        elif step == "retry":
            method, _, attempt = arg.rpartition(":")
            text = tr("tr_step_retry", name=tr("tr_m_" + method), n=attempt)
        else:
            text = tr("tr_step_" + step)
        self.tr_status.setText("⏳  " + text)

    def on_translated(self, photo: str, original: str, translated: str, error: str, used: str):
        self.translating = None
        self.translate_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        if Path(photo) != self.last_photo:
            self.update_translation()  # inzwischen kam ein neueres Foto
            return
        if self.translating_key != translation._key(self.cfg):
            # während des Übersetzens wurde Von/Nach/Dienst geändert → nochmal
            self.start_translation()
            return
        if not used:  # alle Dienste ausgefallen
            self.tr_status.setText(f"{tr('tr_failed')}: {error}")
            return
        self.show_translation(original, translated)
        self.add_history(photo, original, translated, used)
        failed = self.cfg["tr_method"]
        if used != failed and not self.isVisible():
            # Optionen sind offen (Dienst wird gerade eingerichtet) → NICHT umstellen,
            # sonst springt der Dienst dort weg. Nur Bescheid sagen.
            self.tr_status.setText(tr("tr_fallback_once", failed=tr("tr_m_" + failed),
                                      used=tr("tr_m_" + used), error=error))
        elif used != failed:
            # gewählter Dienst ging nicht → auf den umstellen, der übersetzt hat
            self.cfg["tr_method"] = used
            config.save(self.cfg)
            self.fill_method_combo()
            self.sync_combos()
            self.settings_changed.emit()
            self.tr_status.setText(tr("tr_fallback_used", failed=tr("tr_m_" + failed),
                                      used=tr("tr_m_" + used), error=error))


class PanelWindow(QWidget):
    """Eigenes Fenster für einen Teil der Main-Seite (Übersetzung, Verlauf).
    Schließen (✕) = on_close() → zurück ins Hauptfenster."""

    def __init__(self, page: MainPage, title: str, on_close, size=(560, 640)):
        # parent = Seite → das Fenster verschwindet mit ihr (z. B. Sprachwechsel)
        super().__init__(page, Qt.WindowType.Window)
        self.on_close = on_close
        self.docking = False
        self.setWindowTitle("LinuxVR-ViewShot – " + title)
        self.setStyleSheet(page.window().styleSheet())
        self.setObjectName("trwindow")
        # ohne das malt ein einfaches QWidget seinen Hintergrund nicht
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.resize(*size)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)

    def closeEvent(self, event):
        if not self.docking:
            self.on_close()
        event.accept()
