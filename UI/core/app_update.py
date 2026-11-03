"""
core/app_update.py – ⬆ Gibt es eine neuere Version der App?

Fragt beim Start einmal GitHub nach dem neuesten Release. Dabei geht nur diese Anfrage
raus, keine Fotos oder Texte. Klappt es nicht (offline, Limit), bleibt der Pfeil einfach weg.
"""

import json
import logging
import re
import threading
import urllib.request

from PyQt6.QtCore import QObject, pyqtSignal

from core.version import VERSION

API_URL = "https://api.github.com/repos/yakuda-stack/LinuxVR-ViewShot/releases/latest"
RELEASE_URL = "https://github.com/yakuda-stack/LinuxVR-ViewShot/releases/latest"
TIMEOUT_S = 6


def fetch_latest() -> str:
    """Neueste Version von GitHub („1.0.8“) oder "" bei einem Fehler."""
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"LinuxVR-ViewShot/{VERSION}",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as reply:
            return str(json.load(reply).get("tag_name", "")).removeprefix("v")
    except (OSError, ValueError) as e:
        logging.info("Update-Prüfung: %s", e)
        return ""


def parts(version: str) -> tuple[int, ...]:
    """„1.0.10“ → (1, 0, 10). Zusätze wie „-alpha“ zählen nicht."""
    return tuple(int(n) for n in re.findall(r"\d+", version.split("-")[0]))


def is_newer(latest: str, current: str = VERSION) -> bool:
    return parts(latest) > parts(current)


class UpdateChecker(QObject):
    """Einmal nachsehen, ohne das Fenster aufzuhalten. latest = neue Version oder ""."""

    found = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.latest = ""

    def start(self) -> None:
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self) -> None:  # Hintergrund – KEINE Widgets anfassen!
        latest = fetch_latest()
        if is_newer(latest):
            self.latest = latest
            self.found.emit(latest)
