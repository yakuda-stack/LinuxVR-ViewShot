"""
core/share.py – Foto an andere Programme weitergeben.

Unter Linux gibt es kein gemeinsames "Teilen"-Menü wie am Handy.
Deshalb pro Programm ein eigener Weg:

  Discord   → Bild in die Zwischenablage + Discord öffnen (dann Strg+V)
              (auch Vesktop / WebCord – als Programm oder als Flatpak)
  Telegram  → telegram-desktop -sendpath <datei>  (öffnet "Senden an…")
  E-Mail    → xdg-email --attach <datei>

Neues Programm? Unten in TARGETS eintragen.
"""

import shutil
import subprocess
from pathlib import Path


def _flatpak_installed(app_id: str) -> bool:
    if not shutil.which("flatpak"):
        return False
    return subprocess.run(["flatpak", "info", app_id], capture_output=True).returncode == 0


def _find(commands: list[str], flatpak_ids: list[str]) -> list[str] | None:
    """Erstes gefundene Programm als Befehlsliste, oder None.
    Erst normale Befehle, dann Flatpaks (z. B. Vesktop: dev.vencord.Vesktop)."""
    for cmd in commands:
        if shutil.which(cmd):
            return [cmd]
    for app_id in flatpak_ids:
        if _flatpak_installed(app_id):
            return ["flatpak", "run", app_id]
    return None


# (Schlüssel, Name, mögliche Befehle, Flatpak-IDs, Art)
DISCORD_FLATPAKS = ["com.discordapp.Discord", "dev.vencord.Vesktop", "com.discordapp.DiscordCanary",
                    "io.github.spacingbat3.webcord"]
TARGETS = [
    ("discord",  "Discord",  ["discord", "vesktop", "discord-canary", "webcord"], DISCORD_FLATPAKS,          "paste"),
    ("telegram", "Telegram", ["telegram-desktop", "Telegram"],                     ["org.telegram.desktop"],  "sendpath"),
    ("email",    "E-Mail",   ["xdg-email"],                                        [],                        "email"),
]


def available() -> list[tuple[str, str]]:
    """[(Schlüssel, Name)] aller installierten Ziele."""
    return [(key, name) for key, name, cmds, fp, _ in TARGETS if _find(cmds, fp)]


def share(key: str, photo: Path) -> str:
    """Startet das Ziel-Programm. Gibt die Art zurück ("paste" = Nutzer muss Strg+V drücken)."""
    for k, _name, cmds, fp, kind in TARGETS:
        if k != key:
            continue
        cmd = _find(cmds, fp)
        if not cmd:
            raise FileNotFoundError(key)
        if kind == "sendpath":
            subprocess.Popen(cmd + ["-sendpath", str(photo)])
        elif kind == "email":
            subprocess.Popen(cmd + ["--attach", str(photo)])
        else:  # paste: nur öffnen, Bild liegt schon in der Zwischenablage
            subprocess.Popen(cmd)
        return kind
    raise KeyError(key)
