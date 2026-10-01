"""
ui/pages/options_page.py – Optionen mit Tabs (wie bei OSC-DreamChatbox):

    ⚙ General      Community-Links (Discord, Ko-fi …), Sprache, Ordner, Über
    📸 Shot        Rahmengröße, linkes/rechtes Auge, Symbol-Ecke, 🔁 Lens, 🪟 Panel, 🥽 Overlay, Ausnahme-Programme
    🌐 Übersetzung Dienst (Lingva, Google, LibreTranslate, DeepL, eigene API,
                   KI: Claude Code / Gemini / ChatGPT / eigener Befehl), Zielsprache

Die Shot-Einstellungen werden in layer.json gespeichert – der Layer übernimmt
Änderungen sofort, auch während das Spiel läuft.

Neuer Tab? In build_tabs() eine Zeile ("Name", self.build_xyz()) ergänzen.
"""

import shutil
import threading

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QPlainTextEdit, QPushButton, QRadioButton, QSlider,
                             QVBoxLayout, QWidget)

from core import clipboard, config, i18n, layer_config, ocr, overlay, paths, translation
from core import llm_translator as L
from core import vision
from core import translators as T
from core.custom_translator import LIBRE_EXAMPLE
from core.i18n import tr
from core.version import VERSION
from ui.widgets import fill_methods, make_card, open_path, page_title, select_data

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


CUSTOM_MODEL = "__custom__"  # Eintrag "✏ Anderes Modell …" (öffnet ein Eingabefeld)


def fill_model_combo(combo: QComboBox, method: str, current: str):
    """Modelle der KI-Vorlage ins Dropdown. Leer = Standard-Modell der Vorlage.
    Ein selbst eingetipptes Modell steht zusätzlich mit in der Liste."""
    current = (current or L.DEFAULTS.get(L.MODEL_KEYS.get(method, ""), "")).strip()
    models = L.models_for(method)  # Bild-LLM: installierte Ollama-Modelle zuerst
    if current and current not in models:
        models.append(current)
    combo.blockSignals(True)
    combo.clear()
    combo.setProperty("llm_method", method)
    for model in models:
        combo.addItem(model, model)
    combo.addItem("✏  " + tr("tr_model_other"), CUSTOM_MODEL)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    combo.setProperty("llm_model", combo.currentData())
    combo.blockSignals(False)


def model_combo(method: str, current: str, on_change) -> QComboBox:
    """Modell-Dropdown (Klick öffnet die Liste); on_change(neues_modell) nach Auswahl.
    "✏ Anderes Modell …" fragt nach einem Namen – für neue Modelle."""
    combo = QComboBox()
    fill_model_combo(combo, method, current)

    def chosen(_index):
        model = combo.currentData()
        if model == CUSTOM_MODEL:
            from PyQt6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(combo, tr("tr_model"), tr("tr_model_other"))
            text = text.strip()
            model = text if ok and text else combo.property("llm_model")
            fill_model_combo(combo, combo.property("llm_method"), model)
        combo.setProperty("llm_model", model)
        on_change(model)

    combo.activated.connect(chosen)
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
        self.add_main_page_card(lay)
        self.add_folders_card(lay)
        self.add_cleanup_card(lay)
        self.add_wayvr_card(lay)
        self.add_clipboard_card(lay)

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
        frame_slider = QSlider(Qt.Orientation.Horizontal)
        frame_slider.setRange(0, 15)  # cm
        frame_slider.setValue(int(self.layer["frame_inset_cm"]))
        row.addWidget(frame_slider, 1)
        row.addWidget(QLabel(tr("frame_smaller")))
        box.addLayout(row)

        frame_value = QLabel()
        frame_value.setObjectName("cardtitle")
        frame_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(frame_value)

        def frame_changed(cm: int):
            frame_value.setText(tr("frame_value", cm=cm))
            self.layer["frame_inset_cm"] = cm
            self.save_layer()

        frame_slider.valueChanged.connect(frame_changed)
        frame_value.setText(tr("frame_value", cm=frame_slider.value()))
        box.addWidget(button("↺  " + tr("reset"), lambda: frame_slider.setValue(layer_config.DEFAULTS["frame_inset_cm"])),
                      alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)

        # --- Auge ---
        card, box = make_card(tr("eye"))
        box.addWidget(dim(tr("eye_hint")))
        row = QHBoxLayout()
        row.addWidget(QLabel("👁 " + tr("left")))
        eye_slider = QSlider(Qt.Orientation.Horizontal)
        eye_slider.setRange(0, 100)
        eye_slider.setSingleStep(5)
        eye_slider.setPageStep(25)
        eye_slider.setValue(int(self.layer["eye_mix"]))
        row.addWidget(eye_slider, 1)
        row.addWidget(QLabel(tr("right") + " 👁"))
        box.addLayout(row)

        eye_value = QLabel()
        eye_value.setObjectName("cardtitle")
        eye_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(eye_value)

        def eye_changed(right: int):
            source = tr("right") if right > 50 else tr("left")
            eye_value.setText(tr("eye_value", left=100 - right, right=right, source=source))
            self.layer["eye_mix"] = right
            self.save_layer()

        eye_slider.valueChanged.connect(eye_changed)
        eye_changed(eye_slider.value())
        box.addWidget(button("↺  " + tr("reset"), lambda: eye_slider.setValue(layer_config.DEFAULTS["eye_mix"])),
                      alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(card)

        # --- Erkennung & Tasten ---
        self.add_buttons_card(lay)

        # --- Ecke des Typ-Symbols ---
        self.add_icon_position_card(lay)

        # --- 🔁 Lens ---
        self.add_live_card(lay)

        # --- 🪟 Übersetzungs-Panel in VR ---
        self.add_panel_card(lay)

        # --- 🥽 Übersetzung in VR über dem Original ---
        self.add_overlay_card(lay)

        # --- ⚙ Ohne App (Hintergrund-Dienst) ---
        self.add_daemon_card(lay)

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
        box = getattr(self, "panel_edit_box", None)
        if box is not None:
            box.blockSignals(True)
            box.setChecked(bool(fresh.get("panel_edit")))
            box.blockSignals(False)
        for key, combo in self.layer_combos.items():
            self.layer[key] = fresh[key]
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(fresh[key])))
            combo.blockSignals(False)
        manual = fresh["detect_mode"] == "manual"
        self.buttons_note.setText(tr("buttons_manual_note") if manual else tr("buttons_auto_note"))

    def add_icon_position_card(self, lay: QVBoxLayout):
        """Ecke für das Typ-Symbol (🪄 / 🖼 / 📝 / 🔳 / 🔁)."""
        self.icon_position_card, box = make_card(tr("icon_position"))
        box.addWidget(dim(tr("icon_position_hint")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        # Anordnung wie im Rahmen: oben links | oben rechts / unten links | unten rechts
        cells = {"top_left": (0, 0), "top_right": (0, 1), "bottom_left": (1, 0), "bottom_right": (1, 1)}
        self.icon_group = QButtonGroup(self)  # mit Parent, sonst räumt Python die Gruppe weg
        current = self.layer.get("icon_position", layer_config.DEFAULTS["icon_position"])
        for value in layer_config.ICON_POSITIONS:
            radio = QRadioButton(tr(value))
            radio.setChecked(value == current)
            radio.toggled.connect(lambda on, v=value: on and self.icon_position_changed(v))
            self.icon_group.addButton(radio)
            grid.addWidget(radio, *cells[value])
        box.addLayout(grid)
        box.addWidget(button("↺  " + tr("reset"), self.icon_group.buttons()[
            layer_config.ICON_POSITIONS.index(layer_config.DEFAULTS["icon_position"])].click),
            alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.icon_position_card)

    def add_live_card(self, lay: QVBoxLayout):
        """🔁 Lens: statt eines Fotos denselben Bereich alle X s neu fotografieren + übersetzen."""
        card, box = make_card("🔁  " + tr("live_card"))
        box.addWidget(dim(tr("live_hint")))

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("live_every")))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(1, 10)  # Sekunden
        slider.setValue(int(self.layer.get("live_interval_s", layer_config.DEFAULTS["live_interval_s"])))
        row.addWidget(slider, 1)
        value = QLabel()
        value.setMinimumWidth(50)
        row.addWidget(value)
        box.addLayout(row)
        box.addWidget(dim(tr("live_note")))

        def interval_changed(secs: int):
            value.setText(tr("live_seconds", s=secs))
            self.layer["live_interval_s"] = layer_config.update("live_interval_s", secs)["live_interval_s"]

        value.setText(tr("live_seconds", s=slider.value()))
        slider.valueChanged.connect(interval_changed)
        lay.addWidget(card)

    def add_panel_card(self, lay: QVBoxLayout):
        """🪟 Panel mit Foto (①②③) + Übersetzung in VR: wo es hängt, Bearbeiten, Reset."""
        from ui import vr_panel
        card, box = make_card("🪟  " + tr("panel_card"))
        box.addWidget(dim(tr("panel_hint")))
        on = QCheckBox(tr("panel_on"))
        on.setChecked(bool(self.layer.get("panel", True)))
        box.addWidget(on)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.addWidget(QLabel(tr("panel_anchor")), 0, 0)
        anchor = QComboBox()
        for value in ("left", "right", "head", "world"):
            anchor.addItem(tr("panel_anchor_" + value), value)
        anchor.setCurrentIndex(max(0, anchor.findData(self.layer.get("panel_anchor", "left"))))
        grid.addWidget(anchor, 0, 1)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        orow = QHBoxLayout()
        orow.addWidget(QLabel(tr("panel_opacity")))
        opacity = QSlider(Qt.Orientation.Horizontal)
        opacity.setRange(3, 10)  # × 10 %
        opacity.setValue(round(float(self.layer.get("panel_opacity", 100)) / 10))
        orow.addWidget(opacity, 1)
        opacity_value = QLabel(f"{opacity.value() * 10} %")
        opacity_value.setMinimumWidth(60)
        orow.addWidget(opacity_value)
        box.addLayout(orow)
        # Größe in VR (Breite) – steht in panel_pose.json, die legt der Layer an
        srow = QHBoxLayout()
        srow.addWidget(QLabel(tr("panel_size")))
        size = QSlider(Qt.Orientation.Horizontal)
        size.setRange(*vr_panel.SIZE_CM)
        size.setValue(vr_panel.width_cm() or 32)
        srow.addWidget(size, 1)
        size_value = QLabel(f"{size.value()} cm" if vr_panel.width_cm() else tr("panel_size_later"))
        size_value.setMinimumWidth(60)
        srow.addWidget(size_value)
        box.addLayout(srow)

        def size_changed(cm: int):
            size_value.setText(f"{cm} cm" if vr_panel.set_width_cm(cm) else tr("panel_size_later"))

        size.valueChanged.connect(size_changed)

        def opacity_changed(step: int):
            opacity_value.setText(f"{step * 10} %")
            self.layer["panel_opacity"] = layer_config.update("panel_opacity", step * 10)["panel_opacity"]

        opacity.valueChanged.connect(opacity_changed)
        edit = QCheckBox(tr("panel_edit_mode"))
        edit.setChecked(bool(self.layer.get("panel_edit")))
        box.addWidget(edit)
        box.addWidget(dim(tr("panel_edit_hint")))
        reset = button("⟲  " + tr("panel_reset"), vr_panel.reset_position)
        box.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)

        # 🔘 Knopf (wie bei WayVR): auf/zu, nach Foto öffnen, Größe, Farbe
        knob = QCheckBox(tr("panel_button"))
        knob.setChecked(bool(self.layer.get("panel_button", True)))
        knob.toggled.connect(lambda c: self.layer.__setitem__(
            "panel_button", layer_config.update("panel_button", c)["panel_button"]))
        box.addWidget(knob)
        box.addWidget(dim(tr("panel_button_hint")))
        auto_open = QCheckBox(tr("panel_open_on_shot"))
        auto_open.setChecked(bool(self.layer.get("panel_open_on_shot", True)))
        auto_open.toggled.connect(lambda c: self.layer.__setitem__(
            "panel_open_on_shot", layer_config.update("panel_open_on_shot", c)["panel_open_on_shot"]))
        box.addWidget(auto_open)
        brow = QHBoxLayout()
        brow.addWidget(QLabel(tr("panel_button_size")))
        bsize = QSlider(Qt.Orientation.Horizontal)
        bsize.setRange(*vr_panel.BUTTON_CM)
        bsize.setValue(vr_panel.button_cm() or 3)
        brow.addWidget(bsize, 1)
        bsize_value = QLabel(f"{bsize.value()} cm" if vr_panel.button_cm() else tr("panel_size_later"))
        bsize_value.setMinimumWidth(60)
        brow.addWidget(bsize_value)
        box.addLayout(brow)
        bsize.valueChanged.connect(lambda cm: bsize_value.setText(
            f"{cm} cm" if vr_panel.set_button_cm(cm) else tr("panel_size_later")))
        crow = QHBoxLayout()
        crow.addWidget(QLabel(tr("panel_button_color")))
        swatch = QPushButton(tr("panel_button_pick"))
        swatch.setObjectName("linkbtn")

        def show_color():
            c = str(self.layer.get("panel_button_color", vr_panel.BUTTON_COLORS[0]))
            swatch.setStyleSheet(f"border-left: 28px solid {c};")

        def pick_color():
            from PyQt6.QtGui import QColor
            from PyQt6.QtWidgets import QColorDialog
            color = QColorDialog.getColor(QColor(str(self.layer.get("panel_button_color", "#5b8dc9"))), self,
                                          tr("panel_button_color"))
            if color.isValid():
                self.layer["panel_button_color"] = layer_config.update("panel_button_color", color.name())[
                    "panel_button_color"]
                show_color()

        swatch.clicked.connect(pick_color)
        show_color()
        crow.addWidget(swatch)
        crow.addStretch()
        box.addLayout(crow)

        def toggled(checked: bool):
            self.layer["panel"] = layer_config.update("panel", checked)["panel"]
            for w in (anchor, edit, reset, opacity, size, knob, auto_open, bsize, swatch):
                w.setEnabled(checked)

        def anchor_changed(_):
            # anderer Anker → Position passt nicht mehr: neu vor dem Kopf
            self.layer["panel_anchor"] = layer_config.update("panel_anchor", anchor.currentData())["panel_anchor"]
            vr_panel.reset_position()

        on.toggled.connect(toggled)
        anchor.currentIndexChanged.connect(anchor_changed)
        edit.toggled.connect(lambda c: self.layer.__setitem__("panel_edit", layer_config.update("panel_edit", c)["panel_edit"]))
        self.panel_edit_box = edit  # wird im Panel (VR) umgeschaltet → hier nachziehen
        toggled(on.isChecked())
        lay.addWidget(card)

    def add_daemon_card(self, lay: QVBoxLayout):
        """⚙ Übersetzen + Panel auch ohne offene App (Rust-Dienst, startet mit dem VR-Spiel)."""
        from core import daemon
        card, box = make_card("⚙  " + tr("daemon_card"))
        box.addWidget(dim(tr("daemon_hint")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.addWidget(QLabel(tr("daemon_start")), 0, 0)
        mode = QComboBox()
        for value in layer_config.DAEMON_MODES:
            mode.addItem(tr("daemon_" + value), value)
        mode.setCurrentIndex(max(0, mode.findData(self.layer.get("daemon", "all"))))
        grid.addWidget(mode, 0, 1)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)

        # Spiele zum Anhaken: zuletzt gespielte (layer.log) + schon ausgewählte
        games = QWidget()
        gbox = QVBoxLayout(games)
        gbox.setContentsMargins(0, 0, 0, 0)
        gbox.addWidget(dim(tr("daemon_games_hint")))
        checks = QVBoxLayout()
        gbox.addLayout(checks)
        row = QHBoxLayout()
        new_game = QLineEdit()
        new_game.setPlaceholderText(tr("daemon_game_placeholder"))
        row.addWidget(new_game, 1)
        box.addWidget(games)

        def selected() -> list[str]:
            return list(self.layer.get("daemon_apps") or [])

        def save_games(names: list[str]):
            self.layer["daemon_apps"] = layer_config.update("daemon_apps", names)["daemon_apps"]

        def add_check(name: str):
            check = QCheckBox(name)
            check.setChecked(name in selected())
            check.toggled.connect(lambda on, n=name: save_games(
                [g for g in selected() if g != n] + ([n] if on else [])))
            checks.addWidget(check)

        known = selected() + [g for g in daemon.recent_apps() if g not in selected()]
        for name in known:
            add_check(name)

        def add_game():
            name = new_game.text().strip()
            new_game.clear()
            if not name or name in selected():
                return
            save_games(selected() + [name])
            add_check(name)

        new_game.returnPressed.connect(add_game)
        row.addWidget(button("＋  " + tr("add"), add_game))
        gbox.addLayout(row)

        status = dim("")
        box.addWidget(status)

        def update():
            games.setVisible(mode.currentData() == "selected")
            if not daemon.installed():
                status.setText("⚠  " + tr("daemon_not_installed"))
            elif mode.currentData() == "off":
                status.setText(tr("daemon_off_status"))
            else:
                status.setText("✔  " + tr("daemon_ready"))

        def mode_changed(_):
            self.layer["daemon"] = layer_config.update("daemon", mode.currentData())["daemon"]
            update()

        mode.currentIndexChanged.connect(mode_changed)
        update()
        lay.addWidget(card)

    def add_overlay_card(self, lay: QVBoxLayout):
        """🥽 Nur 🔁 Lens: Übersetzung als graue Kästchen in VR über den Originaltext (Fotos → 🪟 Panel)."""
        card, box = make_card("🥽  " + tr("overlay_card"))
        box.addWidget(dim(tr("overlay_hint")))
        on = QCheckBox(tr("overlay_on"))
        on.setChecked(bool(self.layer.get("overlay", True)))
        box.addWidget(on)
        def toggled(checked: bool):
            self.layer["overlay"] = layer_config.update("overlay", checked)["overlay"]
            if not checked:
                overlay.clear()  # sofort weg aus VR

        on.toggled.connect(toggled)
        lay.addWidget(card)

    def icon_position_changed(self, position: str):
        """Neue Ecke → layer.json (der Layer übernimmt sie sofort)."""
        self.layer["icon_position"] = layer_config.update("icon_position", position)["icon_position"]

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
        self.lang.addItem("Français", "fr")
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

    def add_clipboard_card(self, lay: QVBoxLayout):
        """Kopiertes zusätzlich per wl-copy an den Desktop (sonst bleibt es in WayVR)."""
        card, box = make_card(tr("clip_title"))
        box.addWidget(dim(tr("clip_hint")))
        check = QCheckBox(tr("clip_mirror"))
        check.setChecked(bool(self.cfg["clipboard_mirror"]))

        def toggled(on: bool):
            clipboard.enabled = on
            self.save_cfg("clipboard_mirror", on)

        check.toggled.connect(toggled)
        box.addWidget(check)
        row = QHBoxLayout()
        self.clip_status = QLabel()
        self.clip_status.setWordWrap(True)
        self.clip_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.clip_status, 1)
        # 📦 Knopf: wl-clipboard mit dem Paketmanager der Distro installieren
        self.clip_btn = button("📦  " + tr("clip_install"), self.install_wl_clipboard, "sendbtn")
        self.clip_btn.setMinimumHeight(40)
        row.addWidget(self.clip_btn)
        box.addLayout(row)
        self.clip_process = None
        self.update_clip_status()
        lay.addWidget(card)

    def update_clip_status(self, failed: bool = False):
        from core import pkginstall
        found = shutil.which("wl-copy") is not None
        if found:
            text = tr("clip_ok")
        else:
            text = tr("clip_missing", cmd=pkginstall.manual_command("wl-clipboard"))
            if failed:
                text = tr("clip_install_failed") + "\n" + text
        self.clip_status.setText(text)
        self.clip_status.setObjectName("ok" if found else "bad")
        self.clip_status.style().polish(self.clip_status)
        can = not found and pkginstall.install_command("wl-clipboard") is not None
        self.clip_btn.setVisible(can)
        self.clip_btn.setEnabled(True)
        self.clip_btn.setText("📦  " + tr("clip_install"))

    def install_wl_clipboard(self):
        """pkexec fragt das Passwort in einem Fenster ab – kein Terminal nötig."""
        from PyQt6.QtCore import QProcess
        from core import pkginstall
        cmd = pkginstall.install_command("wl-clipboard")
        if cmd is None or self.clip_process is not None:
            return
        self.clip_btn.setEnabled(False)
        self.clip_btn.setText("⏳  " + tr("clip_installing"))
        self.clip_status.setText(tr("clip_password"))
        self.clip_process = QProcess(self)

        def finished(code, _status):
            self.clip_process = None
            self.update_clip_status(failed=code != 0)

        self.clip_process.finished.connect(finished)
        self.clip_process.start(cmd[0], cmd[1:])

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

    def add_main_page_card(self, lay: QVBoxLayout):
        """Was auf der Main-Seite zu sehen ist (🕘 Verlauf, Standard aus)."""
        card, box = make_card(tr("main_page_card"))
        hist = QCheckBox(tr("history_option"))
        hist.setChecked(bool(self.cfg.get("history")))
        hist.toggled.connect(lambda on: self.set_cfg("history", on))
        box.addWidget(hist)
        lay.addWidget(card)

    def add_folders_card(self, lay: QVBoxLayout):
        card, box = make_card(tr("folders"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        rows = [
            (tr("photo_folder"), paths.photo_dir()),
            (tr("log_file"), paths.LOG_FILE),
            (tr("ui_log"), paths.UI_LOG),
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

        # Reihenfolge: 1. ⭐ Favoriten  2. Dienst + Sprache  3. Einstellungen des Dienstes
        # --- ⭐ Favoriten: nur diese stehen im Main-Dropdown -----------
        self.add_favorites_card(lay)

        # --- Dienst + Zielsprache -------------------------------------
        card, box = make_card(tr("tr_service"))
        box.addWidget(dim(tr("tr_service_hint")))
        box.addWidget(dim(tr("tr_only_configured")))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        # Modus: 🤖 Automatisch (Main-KI teilt zu) / ✋ Manuell (Aufgabe selbst wählen)
        self.route_combo = QComboBox()
        self.route_combo.addItem(tr("tr_route_auto"), translation.ROUTE_AUTO)
        self.route_combo.addItem(tr("tr_route_manual"), translation.ROUTE_MANUAL)
        self.route_combo.currentIndexChanged.connect(self.route_changed)
        grid.addWidget(QLabel(tr("tr_route")), 0, 0)
        grid.addWidget(self.route_combo, 0, 1, 1, 2)
        self.route_hint = dim("")
        grid.addWidget(self.route_hint, 1, 1, 1, 2)

        self.method = QComboBox()
        fill_methods(self.method, translation.METHODS)  # ── Übersetzung ── / ── KI-Übersetzung ──
        select_data(self.method, self.cfg["tr_method"])
        grid.addWidget(QLabel(tr("tr_main")), 2, 0)
        grid.addWidget(self.method, 2, 1, 1, 2)
        self.task_updates = []  # Kontext-/Frage-Zeilen auffrischen, wenn sich Main ändert
        self.add_task_rows(grid, 3)  # Zeilen 3–6

        self.tr_source_combo = language_combo(with_auto=True)
        self.tr_source_combo.currentIndexChanged.connect(
            lambda _: self.set_cfg("tr_source", self.tr_source_combo.currentData()))
        grid.addWidget(QLabel(tr("tr_source")), 7, 0)
        grid.addWidget(self.tr_source_combo, 7, 1, 1, 2)

        self.tr_target_combo = language_combo(with_auto=False)
        self.tr_target_combo.currentIndexChanged.connect(
            lambda _: self.set_cfg("tr_target", self.tr_target_combo.currentData()))
        grid.addWidget(QLabel(tr("tr_target")), 8, 0)
        grid.addWidget(self.tr_target_combo, 8, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        # ☁ / 🔒 Wohin geht der Text? (wechselt mit dem gewählten Dienst)
        self.privacy_note = dim("")
        box.addWidget(self.privacy_note)

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
        # welchen Dienst einrichten? – unabhängig von Main (Main muss man dafür nicht umstellen)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("tr_settings_for")))
        self.settings_method = QComboBox()
        fill_methods(self.settings_method, translation.METHODS)
        select_data(self.settings_method, self.cfg["tr_method"])
        self.settings_method.currentIndexChanged.connect(self.settings_method_changed)
        row.addWidget(self.settings_method, 1)
        box.addLayout(row)

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

        # KI-Vorlagen: Programm installiert? (+ Knopf) · Anmelden · Modell
        self.model_combos = {}
        self.llm_status = {}      # method → (Status-Label, Installier-Knopf)
        self.llm_process = None
        self.llm_login_btns = {}
        # nach 🔑: alle 2 s schauen, ob die Anmeldung da ist (max. 5 min)
        from PyQt6.QtCore import QTimer
        self.login_timer = QTimer(self)
        self.login_timer.setInterval(2000)
        self.login_timer.timeout.connect(self.poll_login)
        self.login_polls = 0
        for method in (L.METHOD_CLAUDE, L.METHOD_GEMINI, L.METHOD_CHATGPT):
            b = block(method)
            b.addWidget(dim(tr("tr_llm_info")))
            row = QHBoxLayout()
            status = QLabel()
            status.setWordWrap(True)
            status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(status, 1)
            # 📦 npm install -g --prefix ~/.local … (fehlt npm: erst npm per pkexec)
            btn = button("📦  " + tr("tr_llm_install"), lambda _, m=method: self.install_llm(m), "sendbtn")
            btn.setMinimumHeight(40)
            row.addWidget(btn)
            # 🔑 öffnet ein Terminal mit claude / gemini / codex login
            login = button("🔑  " + tr("tr_llm_login_btn"), lambda _, m=method: self.login_llm(m), "sendbtn")
            login.setMinimumHeight(40)
            row.addWidget(login)
            b.addLayout(row)
            self.llm_status[method] = (status, btn)
            self.llm_login_btns[method] = login
            self.update_llm_status(method)
            b.addWidget(QLabel(tr("tr_model")))
            key = L.MODEL_KEYS[method]
            combo = model_combo(method, self.cfg.get(key, ""),
                                lambda value, k=key: value != self.cfg.get(k) and self.set_cfg(k, value))
            self.model_combos[method] = combo
            b.addWidget(combo)
            b.addLayout(self.retry_row(method))

        # 🖼 Lokales Bild-LLM (Ollama) – bekommt das Foto mit
        b = block(L.METHOD_VISION)
        b.addWidget(dim(tr("tr_vision_info")))
        row = QHBoxLayout()
        self.vision_status = QLabel()
        self.vision_status.setWordWrap(True)
        self.vision_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.vision_status, 1)
        row.addWidget(button("🔄  " + tr("tr_vision_check"), self.update_vision_status))
        # 📦 nur solange Ollama fehlt: pacman-Paket passend zur Grafikkarte / offizielles Skript
        self.vision_install_btn = button("📦  " + tr("tr_vision_install"), self.install_ollama, "sendbtn")
        self.vision_install_btn.setMinimumHeight(40)
        row.addWidget(self.vision_install_btn)
        pull = button("📥  " + tr("tr_vision_pull"), self.pull_vision_model, "sendbtn")
        pull.setMinimumHeight(40)
        row.addWidget(pull)
        b.addLayout(row)
        b.addWidget(QLabel(tr("tr_model")))
        key = L.MODEL_KEYS[L.METHOD_VISION]
        combo = model_combo(L.METHOD_VISION, self.cfg.get(key, ""),
                            lambda value, k=key: value != self.cfg.get(k) and self.set_cfg(k, value))
        self.model_combos[L.METHOD_VISION] = combo
        b.addWidget(combo)
        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(12)
        grid2.addWidget(QLabel(tr("tr_vision_keep")), 0, 0)
        keep = QComboBox()
        for value in vision.KEEP_ALIVE:
            keep.addItem(tr("tr_vision_keep_" + value.replace("-", "forever")), value)
        keep.setCurrentIndex(max(0, keep.findData(self.cfg.get("tr_vision_keep_alive") or "2m")))
        keep.currentIndexChanged.connect(lambda _: self.set_cfg("tr_vision_keep_alive", keep.currentData()))
        grid2.addWidget(keep, 0, 1)
        grid2.addWidget(QLabel(tr("tr_vision_url")), 1, 0)
        grid2.addWidget(self.line_edit("tr_vision_url", vision.DEFAULT_URL), 1, 1)
        grid2.setColumnStretch(1, 1)
        b.addLayout(grid2)

        # KI: eigener Befehl
        b = block(L.METHOD_LLM_CUSTOM)
        b.addWidget(dim(tr("tr_llm_custom_info")))
        b.addWidget(self.line_edit("tr_llm_custom_cmd", L.CUSTOM_EXAMPLE))

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
            if m is None:
                return  # Überschrift
            self.show_method_block(m)
            self.test_result.clear()
            translation.set_main(self.cfg, m)  # evtl. Aufgabe → Übersetzen (Modus ✋ Manuell)
            self.set_cfg("tr_method", m)
            self.update_route()

        self.method.currentIndexChanged.connect(method_changed)
        self.show_method_block(self.cfg["tr_method"])
        self.sync_translation()
        return w

    def add_task_rows(self, grid: QGridLayout, row: int):
        """Kontext erklären / Frage beantworten: [KI ▾] [Modell ▾] – je 2 Zeilen (+ Hinweis).
        Das Modell gehört zur KI (dasselbe wie bei ihr eingestellt)."""
        for i, mode in enumerate(L.TASK_KEYS):
            key = L.TASK_KEYS[mode]
            service = QComboBox()
            service.addItem("", "")  # Text: update() („wie Main“ / „aus“)
            for m in L.METHODS:
                service.addItem(tr("tr_m_" + m), m)
            service.setCurrentIndex(max(0, service.findData(self.cfg.get(key) or "")))
            model = model_combo(service.currentData() or L.METHOD_CLAUDE, "", lambda _m: None)
            status = dim("")
            r = row + 2 * i
            grid.addWidget(QLabel(tr("tr_mode_" + mode)), r, 0)
            grid.addWidget(service, r, 1)
            grid.addWidget(model, r, 2)
            grid.addWidget(status, r + 1, 1, 1, 2)

            def model_chosen(combo=model):
                method = combo.property("llm_method")
                self.set_cfg(L.MODEL_KEYS[method], combo.property("llm_model") or "")
                self.sync_translation()  # gleiches Modell auch im Block der KI unten

            model.activated.connect(lambda _i, c=model: model_chosen(c))

            def update(combo=service, model=model, status=status):
                main_ai = L.is_llm(self.cfg["tr_method"])
                combo.setItemText(0, tr("tr_tasks_same") if main_ai else tr("tr_tasks_off"))
                m = combo.currentData()
                model.setVisible(bool(m))
                if m:
                    fill_model_combo(model, m, self.cfg.get(L.MODEL_KEYS[m], ""))
                if m and not translation.is_configured(m, self.cfg):
                    text = "⚠  " + tr("tr_answer_not_ready")
                else:
                    text = translation.privacy_text(m) if m else ""
                status.setText(text)
                status.setVisible(bool(text))

            def changed(_i, key=key, combo=service, update=update):
                self.set_cfg(key, combo.currentData())
                update()

            service.currentIndexChanged.connect(changed)
            self.task_updates.append(update)
            update()

    def route_changed(self, _i=None):
        translation.set_route(self.cfg, self.route_combo.currentData())
        self.set_cfg("tr_route", self.cfg["tr_route"])
        self.update_route()

    def update_route(self):
        """Modus-Dropdown: ohne KI als Main geht nur Manuell (LibreTranslate kann nicht entscheiden)."""
        main_ai = L.is_llm(self.cfg["tr_method"])
        mode = translation.route_mode(self.cfg)
        self.route_combo.blockSignals(True)
        self.route_combo.setCurrentIndex(max(0, self.route_combo.findData(mode)))
        self.route_combo.blockSignals(False)
        self.route_combo.setEnabled(main_ai)
        self.route_hint.setText(tr("tr_route_hint_" + mode) if main_ai else tr("tr_route_hint_noai"))
        for update in getattr(self, "task_updates", []):
            update()

    def add_favorites_card(self, lay: QVBoxLayout):
        """⭐ Häkchen pro Dienst. Nichts angehakt = alles wie bisher."""
        card, box = make_card("⭐  " + tr("tr_favorites"))
        box.addWidget(dim(tr("tr_favorites_hint")))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        favs = self.cfg.get("tr_favorites") or []
        half = (len(translation.METHODS) + 1) // 2  # zwei Spalten
        for i, m in enumerate(translation.METHODS):
            check = QCheckBox(tr("tr_m_" + m))
            check.setChecked(m in favs)
            check.toggled.connect(lambda on, method=m: self.favorite_toggled(method, on))
            grid.addWidget(check, i % half, i // half)
        box.addLayout(grid)
        lay.addWidget(card)

    def favorite_toggled(self, method: str, on: bool):
        old = self.cfg.get("tr_favorites") or []
        # neue Liste (nicht die alte ändern) – Reihenfolge wie in METHODS
        favs = [m for m in translation.METHODS if (m in old and m != method) or (m == method and on)]
        usable = [m for m in favs if translation.is_configured(m, self.cfg)]
        if usable and self.cfg["tr_method"] not in favs:
            # gewählter Dienst ist kein Favorit mehr → ersten eingerichteten Favoriten nehmen
            self.cfg["tr_method"] = usable[0]
            self.sync_translation()
        self.set_cfg("tr_favorites", favs)

    def retry_row(self, method: str) -> QHBoxLayout:
        """[✓] Neu senden, wenn länger als [60] s  – hängt die KI, wird neu gefragt."""
        from PyQt6.QtWidgets import QSpinBox
        on_key, secs_key = L.RETRY_KEYS[method]
        on, secs = L.retry_settings(method, self.cfg)
        row = QHBoxLayout()
        check = QCheckBox(tr("tr_retry"))
        check.setChecked(on)
        spin = QSpinBox()
        spin.setRange(5, 600)
        spin.setSingleStep(5)
        spin.setSuffix(" s")
        spin.setValue(secs)
        spin.setMinimumWidth(110)
        spin.setEnabled(on)

        def toggled(value: bool):
            spin.setEnabled(value)
            self.set_cfg(on_key, value)

        check.toggled.connect(toggled)
        spin.editingFinished.connect(lambda: self.set_cfg(secs_key, spin.value()))
        row.addWidget(check)
        row.addWidget(spin)
        row.addStretch()
        hint = dim(tr("tr_retry_hint", n=L.RETRIES, max=L.TIMEOUT))
        wrap = QVBoxLayout()
        wrap.setSpacing(2)
        wrap.addLayout(row)
        wrap.addWidget(hint)
        return wrap

    # --- KI-Programm installieren (Knopf statt Befehl abtippen) ----------
    def update_llm_status(self, method: str, error: str = ""):
        from core import pkginstall
        status, btn = self.llm_status[method]
        cmd = L.BINARIES[method]
        found = L.installed(method)
        broken = found and L.broken(method)
        login = L.logged_in(method) if found and not broken else False
        if broken:
            # z. B. "claude native binary not installed" → neu installieren
            text = tr("tr_llm_broken", cmd=cmd)
        elif found:
            text = tr("tr_llm_found", cmd=cmd) + "\n"
            if login:
                text += tr("tr_llm_logged_in")
            elif login is None:
                text += tr("tr_llm_login_unknown", cmd=L.LOGIN_COMMANDS[method])
            else:
                text += tr("tr_llm_not_logged_in")
        else:
            text = tr("tr_llm_missing", cmd=cmd, hint=L.manual_install_command(method))
            if L.needs_npm(method) and not shutil.which("npm"):
                text += "\n" + tr("tr_npm_missing", cmd=pkginstall.manual_command("npm"))
        if error:
            text = error + "\n" + text
        status.setText(text)
        status.setObjectName("ok" if found and not broken and login is not False else "bad")
        status.style().polish(status)
        login_btn = self.llm_login_btns.get(method)
        if login_btn is not None:
            login_btn.setVisible(found and not broken and not login)
            login_btn.setObjectName("linkbtn" if login is None else "sendbtn")
            login_btn.style().polish(login_btn)
        can = (not L.needs_npm(method) or shutil.which("npm") is not None
               or pkginstall.install_command("npm") is not None)
        btn.setVisible((not found or broken) and can)
        btn.setEnabled(self.llm_process is None)
        btn.setText("📦  " + tr("tr_llm_reinstall" if broken else "tr_llm_install"))

    def login_llm(self, method: str):
        """Terminal mit claude / gemini / codex login öffnen – dort im Browser anmelden."""
        from core import terminal
        status, _btn = self.llm_status[method]
        argv = L.login_argv(method)
        if argv is None or not terminal.run(argv, tr("tr_press_enter")):
            status.setText(tr("tr_no_terminal", cmd=L.LOGIN_COMMANDS[method]))
            return
        status.setText(tr("tr_llm_login_running"))
        self.login_polls = 0
        self.login_timer.start()

    def poll_login(self):
        self.login_polls += 1
        done = all(L.logged_in(m) is not False for m in self.llm_status if L.installed(m))
        if done or self.login_polls > 150:
            self.login_timer.stop()
            for m in self.llm_status:
                self.update_llm_status(m)
            self.translation_changed.emit()

    def install_llm(self, method: str):
        """Schritt 1 (nur wenn npm fehlt): npm per pkexec. Schritt 2: npm install … nach ~/.local."""
        from PyQt6.QtCore import QProcess
        from core import pkginstall
        if self.llm_process is not None:
            return
        steps = []
        if L.needs_npm(method) and not shutil.which("npm"):
            steps.append(lambda: pkginstall.install_command("npm"))
        steps += L.install_steps(method)
        status, btn = self.llm_status[method]
        for _s, b in self.llm_status.values():
            b.setEnabled(False)
        btn.setText("⏳  " + tr("clip_installing"))

        def next_step():
            if not steps:
                self.llm_process = None
                self.after_llm_install(method, "")
                return
            argv = steps.pop(0)()
            if argv is None:
                self.llm_process = None
                self.after_llm_install(method, tr("tr_llm_install_failed"))
                return
            if argv[0] == "pkexec":
                status.setText(tr("clip_password"))
            else:
                shown = argv[2] if argv[:2] == ["bash", "-c"] else " ".join(argv[1:])
                status.setText(tr("tr_llm_installing", cmd=shown))
            proc = QProcess(self)
            self.llm_process = proc

            def finished(code, _status):
                if code != 0:
                    out = bytes(proc.readAllStandardError()).decode(errors="replace").strip()
                    last = out.splitlines()[-1] if out else ""
                    self.llm_process = None
                    self.after_llm_install(method, tr("tr_llm_install_failed")
                                           + (f": {last}" if last else ""))
                    return
                next_step()

            proc.finished.connect(finished)
            proc.start(argv[0], argv[1:])

        next_step()

    def after_llm_install(self, method: str, error: str):
        for m in self.llm_status:
            self.update_llm_status(m, error if m == method else "")
        # neu installiert → taucht auf der Main-Seite im Dropdown auf
        self.translation_changed.emit()

    def settings_method_changed(self, _i=None):
        """„Einstellungen für“ umgestellt → nur den Block zeigen, Main bleibt wie es ist."""
        m = self.settings_method.currentData()
        if m is None:
            return  # Überschrift
        self.test_result.clear()
        self.show_method_block(m, sync_picker=False)

    def show_method_block(self, method: str, sync_picker: bool = True):
        """Block eines Dienstes zeigen. sync_picker: „Einstellungen für“ mitziehen
        (wenn Main sich ändert, zeigt die Karte den neuen Main-Dienst)."""
        self.shown_method = method
        picker = getattr(self, "settings_method", None)
        if sync_picker and picker is not None:
            picker.blockSignals(True)
            select_data(picker, method)
            picker.blockSignals(False)
        for key, widget in self.method_blocks.items():
            widget.setVisible(key == method)
        # ☁/🔒 steht in der Main-Karte → gilt für den Main-Dienst
        self.privacy_note.setText(translation.privacy_text(self.cfg["tr_method"]))
        if method == T.METHOD_LIBRE:
            self.check_libre()
        if method == L.METHOD_VISION:
            self.update_vision_status()

    # --- 🖼 Bild-LLM (Ollama): läuft es? Modelle da? ----------------------
    def update_vision_status(self):
        url = vision.url_of(self.cfg)
        self.vision_install_btn.setVisible(not L.installed(L.METHOD_VISION))
        if not vision.running(url):
            text, ok = tr("tr_vision_off", url=url), False
        else:
            vision._models_cache.pop(url, None)  # frisch nachschauen
            models = vision.vision_models(url)
            text = tr("tr_vision_ok", n=len(models), models=", ".join(models[:4])) if models \
                else tr("tr_vision_no_model")
            ok = bool(models)
            combo = self.model_combos.get(L.METHOD_VISION)
            if combo is not None:
                fill_model_combo(combo, L.METHOD_VISION, self.cfg.get(L.MODEL_KEYS[L.METHOD_VISION], ""))
        self.vision_status.setObjectName("ok" if ok else "bad")
        self.vision_status.style().polish(self.vision_status)
        self.vision_status.setText(text)

    def install_ollama(self):
        """📦 Terminal: Ollama passend zu Distro + Grafikkarte installieren und starten."""
        from core import terminal
        script = vision.install_script()
        ok = terminal.run(["bash", "-c", script])
        self.vision_status.setObjectName("dim" if ok else "bad")
        self.vision_status.style().polish(self.vision_status)
        self.vision_status.setText(tr("tr_vision_installing") if ok else tr("tr_vision_install_manual", cmd=script))

    def pull_vision_model(self):
        """📥 Terminal mit „ollama pull <Modell>“ (zeigt den Download-Fortschritt)."""
        from core import terminal
        model = L.model_of(L.METHOD_VISION, self.cfg)
        exe = L.find_binary("ollama")
        if exe is None or not terminal.run([exe, "pull", model]):
            self.vision_status.setObjectName("bad")
            self.vision_status.style().polish(self.vision_status)
            self.vision_status.setText(tr("tr_vision_pull_manual", model=model))

    def sync_translation(self):
        """Dropdowns an ui.json anpassen (z. B. nach Änderung auf der Main-Seite).
        blockSignals: sonst würde das Setzen selbst wieder "geändert" melden."""
        for combo, key in ((self.method, "tr_method"), (self.tr_source_combo, "tr_source"),
                           (self.tr_target_combo, "tr_target")):
            combo.blockSignals(True)
            select_data(combo, self.cfg[key])
            combo.blockSignals(False)
        for method, combo in self.model_combos.items():
            fill_model_combo(combo, method, self.cfg.get(L.MODEL_KEYS[method], ""))
        # Main hat sich geändert → Einstellungen des neuen Main zeigen;
        # sonst bleibt der Dienst stehen, den man gerade unter „Einstellungen für“ einrichtet
        if self.cfg["tr_method"] != getattr(self, "_last_main", None) or not getattr(self, "shown_method", None):
            self.show_method_block(self.cfg["tr_method"])
        else:
            self.show_method_block(self.shown_method, sync_picker=False)
        self._last_main = self.cfg["tr_method"]
        if hasattr(self, "route_combo"):
            self.update_route()

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
        if url and not self.cfg.get("tr_libre_seen"):
            # merken → LibreTranslate taucht ab jetzt im Dropdown auf der Main-Seite auf
            self.save_cfg("tr_libre_seen", True)
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
        method = getattr(self, "shown_method", None) or cfg["tr_method"]

        def work():  # Hintergrund – KEINE Widgets anfassen!
            # NUR den gewählten Dienst testen – ohne Lingva/Google als Ersatz,
            # sonst sieht ein kaputter Dienst beim Einrichten wie "geht" aus
            try:
                out, error = translation.translate_only(method, tr("tr_test_text"), cfg)
            except Exception as e:  # noqa: BLE001
                out, error = None, str(e)
            self._test_done.emit("✔ " + out if out else "✘ " + (error or tr("tr_no_answer")))

        threading.Thread(target=work, daemon=True).start()

    def on_test_done(self, text: str):
        self.test_btn.setEnabled(True)
        self.test_result.setObjectName("ok" if text.startswith("✔") else "bad")
        self.test_result.style().polish(self.test_result)
        self.test_result.setText(text)
