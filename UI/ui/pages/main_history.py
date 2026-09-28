"""
ui/pages/main_history.py – Main-Seite: 🕘 Verlauf der Übersetzungen
(Karte, ⧉ eigenes Fenster, Eintrag anklicken → wieder anzeigen).
"""

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core import history
from core.i18n import tr
from ui.panel_window import PanelWindow
from ui.widgets import make_card


class HistoryMixin:
    """Teil von MainPage (wird dort mit eingemischt)."""

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
