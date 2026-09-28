"""
ui/pages/main_translation.py – Main-Seite: 🌐 Übersetzung neben dem Foto
(Dienst/Sprache/KI-Aufgabe, erkannter Text, ⧉ eigenes Fenster, Hintergrund-Übersetzung).
"""

import html
import threading
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                             QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout)

from core import llm_translator as llm
from core import clipboard, config, ocr, qr, translation
from core.i18n import tr
from ui.panel_window import PanelWindow


class TranslationMixin:
    """Teil von MainPage (wird dort mit eingemischt)."""

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
            # Maus drüber: bleibt der Text auf dem PC oder geht er ins Internet?
            self.method_combo.setItemData(self.method_combo.count() - 1, translation.privacy_text(m),
                                          Qt.ItemDataRole.ToolTipRole)
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
        if step == "partial":
            # KI schreibt noch – bisherigen Text schon zeigen (Endergebnis ersetzt ihn)
            self.tr_text.setPlainText(arg)
            self.tr_text.verticalScrollBar().setValue(self.tr_text.verticalScrollBar().maximum())
            self.tr_status.setText("⏳  " + tr("tr_step_partial"))
            return
        if step == "service":
            text = tr("tr_step_service", name=tr("tr_m_" + arg))
        elif step == "retry":
            method, _, attempt = arg.rpartition(":")
            text = tr("tr_step_retry", name=tr("tr_m_" + method), n=attempt)
            self.tr_text.clear()  # halbe Antwort vom hängenden Versuch weg
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
