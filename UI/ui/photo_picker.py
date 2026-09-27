"""
ui/photo_picker.py – Kleine Galerie als Fenster: ein Foto anklicken = auswählen.

Benutzt auf der Main-Seite (🖼-Knopf neben "Letztes Foto"), um ein anderes
Foto für die Übersetzung zu wählen.

    photo = pick_photo(parent)   # Path oder None (abgebrochen)
"""

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from core import paths
from core.i18n import tr

THUMB = 160  # Kachelgröße im Fenster (Pixel)


class PhotoPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("pick_photo_title"))
        self.resize(900, 620)
        self.chosen = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        hint = QLabel(tr("pick_photo_hint"))
        hint.setObjectName("dim")
        layout.addWidget(hint)

        # gleiche Kacheln wie in der Galerie, nur kleiner
        from ui.pages.gallery_page import load_thumbnail
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(THUMB, THUMB))
        self.grid.setGridSize(QSize(THUMB + 24, THUMB + 40))
        self.grid.setUniformItemSizes(True)
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setMovement(QListWidget.Movement.Static)
        self.grid.setCursor(Qt.CursorShape.PointingHandCursor)
        for photo in paths.list_photos():
            item = QListWidgetItem(QIcon(load_thumbnail(photo, THUMB)),
                                   photo.stem.removeprefix("ViewShot_"))
            item.setData(Qt.ItemDataRole.UserRole, str(photo))
            item.setToolTip(str(photo))
            self.grid.addItem(item)
        # ein Klick reicht (leichter in VR als Doppelklick)
        self.grid.itemClicked.connect(self.choose)
        layout.addWidget(self.grid, 1)

        if self.grid.count() == 0:
            empty = QLabel(tr("no_photo"))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton(tr("cancel"))
        cancel.setObjectName("linkbtn")
        cancel.setMinimumHeight(40)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

    def choose(self, item: QListWidgetItem):
        self.chosen = Path(item.data(Qt.ItemDataRole.UserRole))
        self.accept()


def pick_photo(parent=None):
    """Zeigt das Fenster. Gibt den Pfad des gewählten Fotos zurück, sonst None."""
    dialog = PhotoPicker(parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.chosen
    return None
