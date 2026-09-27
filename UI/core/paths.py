"""
core/paths.py – Wo liegen Fotos, Log und Layer?

Die Pfade müssen genau zu denen im Rust-Layer passen
(layer/src/save.rs und log.rs), sonst findet die UI nichts.
"""

import os
from pathlib import Path

from PyQt6.QtCore import QStandardPaths

HOME = Path.home()

# Projektordner (…/LinuxVR-ViewShot) und das Install-Skript des Layers
PROJECT_DIR = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = PROJECT_DIR / "scripts" / "install-layer.sh"

# App-Icon (Fenster, Taskleiste, Seitenleiste) – install.sh kopiert es auch
# nach ~/.local/share/icons/hicolor/…/apps/linuxvr-viewshot.png
APP_ICON = PROJECT_DIR / "UI" / "assets" / "linuxvr-viewshot.png"
# Name der .desktop-Datei = App-ID unter Wayland → Taskleiste findet Icon + Namen
DESKTOP_ID = "linuxvr-viewshot"

# Config der UI (Sprache usw.)
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "linuxvr-viewshot"

# Log des Layers
LOG_FILE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "linuxvr-viewshot" / "layer.log"

# Manifest, das install-layer.sh anlegt – existiert es, ist der Layer installiert
MANIFEST = (Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
            / "openxr/1/api_layers/implicit.d/linuxvr_viewshot.json")


def photo_dir() -> Path:
    """Gleiche Regel wie im Layer: $VIEWSHOT_OUTPUT_DIR oder ~/Bilder/LinuxVR-ViewShot"""
    custom = os.environ.get("VIEWSHOT_OUTPUT_DIR")
    if custom:
        return Path(custom)
    # QStandardPaths kennt den echten Bilder-Ordner (Bilder, Pictures, …)
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or HOME / "Pictures") / "LinuxVR-ViewShot"


def list_photos() -> list[Path]:
    """Alle Fotos, neueste zuerst."""
    folder = photo_dir()
    if not folder.is_dir():
        return []
    photos = [p for p in folder.iterdir() if p.suffix.lower() == ".png"]
    photos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return photos


def layer_installed() -> bool:
    return MANIFEST.is_file()
