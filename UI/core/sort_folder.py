"""
core/sort_folder.py – 🗂 Foto-Ordner aufräumen (einmalig beim ersten Start von v1.0.9,
danach per Knopf in Optionen → Allgemein).

Was direkt im Foto-Ordner liegt, wandert in Unterordner:
    Fotos (png/jpg/jpeg/webp)        → picture/
    GIFs + Videos (gif/mp4)          → gif_vid/   (mit dem versteckten Video-Vorschaubild)
Unterordner (live/, panel/, desktop/ …) und halb geschriebene Dateien bleiben, wo sie sind.
Name und Änderungszeit bleiben gleich → Tags, Übersetzungen und Galerie-Reihenfolge passen weiter.
Gibt es den Namen im Ziel schon, bleibt die Datei liegen (nichts wird überschrieben).
"""

import os
from pathlib import Path

from core import paths

PICTURE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MOTION_EXTS = {".gif", ".mp4"}


def target_for(path: Path) -> Path | None:
    """Wohin gehört diese Datei? None = bleibt liegen."""
    name = path.name
    if name.endswith(".part"):
        return None  # wird gerade geschrieben
    if name.startswith("."):
        # 🎬 verstecktes Vorschaubild „.X.mp4.png“ gehört zum Video
        if name.lower().endswith(".mp4.png"):
            return paths.gif_vid_dir() / name
        return None
    ext = path.suffix.lower()
    if ext in PICTURE_EXTS:
        return paths.picture_dir() / name
    if ext in MOTION_EXTS:
        return paths.gif_vid_dir() / name
    return None


def pending() -> list[tuple[Path, Path]]:
    """[(Datei, Ziel)] – was ein Aufräumen verschieben würde."""
    root = paths.photo_dir()
    if not root.is_dir():
        return []
    out = []
    for entry in root.iterdir():
        if entry.is_file():
            target = target_for(entry)
            if target is not None:
                out.append((entry, target))
    return out


def sort_now() -> dict:
    """Verschieben. → {"pictures", "gif_vid", "skipped"} (Anzahl)"""
    paths.make_sorted_dirs()
    counts = {"pictures": 0, "gif_vid": 0, "skipped": 0}
    for src, dst in pending():
        if dst.exists():
            counts["skipped"] += 1
            continue
        try:
            os.rename(src, dst)  # gleiches Dateisystem → schnell, Änderungszeit bleibt
        except OSError:
            counts["skipped"] += 1
            continue
        if src.name.startswith("."):
            continue  # Vorschaubild zählt nicht extra
        counts["gif_vid" if dst.parent == paths.gif_vid_dir() else "pictures"] += 1
    paths.forget_scan()
    return counts
