"""
core/layer_install.py – den Layer aus der AppImage nach ~/.local kopieren.

Für AppImage UND AUR-Paket (paths.copies_layer()). Macht dasselbe wie
scripts/install-layer.sh, nur ohne cargo: die .so liegt schon fertig bei.
Immer nach ~/.local – nur das sehen auch Proton-Spiele im Steam-Container.

    ~/.local/lib/linuxvr-viewshot/liblinuxvr_viewshot_layer.so
    ~/.local/lib/linuxvr-viewshot/VERSION
    ~/.local/share/openxr/1/api_layers/implicit.d/linuxvr_viewshot.json

Nach einem AppImage-Update ist VERSION älter als die App → needs_update().
"""

import os
import shutil

from core import paths
from core.version import VERSION


def _replace(target, write) -> None:
    """Neue Datei daneben schreiben, dann in einem Schritt austauschen.
    Ein laufendes Spiel behält so die alte .so im Speicher und stürzt nicht ab
    (in eine geladene .so hineinzuschreiben würde es sofort abschießen)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".new")
    write(tmp)
    os.replace(tmp, target)


def install_bundled() -> None:
    """Layer + Manifest aus der AppImage installieren (oder aktualisieren)."""
    def copy_lib(tmp):
        shutil.copyfile(paths.bundled_layer(), tmp)
        tmp.chmod(0o755)

    _replace(paths.USER_LIB, copy_lib)
    manifest = paths.MANIFEST_TEMPLATE.read_text(encoding="utf-8").replace(
        "@LIBRARY_PATH@", str(paths.USER_LIB))
    _replace(paths.MANIFEST, lambda tmp: tmp.write_text(manifest, encoding="utf-8"))
    paths.LAYER_VERSION_FILE.write_text(VERSION + "\n", encoding="utf-8")
    # Foto-Ordner gleich mit anlegen (wie install-layer.sh)
    paths.photo_dir().mkdir(parents=True, exist_ok=True)


def installed_version() -> str:
    try:
        return paths.LAYER_VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def needs_update() -> bool:
    """AppImage/Paket + Layer in ~/.local installiert, aber von einer anderen
    Version (z. B. nach einem AppImage- oder pacman-Update)?"""
    return (paths.copies_layer() and paths.MANIFEST.is_file()
            and installed_version() != VERSION)
