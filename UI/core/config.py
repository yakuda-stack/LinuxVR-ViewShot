"""
core/config.py – Einstellungen der UI laden und speichern.

Gespeichert wird als JSON in ~/.config/linuxvr-viewshot/ui.json.
Neue Einstellung? Einfach unten in DEFAULTS eintragen.
"""

import json

from core.paths import CONFIG_DIR
from core.translation import DEFAULTS as TRANSLATION_DEFAULTS

CONFIG_FILE = CONFIG_DIR / "ui.json"

DEFAULTS = {
    "language": "de",   # "de" oder "en"
    "thumb_size": 180,  # Kachelgröße in der Galerie (Pixel)
    "cleanup_qr": False,    # beim Beenden QR-Code-Fotos in den Papierkorb
    "cleanup_text": False,  # beim Beenden Text-Fotos in den Papierkorb
    **TRANSLATION_DEFAULTS,  # tr_… Einstellungen (Optionen → Übersetzung)
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass  # Datei fehlt oder ist kaputt → Standardwerte
    return cfg


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
