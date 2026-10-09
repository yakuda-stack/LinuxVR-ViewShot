"""
core/gifshrink.py – 🗜 GIF für Discord verkleinern (unter 10 MB).

Die eigentliche Arbeit macht der Rust-Dienst:  viewshot-daemon gif-shrink EIN AUS MAX
(weniger Bilder/s, kleiner skalieren – bis es passt). So braucht die App kein Pillow.

Mit Backup landet das Original vorher in  <Foto-Ordner>/backup/  – der Ordner wird
in der Galerie nicht angezeigt (paths.HELPER_DIRS). Name und Änderungszeit des GIFs
bleiben gleich, damit es in der Galerie an derselben Stelle steht.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from core import daemon, paths

LIMIT = 10_000_000   # Discord ohne Nitro: 10 MB
TARGET = 9_500_000   # etwas Luft lassen
TIMEOUT_S = 600


def binary() -> Path | None:
    """viewshot-daemon: frisch gebaut / AppImage / Paket, sonst der installierte."""
    src = daemon.source_binary()
    if src is not None:
        return src
    return daemon.BINARY if daemon.BINARY.is_file() else None


def small_enough(photo: Path) -> bool:
    return photo.stat().st_size <= LIMIT


def backup_dir() -> Path:
    return paths.photo_dir() / "backup"


def make_backup(photo: Path) -> Path:
    """Original nach backup/ kopieren (gibt es den Namen schon: _1, _2 …)."""
    folder = backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / photo.name
    n = 1
    while target.exists():
        target = folder / f"{photo.stem}_{n}{photo.suffix}"
        n += 1
    shutil.copy2(photo, target)
    return target


def compress(photo: Path, keep_backup: bool) -> dict:
    """GIF unter TARGET bringen. BLOCKIERT (bis zu ein paar Minuten) → nur im Thread!
    → {"old", "new" (Bytes), "w", "h", "frames", "fps", "backup" (Pfad oder "")}"""
    tool = binary()
    if tool is None:
        raise RuntimeError("viewshot-daemon")
    old = photo.stat()
    # Hilfsdatei ohne .gif-Endung → die Galerie zeigt sie nicht
    tmp = photo.with_name(f".{photo.name}.part")
    try:
        run = subprocess.run([str(tool), "gif-shrink", str(photo), str(tmp), str(TARGET)],
                             capture_output=True, text=True, timeout=TIMEOUT_S)
        if run.returncode != 0 or not tmp.is_file():
            lines = (run.stderr or "").strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"Code {run.returncode}")
        info = json.loads(run.stdout.strip().splitlines()[-1])
        backup = make_backup(photo) if keep_backup else None
        os.replace(tmp, photo)  # in einem Schritt – nie halb geschrieben
        os.utime(photo, (old.st_atime, old.st_mtime))  # bleibt in der Galerie an seiner Stelle
    finally:
        tmp.unlink(missing_ok=True)
    paths.forget_scan()
    return {"old": old.st_size, "new": photo.stat().st_size, "w": info.get("w", 0), "h": info.get("h", 0),
            "frames": info.get("frames", 0), "fps": info.get("fps", 0), "backup": str(backup or "")}
