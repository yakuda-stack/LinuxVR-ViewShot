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
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "linuxvr-viewshot"

# Log des Layers
LOG_FILE = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state") / "linuxvr-viewshot" / "layer.log"

# Manifest, das install-layer.sh anlegt – existiert es, ist der Layer installiert
MANIFEST = (Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
            / "openxr/1/api_layers/implicit.d/linuxvr_viewshot.json")


def photo_dir() -> Path:
    """Gleiche Regel wie im Layer: $VIEWSHOT_OUTPUT_DIR oder ~/Bilder/LinuxVR-ViewShot"""
    custom = os.environ.get("VIEWSHOT_OUTPUT_DIR")
    if custom:
        return Path(custom)
    # QStandardPaths kennt den echten Bilder-Ordner (Bilder, Pictures, …)
    pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return Path(pictures or HOME / "Pictures") / "LinuxVR-ViewShot"


def photo_ready(path: Path) -> bool:
    """Ist das PNG vollständig geschrieben? Ein fertiges PNG endet immer mit
    dem IEND-Block. Schnell (liest nur die letzten 12 Bytes) und ohne Qt –
    darf also auch aus Hintergrund-Threads aufgerufen werden.
    Andere Formate (per 📁 gewählte JPGs …) gelten als fertig."""
    if Path(path).suffix.lower() != ".png":
        return Path(path).is_file()
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            f.seek(-12, os.SEEK_END)
            return f.read(12)[4:8] == b"IEND"
    except OSError:
        return False


def list_photos() -> list[Path]:
    """Alle Fotos, neueste zuerst."""
    folder = photo_dir()
    if not folder.is_dir():
        return []
    photos = [p for p in folder.iterdir() if p.suffix.lower() == ".png"]
    photos.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return photos


# WICHTIG: Der Layer MUSS im Home-Ordner registriert sein (~/.local).
# Steam-Spiele über Proton (z. B. VRChat) laufen im Steam-Container
# (pressure-vessel) – dort ist /usr NICHT das /usr des Systems, ein Layer in
# /usr/share/openxr bzw. /usr/lib wäre für sie unsichtbar. Der Home-Ordner
# ist im Container sichtbar. Deshalb landet der Layer bei ALLEN Wegen
# (Skript, AppImage, AUR-Paket) in ~/.local.
LAYER_NAME = "liblinuxvr_viewshot_layer.so"
USER_LIB = HOME / ".local/lib/linuxvr-viewshot" / LAYER_NAME
# Welche Version dort liegt (schreiben install-layer.sh und layer_install.py)
LAYER_VERSION_FILE = USER_LIB.parent / "VERSION"

# Alte Paket-Versionen (bis 0.4.1) haben den Layer systemweit registriert –
# das sehen Proton-Spiele nicht. Wird nur noch erkannt, um davor zu warnen.
SYSTEM_MANIFEST = Path("/usr/share/openxr/1/api_layers/implicit.d/linuxvr_viewshot.json")

# Fertig gebauter Layer, der nur noch nach ~/.local kopiert wird
# (layer_install.py). Manifest-Vorlage jeweils in PROJECT_DIR/manifest/.
APPIMAGE_LAYER = PROJECT_DIR / "lib" / LAYER_NAME             # in der AppImage
PACKAGE_LAYER = Path("/usr/lib/linuxvr-viewshot") / LAYER_NAME  # AUR-Paket
MANIFEST_TEMPLATE = PROJECT_DIR / "manifest" / "linuxvr_viewshot.json.in"


def mode() -> str:
    """Wie ist die App installiert?
      "appimage" – Layer liegt fertig in der AppImage
      "source"   – Projektordner / install.sh: Layer wird mit cargo gebaut
      "package"  – AUR-Paket: Layer liegt fertig in /usr/lib/linuxvr-viewshot"""
    if APPIMAGE_LAYER.is_file():
        return "appimage"
    if INSTALL_SCRIPT.is_file():
        return "source"
    return "package"


def bundled_layer() -> Path | None:
    """Der mitgelieferte, fertig gebaute Layer (AppImage / Paket), sonst None."""
    layer = {"appimage": APPIMAGE_LAYER, "package": PACKAGE_LAYER}.get(mode())
    return layer if layer is not None and layer.is_file() else None


def copies_layer() -> bool:
    """Wird "Installieren" den Layer nur kopieren (statt mit cargo zu bauen)?"""
    return bundled_layer() is not None and MANIFEST_TEMPLATE.is_file()


def packaged() -> bool:
    """Läuft die App aus einem Paket (z. B. AUR)?"""
    return mode() == "package"


def app_command() -> Path:
    """Womit startet man diese App von außen (z. B. der WayVR-Uhrknopf)?
    In der AppImage ist das die .AppImage-Datei selbst – der Ordner darin
    verschwindet, sobald die App zu ist."""
    appimage = os.environ.get("APPIMAGE")
    if mode() == "appimage" and appimage:
        return Path(appimage)
    return PROJECT_DIR / "UI" / "start.sh"


def layer_installed() -> bool:
    """Nur die Registrierung in ~/.local zählt – die sehen alle Spiele."""
    return MANIFEST.is_file()


def legacy_system_layer() -> bool:
    """Alte Paket-Version hat den Layer systemweit registriert (siehe oben)."""
    return SYSTEM_MANIFEST.is_file()


def uninstall_user_layer() -> None:
    """Entfernt den per Skript installierten Layer (~/.local). Das Paket,
    die App, Fotos und Einstellungen bleiben."""
    for f in (MANIFEST, USER_LIB, LAYER_VERSION_FILE):
        f.unlink(missing_ok=True)
    try:
        USER_LIB.parent.rmdir()
    except OSError:
        pass
