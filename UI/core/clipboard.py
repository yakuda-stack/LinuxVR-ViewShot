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
    """Bild als Bild UND als Datei (für Dolphin). GIF nur als Datei: Als Bild käme nur das
    erste Einzelbild an, und Discord würde dieses statt der Datei nehmen."""
    mime = QMimeData()
    if path.suffix.lower() not in (".gif", ".mp4"):  # 🎬 Video ebenfalls nur als Datei
        mime.setImageData(QImage(str(path)))
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    QApplication.clipboard().setMimeData(mime)
