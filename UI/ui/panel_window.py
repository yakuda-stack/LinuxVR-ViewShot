"""
ui/panel_window.py – eigenes Fenster für einen Teil einer Seite
(Übersetzung, Verlauf). Schließen = zurück ins Hauptfenster.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class PanelWindow(QWidget):
    """Eigenes Fenster für einen Teil der Main-Seite (Übersetzung, Verlauf).
    Schließen (✕) = on_close() → zurück ins Hauptfenster."""

    def __init__(self, page: QWidget, title: str, on_close, size=(560, 640)):
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
