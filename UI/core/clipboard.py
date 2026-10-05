"""
core/clipboard.py – Text und Bilder in die Zwischenablage (Qt).
"""

from pathlib import Path

from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication


def set_text(text: str):
    QApplication.clipboard().setText(text)


def set_image(path: Path):
    """Bild als Bild UND als Datei (für Dolphin)."""
    mime = QMimeData()
    mime.setImageData(QImage(str(path)))
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    QApplication.clipboard().setMimeData(mime)
