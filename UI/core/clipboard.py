"""
core/clipboard.py – Zwischenablage, die auch aus WayVR heraus auf dem Desktop ankommt.

Problem: Läuft die App als Fenster IN WayVR, hat sie WayVRs eigenen Wayland-Server.
"Kopieren" landet dann nur in WayVRs Zwischenablage – auf dem Desktop geht Strg+V ins Leere.

Lösung: Zusätzlich zur normalen Qt-Zwischenablage wird der Inhalt mit `wl-copy`
(Paket wl-clipboard) an JEDEN anderen Wayland-Server im Laufzeit-Ordner gegeben
(= der Desktop). Kein wl-copy / kein Wayland? Dann per xclip/xsel an X11 (DISPLAY :0).

Läuft im Hintergrund-Thread – die UI friert nie ein, Fehler werden ignoriert.
"""

import os
import re
import shutil
import stat
import subprocess
import threading
from pathlib import Path

from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

_SOCKET = re.compile(r"^wayland-\d+$")

# In den Optionen abschaltbar (config "clipboard_mirror")
enabled = True


def runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def other_displays() -> list[str]:
    """Alle Wayland-Sockets außer dem, auf dem die App gerade läuft."""
    current = os.environ.get("WAYLAND_DISPLAY", "")
    current = Path(current).name  # kann auch ein voller Pfad sein
    found = []
    try:
        for entry in sorted(runtime_dir().iterdir()):
            if not _SOCKET.match(entry.name) or entry.name == current:
                continue
            try:
                if stat.S_ISSOCK(entry.stat().st_mode):
                    found.append(entry.name)
            except OSError:
                pass
    except OSError:
        pass
    return found


def _run(argv: list[str], data: bytes, env: dict):
    try:
        # wl-copy/xclip bleiben im Hintergrund und liefern den Inhalt aus –
        # darum stdout/stderr NICHT auffangen, sonst wartet run() auf sie
        subprocess.run(argv, input=data, env=env, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass


def _mirror(data: bytes, mime: str):
    wl_copy = shutil.which("wl-copy")
    displays = other_displays() if wl_copy else []
    for display in displays:
        env = dict(os.environ, WAYLAND_DISPLAY=display)
        _run([wl_copy, "--type", mime], data, env)
    if displays:
        return
    # Fallback: X11 (z. B. Desktop ohne Wayland)
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    if shutil.which("xclip"):
        _run(["xclip", "-selection", "clipboard", "-t", mime], data, env)
    elif shutil.which("xsel") and mime.startswith("text/"):
        _run(["xsel", "--clipboard", "--input"], data, env)


def mirror(data: bytes, mime: str):
    if enabled:
        threading.Thread(target=_mirror, args=(data, mime), daemon=True).start()


def set_text(text: str):
    QApplication.clipboard().setText(text)
    mirror(text.encode("utf-8"), "text/plain;charset=utf-8")


def set_image(path: Path):
    """Bild als Bild UND als Datei (für Dolphin) – auf dem Desktop als PNG."""
    mime = QMimeData()
    mime.setImageData(QImage(str(path)))
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    QApplication.clipboard().setMimeData(mime)
    try:
        data = Path(path).read_bytes()
    except OSError:
        return
    kind = "image/jpeg" if Path(path).suffix.lower() in (".jpg", ".jpeg") else "image/png"
    if Path(path).suffix.lower() in (".png", ".jpg", ".jpeg"):
        mirror(data, kind)
    else:  # webp/bmp → vorher in PNG umwandeln
        from PyQt6.QtCore import QBuffer, QIODevice
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        QImage(str(path)).save(buf, "PNG")
        mirror(bytes(buf.data()), "image/png")
