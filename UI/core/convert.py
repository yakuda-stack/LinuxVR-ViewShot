"""
core/convert.py – 🔄 Converter: Video → GIF (Seite „Converter“).

ffmpeg macht die Arbeit (zwei Durchgänge in einem Aufruf: erst eine passende
256-Farben-Palette, dann das GIF damit – sieht viel besser aus als die Standard-Palette).
Danach auf Wunsch 🗜 unter die Discord-Grenze (core/gifshrink.py).

Das GIF landet in gif_vid/convert/ → erscheint gleich in der Galerie.
"""

import os
import shutil
import subprocess
from pathlib import Path

from core import gifshrink, paths

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v")
FPS_CHOICES = (8, 10, 12, 15, 20)
SIDE_CHOICES = (320, 480, 640, 800)
TARGET_MB_CHOICES = (10, 8, 5)  # Discord ohne Nitro: 10 MB
TIMEOUT_S = 600

DEFAULTS = {
    "conv_fps": 12,          # Bilder pro Sekunde im GIF
    "conv_side": 480,        # längste Seite in Pixeln
    "conv_max_s": 15,        # höchstens so viele Sekunden vom Anfang
    "conv_shrink": True,     # danach 🗜 unter conv_target_mb bringen
    "conv_target_mb": 10,    # Zielgröße (MB) – auch fürs 🗜 Komprimieren
    "conv_backup": True,     # 🗜 Komprimieren: Original nach backup/
}


def ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def target_bytes(mb: int) -> int:
    """Etwas Luft unter der Grenze lassen (10 MB → 9,5 MB)."""
    return int(mb * 1_000_000 * 0.95)


def gif_filter(fps: int, side: int) -> str:
    """fps → längste Seite höchstens side (nie vergrößern) → eigene Palette."""
    scale = (f"scale=w='if(gte(iw,ih),min({side},iw),-1)':h='if(gte(iw,ih),-1,min({side},ih))'"
             ":flags=lanczos")
    return (f"fps={fps},{scale},split[a][b];[a]palettegen=stats_mode=diff[p];"
            "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")


def command(tool: str, src: Path, out: Path, fps: int, side: int, max_s: float) -> list[str]:
    cmd = [tool, "-hide_banner", "-loglevel", "error", "-y"]
    if max_s > 0:
        cmd += ["-t", str(max_s)]  # vor -i: nur so viel einlesen
    return cmd + ["-i", str(src), "-vf", gif_filter(fps, side), "-loop", "0", "-f", "gif", str(out)]


def free_name(folder: Path, stem: str, suffix: str) -> Path:
    """name.gif, sonst name_1.gif, name_2.gif …"""
    target = folder / f"{stem}{suffix}"
    n = 1
    while target.exists():
        target = folder / f"{stem}_{n}{suffix}"
        n += 1
    return target


def video_to_gif(src: Path, fps: int, side: int, max_s: float,
                 shrink_mb: int | None = None, folder: Path | None = None) -> dict:
    """Video → GIF. BLOCKIERT (ffmpeg + evtl. 🗜) → nur im Thread!
    → {"path", "size", "shrunk" (bool)}"""
    tool = ffmpeg()
    if tool is None:
        raise RuntimeError("ffmpeg")
    folder = folder or paths.convert_dir()  # 🗂 gif_vid/convert/
    folder.mkdir(parents=True, exist_ok=True)
    out = free_name(folder, src.stem, ".gif")
    tmp = out.with_name(f".{out.name}.part")  # versteckt → die Galerie zeigt es nicht halb fertig
    try:
        run = subprocess.run(command(tool, src, tmp, fps, side, max_s),
                             capture_output=True, text=True, timeout=TIMEOUT_S)
        if run.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
            lines = (run.stderr or "").strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"ffmpeg: Code {run.returncode}")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    shrunk = False
    if shrink_mb and out.stat().st_size > target_bytes(shrink_mb):
        gifshrink.compress(out, keep_backup=False, target=target_bytes(shrink_mb))
        shrunk = True
    paths.forget_scan()
    return {"path": str(out), "size": out.stat().st_size, "shrunk": shrunk}
