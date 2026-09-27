"""
ui/pages/options_page.py – Optionen mit Tabs (wie bei OSC-DreamChatbox):

    ⚙ General      Community-Links (Discord, Ko-fi …), Sprache, Ordner, Über
    📸 Shot        Rahmengröße, linkes/rechtes Auge, Ausnahme-Programme
    🌐 Übersetzung Dienst (Lingva, Google, LibreTranslate, DeepL, eigene API), Zielsprache

Die Shot-Einstellungen werden in layer.json gespeichert – der Layer übernimmt
Änderungen sofort, auch während das Spiel läuft.

Neuer Tab? In build_tabs() eine Zeile ("Name", self.build_xyz()) ergänzen.
"""

import threading

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QSlider,
                             QVBoxLayout, QWidget)

from core import config, i18n, layer_config, ocr, paths, translation
from core import translators as T
from core.custom_translator import LIBRE_EXAMPLE
from core.i18n import tr
from core.version import VERSION
from ui.widgets import make_card, open_path, page_title

DISCORD_URL = "https://discord.gg/ShNKvvZu74"
DONATE_URL = "https://ko-fi.com/yakuda_"
VRCHAT_GROUP_URL = "https://vrchat.com/home/group/grp_829b7777-430d-48b2-8bf3-4e348d0dac9b"
GITHUB_URL = "https://github.com/yakuda-stack/LinuxVR-ViewShot"


def button(text: str, slot, style: str = "linkbtn") -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName(style)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setMinimumHeight(34)
    btn.clicked.connect(slot)
    return btn


def dim(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("dim")
    label.setWordWrap(True)
    return label


def language_combo(with_auto: bool) -> QComboBox:
    """Dropdown mit Sprachen (Anzeige in UI-Sprache, Wert = Sprachcode)."""
    combo = QComboBox()
    entries = ([translation.AUTO] if with_auto else []) + translation.LANGUAGES
    for code, de, en in entries:
        combo.addItem(de if i18n._lang == "de" else en, code)
    return combo


def open_url(url: str):
    return lambda: QDesktopServices.openUrl(QUrl(url))


class OptionsPage(QWidget):
    # Signal an das Hauptfenster: "Sprache wurde geändert" (mit "de"/"en")
    language_changed = pyqtSignal(str)
    # Übersetzungs-Einstellungen geändert → Main-Seite aktualisiert sich
    translation_changed = pyqtSignal()
    # Erkennung (auto/manuell) oder Tasten geändert → Main-Seite passt ihr Dropdown an
    layer_changed = pyqtSignal()
    # Ergebnis der WayVR-Design-Installation (Hintergrund-Thread): (ok, Text)
    _wayvr_done = pyqtSignal(bool, str)
    # Ergebnis des Test-Knopfs (kommt aus einem Hintergrund-Thread)
    _test_done = pyqtSignal(str)
    # Ergebnis der LibreTranslate-Suche (Adresse oder "")
    _libre_found = pyqtSignal(str)

    def __init__(self, cfg: dict, tab: int = 0):
        super().__init__()
        self.cfg = cfg
        self.layer = layer_config.load()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(page_title(tr("nav_options")))

        # --- Tab-Knöpfe oben ------------------------------------------
        tabs = [
            ("⚙  " + tr("tab_general"), self.build_general()),
            ("📸  " + tr("tab_shot"), self.build_shot()),
            ("🌐  " + tr("tab_translation"), self.build_translation()),
        ]
        row = QHBoxLayout()
        row.setSpacing(8)
        self.tab_group = QButtonGroup(self)  # sorgt dafür, dass nur EIN Tab aktiv ist
        self.tab_pages = []
        for i, (label, page) in enumerate(tabs):
            btn = QPushButton(label)
            btn.setObjectName("tabbtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(btn, i)
            row.addWidget(btn)
            # Alle Tabs liegen untereinander, nur einer ist sichtbar.
            # (Versteckte Widgets brauchen keinen Platz.)
            layout.addWidget(page)
            self.tab_pages.append(page)
        row.addStretch()
        layout.insertLayout(1, row)
        self.tab_group.idClicked.connect(self.show_tab)
        layout.addStretch()
        self.show_tab(tab)

    def show_tab(self, index: int):
        self.current_tab = index
        self.tab_group.button(index).setChecked(True)
        for i, page in enumerate(self.tab_pages):
            page.setVisible(i == index)

    @staticmethod
    def tab_widget() -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        return w, lay

    def save_layer(self):
        layer_config.save(self.layer)

    # ------------------------------------------------------------------
    # Tab: General – Community, Sprache, Ordner, Über
    # ------------------------------------------------------------------
    def build_general(self) -> QWidget:
        w, lay = self.tab_widget()

        card, box = make_card(tr("community"))
        box.addWidget(dim(tr("community_hint")))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(button("💬  Discord", open_url(DISCORD_URL)))
        row.addWidget(button("☕  " + tr("kofi"), open_url(DONATE_URL)))
        row.addWidget(button("👥  VRChat Group", open_url(VRCHAT_GROUP_URL)))
        row.addWidget(button("🐙  GitHub", open_url(GITHUB_URL)))
        row.addStretch()
        box.addLayout(row)
        lay.addWidget(card)

        self.add_language_card(lay)
        self.add_folders_card(lay)
        self.add_cleanup_card(lay)
        self.add_wayvr_card(lay)

        card, box = make_card(tr("about"))
        box.addWidget(QLabel(f"LinuxVR-ViewShot  v{VERSION}"))
        box.addWidget(dim(tr("about_text")))
        lay.addWidget(card)
        return w

    # ------------------------------------------------------------------
    # Tab: Shot – Rahmengröße, Auge, Ausnahmen
    # (alles landet in layer.json und wirkt sofort im Layer)
    # ------------------------------------------------------------------
    def build_shot(self) -> QWidget:
        w, lay = self.tab_widget()
        card, box = make_card(tr("frame_size"))
        box.addWidget(dim(tr("frame_size_hint")))

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("frame_bigger")))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 15)  # cm
        slider.setValue(int(self.layer["frame_inset_cm"]))
        row.addWidget(slider, 1)
        row.addWidget(QLabel(tr("frame_smaller")))
        box.addLayout(row)

        value = QLabel()
        value.setObjectName("cardtitle")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(value)

        def changed(cm: int):
            value.setText(tr("frame_value", cm=cm))
            self.layer["frame_inset_cm"] = cm
            self.save_layer()

        slider.valueChanged.connect(changed)
        value.setText(tr("frame_value", cm=slider.value()))
        box.addWidget(button("↺  " + tr("reset"), lambda: slider.setValue(layer_config.DEFAULTS["frame_inset_cm"])),
                      alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)

        # --- Auge ---
        card, box = make_card(tr("eye"))
        box.addWidget(dim(tr("eye_hint")))
        row = QHBoxLayout()
        row.addWidget(QLabel("👁 " + tr("left")))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setSingleStep(5)
        slider.setPageStep(25)
        slider.setValue(int(self.layer["eye_mix"]))
        row.addWidget(slider, 1)
        row.addWidget(QLabel(tr("right") + " 👁"))
        box.addLayout(row)

        value = QLabel()
        value.setObjectName("cardtitle")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(value)

        def changed(right: int):
            source = tr("right") if right > 50 else tr("left")
            value.setText(tr("eye_value", left=100 - right, right=right, source=source))
            self.layer["eye_mix"] = right
            self.save_layer()

        slider.valueChanged.connect(changed)
        changed(slider.value())
        box.addWidget(button("↺  " + tr("reset"), lambda: slider.setValue(layer_config.DEFAULTS["eye_mix"])),
                      alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)

        # --- Erkennung & Tasten ---
        self.add_buttons_card(lay)

        # --- Ausnahmen ---
        card, box = make_card(tr("excluded"))
        box.addWidget(dim(tr("excluded_hint")))
        self.excluded = QListWidget()
        self.excluded.addItems(self.layer["excluded_apps"])
        self.excluded.setFixedHeight(110)
        box.addWidget(self.excluded)

        row = QHBoxLayout()
        self.new_app = QLineEdit()
        self.new_app.setPlaceholderText(tr("excluded_placeholder"))
        self.new_app.returnPressed.connect(self.add_excluded)
        row.addWidget(self.new_app, 1)
        row.addWidget(button("＋  " + tr("add"), self.add_excluded, "sendbtn"))
        row.addWidget(button("🗑  " + tr("remove"), self.remove_excluded))
        box.addLayout(row)
        box.addWidget(dim(tr("excluded_restart")))
        lay.addWidget(card)
        return w

    def add_buttons_card(self, lay: QVBoxLayout):
        """Erkennung (automatisch / manuell in VR) + welche Trigger was tun."""
        card, box = make_card(tr("buttons_title"))
        box.addWidget(dim(tr("buttons_hint")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.layer_combos = {}
        rows = [
            ("detect_mode", tr("detect_mode"), [("auto", tr("detect_auto")), ("manual", tr("detect_manual"))]),
            ("shutter", tr("shutter"), [(c, tr("combo_" + c)) for c in layer_config.COMBOS]),
            ("mode_button", tr("mode_button"), [(c, tr("combo_" + c)) for c in layer_config.COMBOS]),
        ]
        for r, (key, label, items) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            combo = QComboBox()
            for value, text in items:
                combo.addItem(text, value)
            combo.currentIndexChanged.connect(lambda _, k=key, c=combo: self.layer_combo_changed(k, c))
            grid.addWidget(combo, r, 1)
            self.layer_combos[key] = combo
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        self.buttons_note = dim("")
        box.addWidget(self.buttons_note)
        lay.addWidget(card)
        self.sync_layer()

    def layer_combo_changed(self, key: str, combo: QComboBox):
        # layer_config.update lädt frisch → überschreibt nichts von der Main-Seite
        fresh = layer_config.update(key, combo.currentData())
        for k in self.layer_combos:
            self.layer[k] = fresh[k]
        self.sync_layer()
        self.layer_changed.emit()

    def sync_layer(self):
        """Dropdowns an layer.json anpassen (auch nach Änderung auf der Main-Seite)."""
        fresh = layer_config.load()
        for key, combo in self.layer_combos.items():
            self.layer[key] = fresh[key]
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(fresh[key])))
            combo.blockSignals(False)
        manual = fresh["detect_mode"] == "manual"
        self.layer_combos["mode_button"].setEnabled(manual)
        self.buttons_note.setText(tr("buttons_manual_note") if manual else tr("buttons_auto_note"))

    def add_excluded(self):
        name = self.new_app.text().strip()
        if name and name.lower() not in [a.lower() for a in self.layer["excluded_apps"]]:
            self.layer["excluded_apps"].append(name)
            self.excluded.addItem(name)
            self.save_layer()
        self.new_app.clear()

    def remove_excluded(self):
        row = self.excluded.currentRow()
        if row >= 0:
            self.excluded.takeItem(row)
            del self.layer["excluded_apps"][row]
            self.save_layer()

    # ------------------------------------------------------------------
    # Karten für den General-Tab
    # ------------------------------------------------------------------
    def add_language_card(self, lay: QVBoxLayout):
        card, box = make_card(tr("language"))
        self.lang = QComboBox()
        self.lang.addItem("Deutsch", "de")   # sichtbarer Text, gespeicherter Wert
        self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(max(0, self.lang.findData(self.cfg["language"])))
        self.lang.setFixedWidth(200)
        # erst NACH dem Setzen verbinden, sonst feuert es schon beim Start
        self.lang.currentIndexChanged.connect(lambda _: self.language_changed.emit(self.lang.currentData()))
        box.addWidget(self.lang)
        lay.addWidget(card)

    def add_cleanup_card(self, lay: QVBoxLayout):
        """Beim Beenden QR-/Text-Fotos löschen (Standard: aus)."""
        card, box = make_card(tr("cleanup_title"))
        box.addWidget(dim(tr("cleanup_hint")))
        for key in ("cleanup_qr", "cleanup_text"):
            check = QCheckBox(tr(key))
            check.setChecked(bool(self.cfg[key]))
            check.toggled.connect(lambda on, k=key: self.save_cfg(k, on))
            box.addWidget(check)
        lay.addWidget(card)

    def add_wayvr_card(self, lay: QVBoxLayout):
        """WayVR-Design von Cubee + ViewShot-Knopf auf der Uhr."""
        from core import wayvr_theme
        card, box = make_card(tr("wayvr_title"))
        box.addWidget(dim(tr("wayvr_hint")))
        row = QHBoxLayout()
        self.wayvr_btn = button("", self.install_wayvr, "sendbtn")
        self.wayvr_btn.setMinimumHeight(40)
        row.addWidget(self.wayvr_btn)
        row.addWidget(button("🐙  " + tr("wayvr_source"), open_url(wayvr_theme.SOURCE_URL)))
        row.addStretch()
        box.addLayout(row)
        self.wayvr_status = QLabel()
        self.wayvr_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self.wayvr_status)
        self._wayvr_done.connect(self.on_wayvr_done)
        self.update_wayvr_btn()
        lay.addWidget(card)

    def update_wayvr_btn(self):
        from core import wayvr_theme
        key = "wayvr_reinstall" if wayvr_theme.installed() else "wayvr_install"
        self.wayvr_btn.setText("🎨  " + tr(key))
        self.wayvr_btn.setEnabled(True)

    def install_wayvr(self):
        from core import wayvr_theme
        self.wayvr_btn.setEnabled(False)
        self.wayvr_btn.setText("⏳  " + tr("wayvr_installing"))
        self.wayvr_status.clear()

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                r = wayvr_theme.install()
                lines = [tr("wayvr_ok", n=r["files"], path=wayvr_theme.WAYVR_DIR)]
                if r["backup"]:
                    lines.append(tr("wayvr_backup", path=r["backup"]))
                if not r["button"]:
                    lines.append(tr("wayvr_no_button"))
                if not r["wayvrctl"]:
                    lines.append(tr("wayvr_no_ctl"))
                lines.append(tr("wayvr_restart"))
                self._wayvr_done.emit(True, "\n".join(lines))
            except Exception as e:  # noqa: BLE001 – Netz, Rechte, GitHub geändert …
                self._wayvr_done.emit(False, f"{tr('wayvr_failed')}: {e}")

        threading.Thread(target=work, daemon=True).start()

    def on_wayvr_done(self, ok: bool, text: str):
        self.wayvr_status.setObjectName("ok" if ok else "bad")
        self.wayvr_status.style().polish(self.wayvr_status)
        self.wayvr_status.setText(text)
        self.update_wayvr_btn()

    def save_cfg(self, key: str, value):
        self.cfg[key] = value
        config.save(self.cfg)

    def add_folders_card(self, lay: QVBoxLayout):
        card, box = make_card(tr("folders"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        rows = [
            (tr("photo_folder"), paths.photo_dir()),
            (tr("log_file"), paths.LOG_FILE),
            (tr("settings_folder"), paths.CONFIG_DIR),
        ]
        for r, (name, path) in enumerate(rows):
            grid.addWidget(QLabel(name), r, 0)
            value = QLabel(str(path))
            value.setObjectName("dim")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(value, r, 1)
            # p=path: merkt sich den Pfad DIESER Zeile (sonst hätten alle den letzten)
            grid.addWidget(button(tr("open"), lambda _, p=path: open_path(p)), r, 2)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        lay.addWidget(card)

    # ------------------------------------------------------------------
    # Tab: Übersetzung
    # ------------------------------------------------------------------
    def set_cfg(self, key: str, value):
        """Wert speichern und der Main-Seite Bescheid geben."""
        self.cfg[key] = value
        config.save(self.cfg)
        self.translation_changed.emit()

    def line_edit(self, key: str, placeholder: str = "", secret: bool = False) -> QLineEdit:
        """Eingabefeld, das sich selbst in ui.json speichert."""
        field = QLineEdit(self.cfg[key])
        field.setPlaceholderText(placeholder)
        if secret:
            field.setEchoMode(QLineEdit.EchoMode.Password)
        # erst beim Verlassen / Enter speichern, nicht bei jedem Buchstaben
        field.editingFinished.connect(lambda: self.set_cfg(key, field.text().strip()))
        return field

    def build_translation(self) -> QWidget:
        w, lay = self.tab_widget()

        # --- Dienst + Zielsprache -------------------------------------
        card, box = make_card(tr("tr_service"))
        box.addWidget(dim(tr("tr_service_hint")))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.method = QComboBox()
        for m in translation.METHODS:
            self.method.addItem(tr("tr_m_" + m), m)
        self.method.setCurrentIndex(max(0, self.method.findData(self.cfg["tr_method"])))
        grid.addWidget(QLabel(tr("tr_service")), 0, 0)
        grid.addWidget(self.method, 0, 1)

        self.tr_source_combo = language_combo(with_auto=True)
        self.tr_source_combo.currentIndexChanged.connect(
            lambda _: self.set_cfg("tr_source", self.tr_source_combo.currentData()))
        grid.addWidget(QLabel(tr("tr_source")), 1, 0)
        grid.addWidget(self.tr_source_combo, 1, 1)

        self.tr_target_combo = language_combo(with_auto=False)
        self.tr_target_combo.currentIndexChanged.connect(
            lambda _: self.set_cfg("tr_target", self.tr_target_combo.currentData()))
        grid.addWidget(QLabel(tr("tr_target")), 2, 0)
        grid.addWidget(self.tr_target_combo, 2, 1)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)

        auto = QCheckBox(tr("tr_auto"))
        auto.setChecked(bool(self.cfg["tr_auto"]))
        auto.toggled.connect(lambda on: self.set_cfg("tr_auto", on))
        box.addWidget(auto)

        # Texterkennung vorhanden?
        if ocr.available():
            ok = QLabel(tr("ocr_ok"))
            ok.setObjectName("ok")
        else:
            ok = QLabel(tr("ocr_missing", cmd=ocr.INSTALL_HINT))
            ok.setObjectName("bad")
            ok.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(ok)
        lay.addWidget(card)

        # --- Einstellungen des gewählten Dienstes ---------------------
        # Für jeden Dienst ein eigener Block; nur der gewählte ist sichtbar.
        card, box = make_card(tr("settings_folder"))
        self.method_blocks = {}

        def block(method: str) -> QVBoxLayout:
            widget = QWidget()
            b = QVBoxLayout(widget)
            b.setContentsMargins(0, 0, 0, 0)
            b.setSpacing(8)
            box.addWidget(widget)
            self.method_blocks[method] = widget
            return b

        # Lingva
        block(T.METHOD_LINGVA).addWidget(dim(tr("tr_lingva_info")))

        # Google
        b = block(T.METHOD_GOOGLE)
        b.addWidget(dim(tr("tr_google_info")))
        b.addWidget(QLabel(tr("api_key_optional")))
        b.addWidget(self.line_edit("tr_google_key", "AIza…", secret=True))

        # LibreTranslate lokal
        b = block(T.METHOD_LIBRE)
        info = dim(tr("tr_libre_info"))
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        b.addWidget(info)
        installed = T.libretranslate_installed()
        status = QLabel(tr("tr_libre_found") if installed else tr("tr_libre_not_installed"))
        status.setObjectName("ok" if installed else "dim")
        b.addWidget(status)
        # läuft ein Server? (auch Docker – dann ist nichts "installiert")
        row = QHBoxLayout()
        self.libre_status = QLabel()
        self.libre_status.setWordWrap(True)
        row.addWidget(self.libre_status, 1)
        self.libre_use_btn = button(tr("use_this"), self.use_found_libre)
        self.libre_use_btn.hide()
        row.addWidget(self.libre_use_btn)
        row.addWidget(button("↻  " + tr("check_again"), self.check_libre))
        b.addLayout(row)
        b.addWidget(QLabel(tr("server")))
        self.libre_url = self.line_edit("tr_libre_url", T.DEFAULT_LIBRE_URL)
        self.libre_url.editingFinished.connect(self.check_libre)
        b.addWidget(self.libre_url)
        self._libre_found.connect(self.on_libre_found)
        self.found_libre = ""

        # LibreTranslate online
        b = block(T.METHOD_LIBRE_ONLINE)
        b.addWidget(dim(tr("tr_online_info")))
        b.addWidget(QLabel(tr("server")))
        server = QComboBox()
        for label, value in T.LIBRE_ONLINE_SERVERS:
            server.addItem(label, value)
        custom_url = self.line_edit("tr_libre_online_url", "https://…")
        current = self.cfg["tr_libre_online_url"]
        preset = server.findData(current)
        server.setCurrentIndex(preset if preset >= 0 else server.findData(T.LIBRE_ONLINE_CUSTOM))
        custom_url.setVisible(server.currentData() == T.LIBRE_ONLINE_CUSTOM)

        def server_changed(_):
            value = server.currentData()
            custom_url.setVisible(value == T.LIBRE_ONLINE_CUSTOM)
            if value != T.LIBRE_ONLINE_CUSTOM:
                custom_url.setText(value)
                self.set_cfg("tr_libre_online_url", value)

        server.currentIndexChanged.connect(server_changed)
        b.addWidget(server)
        b.addWidget(custom_url)
        b.addWidget(QLabel(tr("api_key_optional")))
        b.addWidget(self.line_edit("tr_libre_online_key", "", secret=True))

        # DeepL
        b = block(T.METHOD_DEEPL)
        b.addWidget(dim(tr("tr_deepl_info")))
        b.addWidget(QLabel(tr("api_key")))
        b.addWidget(self.line_edit("tr_deepl_key", "xxxxxxxx-xxxx-…:fx", secret=True))

        # Eigene API
        b = block(T.METHOD_CUSTOM)
        b.addWidget(dim(tr("tr_custom_info")))
        snippet = QPlainTextEdit(self.cfg["tr_custom_snippet"])
        snippet.setFixedHeight(130)
        snippet.textChanged.connect(lambda: self.set_cfg("tr_custom_snippet", snippet.toPlainText()))
        b.addWidget(snippet)
        b.addWidget(button("↺  " + tr("tr_reset_example"), lambda: snippet.setPlainText(LIBRE_EXAMPLE)),
                    alignment=Qt.AlignmentFlag.AlignLeft)

        # Test-Knopf für alle Dienste
        row = QHBoxLayout()
        self.test_btn = button("🧪  " + tr("tr_test"), self.run_test, "sendbtn")
        row.addWidget(self.test_btn)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        row.addWidget(self.test_result, 1)
        box.addLayout(row)
        self._test_done.connect(self.on_test_done)
        lay.addWidget(card)

        def method_changed(_):
            m = self.method.currentData()
            self.show_method_block(m)
            self.test_result.clear()
            self.set_cfg("tr_method", m)

        self.method.currentIndexChanged.connect(method_changed)
        self.show_method_block(self.cfg["tr_method"])
        self.sync_translation()
        return w

    def show_method_block(self, method: str):
        for key, widget in self.method_blocks.items():
            widget.setVisible(key == method)
        if method == T.METHOD_LIBRE:
            self.check_libre()

    def sync_translation(self):
        """Dropdowns an ui.json anpassen (z. B. nach Änderung auf der Main-Seite).
        blockSignals: sonst würde das Setzen selbst wieder "geändert" melden."""
        for combo, key in ((self.method, "tr_method"), (self.tr_source_combo, "tr_source"),
                           (self.tr_target_combo, "tr_target")):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(self.cfg[key])))
            combo.blockSignals(False)
        self.show_method_block(self.cfg["tr_method"])

    # --- LibreTranslate: läuft ein Server? -------------------------------
    def check_libre(self):
        self.libre_status.setObjectName("dim")
        self.libre_status.style().polish(self.libre_status)
        self.libre_status.setText(tr("libre_checking"))
        self.libre_use_btn.hide()
        url = self.cfg["tr_libre_url"]
        threading.Thread(target=lambda: self._libre_found.emit(translation.find_libre(url) or ""),
                         daemon=True).start()

    def on_libre_found(self, url: str):
        self.found_libre = url
        configured = (self.cfg["tr_libre_url"] or T.DEFAULT_LIBRE_URL).rstrip("/")
        if not url:
            self.libre_status.setText(tr("libre_not_running"))
            self.libre_status.setObjectName("bad")
        elif url.rstrip("/") == configured:
            self.libre_status.setText(tr("libre_running", url=url))
            self.libre_status.setObjectName("ok")
        else:
            # läuft, aber unter einer anderen Adresse als eingestellt
            self.libre_status.setText(tr("libre_running_other", url=url))
            self.libre_status.setObjectName("ok")
            self.libre_use_btn.show()
        self.libre_status.style().polish(self.libre_status)

    def use_found_libre(self):
        self.libre_url.setText(self.found_libre)
        self.set_cfg("tr_libre_url", self.found_libre)
        self.check_libre()

    def run_test(self):
        self.test_btn.setEnabled(False)
        self.test_result.setObjectName("")
        self.test_result.setText(tr("tr_testing"))
        cfg = dict(self.cfg)
        errors = []

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                out = translation.translate_text(tr("tr_test_text"), cfg, log=errors.append)
                note = f"   ({errors[0]})" if errors else ""  # z. B. "DeepL failed – Lingva übernommen"
                self._test_done.emit("✔ " + out + note)
            except Exception as e:  # noqa: BLE001
                self._test_done.emit("✘ " + ("; ".join(errors) or str(e)))

        threading.Thread(target=work, daemon=True).start()

    def on_test_done(self, text: str):
        self.test_btn.setEnabled(True)
        self.test_result.setObjectName("ok" if text.startswith("✔") else "bad")
        self.test_result.style().polish(self.test_result)
        self.test_result.setText(text)
