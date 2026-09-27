"""
core/wayvr_theme.py – WayVR-Design von Cubee installieren + ViewShot-Knopf auf der Uhr.

Quelle: https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr
(GPL-3.0, wie dieses Projekt). Wird beim Klick frisch von GitHub geladen.

Was passiert (alles in ~/.config/wayvr):
  theme/      Cubees Uhr-Layout + Symbole        → überschrieben (vorher Backup)
  palettes/   Farbpalette "cubee.json"
  sound/      Cubees Sounds
  conf.d/     custom_panels.yaml, timezones.yaml – nur wenn noch nicht vorhanden
              + Farbpalette auf "cubee.json" stellen
NICHT übernommen: Cubees persönliche Einstellungen (zz-saved-config.json5,
z. B. Skybox-Pfad auf seinem PC) und openxr_actions.json5 (würde deine
Controller-Belegung ändern).

Auf der Uhr wird der Knopf "Chatbox öffnen" ersetzt durch "LinuxVR-ViewShot":
er startet ein kleines Skript, das die App per `wayvrctl process-launch`
als Fenster IN WayVR öffnet (ohne wayvrctl: normal auf dem Desktop).

Alles BLOCKIERT (Download) → nur im Hintergrund-Thread aufrufen!
"""

import io
import os
import re
import shutil
import stat
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from core.paths import HOME, app_command

SOURCE_URL = "https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr"
ZIP_URL = "https://codeload.github.com/cubee-cb/linux-vr-compat/zip/refs/heads/master"
SOURCE_PREFIX = "dotfiles/wayvr/"  # im Zip: linux-vr-compat-master/dotfiles/wayvr/…

WAYVR_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "wayvr"
LAUNCHER = WAYVR_DIR / "theme" / "linuxvr-viewshot-open.sh"

# Ordner, die komplett übernommen werden
COPY_DIRS = ("theme/", "palettes/", "sound/")
# conf.d-Dateien, die nur angelegt werden, wenn es sie noch nicht gibt
CONF_IF_MISSING = ("conf.d/custom_panels.yaml", "conf.d/timezones.yaml")
PALETTE = "cubee.json"

# Der Chatbox-Knopf in Cubees watch.xml (mehrzeilig, bis </Button>)
CHAT_BUTTON = re.compile(r'<Button[^>]*_press="::OscSend /chatbox/input"[^>]*>.*?</Button>', re.DOTALL)

# Kamera-Symbol für den Uhr-Knopf (selbst gezeichnet, färbt sich wie die anderen)
VIEWSHOT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24">'
    '<!-- LinuxVR-ViewShot camera icon -->'
    '<path fill="currentColor" d="M9 3L7.2 5H4q-.825 0-1.412.588T2 7v12q0 .825.588 1.413T4 21h16'
    'q.825 0 1.413-.587T22 19V7q0-.825-.587-1.412T20 5h-3.2L15 3zm3 14.5q-1.875 0-3.187-1.312'
    'T7.5 13t1.313-3.187T12 8.5t3.188 1.313T16.5 13t-1.312 3.188T12 17.5m0-2q1.05 0 1.775-.725'
    'T14.5 13t-.725-1.775T12 10.5t-1.775.725T9.5 13t.725 1.775T12 15.5"/></svg>'
)


def viewshot_button(launcher: Path) -> str:
    # ::ShellExec startet per "sh -c" → Pfad in einfache Anführungszeichen
    return (
        f'<Button macro="button_style" _press="::ShellExec \'{launcher}\'" '
        'tooltip_str="LinuxVR-ViewShot" tooltip_side="top">\n'
        '                <sprite color="~color_text" width="40" height="40" src="watch/viewshot.svg" />\n'
        '              </Button>'
    )


def launcher_script(app: Path) -> str:
    return f"""#!/bin/sh
# Angelegt von LinuxVR-ViewShot (Optionen → General → WayVR-Design).
# Öffnet die App als Fenster in WayVR. Ohne wayvrctl: normal auf dem Desktop.
APP='{app}'
if command -v wayvrctl >/dev/null 2>&1 &&
   wayvrctl process-launch --name LinuxVR-ViewShot --env QT_QPA_PLATFORM=wayland "$APP" 1600x1000 floating; then
    exit 0
fi
exec "$APP"  # kein wayvrctl / WayVR antwortet nicht
"""


def download(url: str = ZIP_URL) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "LinuxVR-ViewShot"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def install(zip_bytes: bytes | None = None, log=lambda s: None) -> dict:
    """Installiert alles. Gibt {"files": n, "backup": Pfad|None, "button": bool,
    "wayvrctl": bool} zurück. `zip_bytes` = schon geladenes Zip (für Tests)."""
    if zip_bytes is None:
        log("download")
        zip_bytes = download()
    archive = zipfile.ZipFile(io.BytesIO(zip_bytes))

    # Dateien aus dotfiles/wayvr/ einsammeln: relativer Pfad → Inhalt
    files = {}
    for name in archive.namelist():
        _, _, rel = name.partition(SOURCE_PREFIX)
        if not rel or name.endswith("/") or SOURCE_PREFIX not in name:
            continue
        if rel.startswith(COPY_DIRS):
            files[rel] = archive.read(name)
        elif rel in CONF_IF_MISSING and not (WAYVR_DIR / rel).exists():
            files[rel] = archive.read(name)
    if not any(rel.startswith("theme/") for rel in files):
        raise RuntimeError("WayVR-Design im Download nicht gefunden")

    # watch.xml: Chatbox-Knopf → ViewShot-Knopf
    watch = "theme/gui/watch.xml"
    button_replaced = False
    if watch in files:
        text = files[watch].decode("utf-8")
        text, n = CHAT_BUTTON.subn(viewshot_button(LAUNCHER), text, count=1)
        button_replaced = n == 1
        files[watch] = text.encode("utf-8")
    files["theme/watch/viewshot.svg"] = VIEWSHOT_SVG.encode("utf-8")

    # Backup von allem, was überschrieben wird
    backup = WAYVR_DIR / datetime.now().strftime("backup-viewshot-%Y%m%d-%H%M%S")
    for rel in files:
        target = WAYVR_DIR / rel
        if target.is_file():
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup / rel)

    log("write")
    for rel, data in files.items():
        target = WAYVR_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    # Start-Skript für den Uhr-Knopf
    # AppImage: die .AppImage-Datei starten, sonst UI/start.sh
    LAUNCHER.write_text(launcher_script(app_command()), encoding="utf-8")
    LAUNCHER.chmod(LAUNCHER.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    set_palette(backup)
    return {
        "files": len(files),
        "backup": backup if backup.exists() else None,
        "button": button_replaced,
        "wayvrctl": shutil.which("wayvrctl") is not None,
    }


def set_palette(backup: Path) -> None:
    """Farbpalette auf Cubees stellen. Steht sie schon in WayVRs gespeicherten
    Einstellungen, dort ändern (die gewinnen sonst) – sonst eigene conf.d-Datei."""
    saved = WAYVR_DIR / "conf.d" / "zz-saved-config.json5"
    if saved.is_file():
        text = saved.read_text(encoding="utf-8")
        new, n = re.subn(r'("color_palette"\s*:\s*)(null|"[^"]*")', rf'\1"{PALETTE}"', text)
        if n:
            if new != text:
                (backup / "conf.d").mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, backup / "conf.d" / saved.name)
                saved.write_text(new, encoding="utf-8")
            return
    own = WAYVR_DIR / "conf.d" / "linuxvr-viewshot-palette.yaml"
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_text(f'# Angelegt von LinuxVR-ViewShot (Cubee-Design)\ncolor_palette: "{PALETTE}"\n',
                   encoding="utf-8")


def installed() -> bool:
    """Ist der ViewShot-Knopf auf der Uhr?"""
    watch = WAYVR_DIR / "theme" / "gui" / "watch.xml"
    try:
        return "linuxvr-viewshot-open.sh" in watch.read_text(encoding="utf-8")
    except OSError:
        return False
