"""
core/layer_config.py – Einstellungen für den Rust-Layer.

Datei: ~/.config/linuxvr-viewshot/layer.json
Der Layer liest sie alle 0,5 s neu (layer/src/config.rs) – Änderungen
wirken also sofort in VR, ohne Neustart.

Die Namen und Standardwerte müssen zu config.rs passen!
"""

import json

from core.paths import CONFIG_DIR

LAYER_FILE = CONFIG_DIR / "layer.json"

DEFAULTS = {
    "frame_inset_cm": 7,          # Rand zwischen Händen und Rahmen
    "eye_mix": 50,                # 0 = linkes Auge … 100 = rechtes Auge
    "excluded_apps": ["wayvr"],   # hier ist ViewShot aus
    "detect_mode": "auto",        # "auto" = App erkennt Text/QR/Bild, "manual" = in VR wählen
    "shutter": "right",           # Auslöser: "left" / "right" / "both"
    "mode_button": "left",        # Typ wechseln (nur manual): "left" / "right" / "both"
    "icon_position": "bottom_left",  # Ecke des Typ-Symbols (nur manual), siehe ICON_POSITIONS
}

COMBOS = ("left", "right", "both")
ICON_POSITIONS = ("bottom_left", "bottom_right", "top_left", "top_right")


def update(key: str, value) -> dict:
    """Einen Wert ändern: frisch laden, setzen, speichern. So überschreiben
    sich Main-Seite und Optionen nicht gegenseitig."""
    cfg = load()
    cfg[key] = value
    # Auslöser und Typ-Taste nie gleich → die andere ausweichen lassen
    if key in ("shutter", "mode_button") and cfg["shutter"] == cfg["mode_button"]:
        other = "mode_button" if key == "shutter" else "shutter"
        cfg[other] = next(c for c in COMBOS if c != value)
    save(cfg)
    return cfg


def load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # tiefe Kopie (Liste nicht teilen!)
    try:
        cfg.update(json.loads(LAYER_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # erst in eine Hilfsdatei, dann umbenennen → der Layer liest nie eine halbe Datei
    tmp = LAYER_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(LAYER_FILE)
