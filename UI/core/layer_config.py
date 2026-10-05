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
    "mode_button": "left",        # Typ wechseln (auto: 🪄↔🔁, manual: 🖼📝🔳🔁): "left" / "right" / "both"
    "icon_position": "bottom_left",  # Ecke des Typ-Symbols, siehe ICON_POSITIONS
    "aspect": "free",             # 📐 Seitenverhältnis des Fotos, siehe ASPECTS
    "gif_hold": True,             # 🎞 Auslöser gedrückt halten = GIF aufnehmen (Foto dann beim Loslassen)
    "gif_max_s": 15,              # 🎞 längste GIF-Aufnahme in Sekunden (1–15)
    "gif_fps": 10,                # 🎞 Bilder pro Sekunde im GIF (5–15)
    "live_interval_s": 3,         # 🔁 Lens: alle so viele Sekunden neu fotografieren + übersetzen
    "overlay": False,             # 🥽 Übersetzung in VR über dem Original (overlay/overlay.png)
    "panel": True,                # 🪟 Übersetzungs-Panel in VR (panel/panel.png, ui/vr_panel.py)
    "panel_anchor": "left",       # hängt an: "left" / "right" (Hand), "head", "world"
    "panel_edit": False,          # Bearbeiten: Grip = verschieben, Ecke + Trigger = Größe
    "panel_port": 47931,          # Klicks aus VR kommen per UDP an diesen Port
    "panel_opacity": 100,         # Deckkraft des Panels in % (30–100, malt ui/vr_panel.py)
    "panel_button": True,         # 🔘 Knopf (Handgelenk) klappt das Panel auf/zu – wie bei WayVR
    "panel_button_color": "#5b8dc9",  # Farbe des Knopfs (passend zum Hand-Overlay)
    "panel_open_on_shot": True,   # zugeklapptes Panel geht nach einem Foto von selbst auf
    # ⚙ Hintergrund-Dienst (viewshot-daemon): übersetzt + malt das Panel, wenn die App zu ist.
    # Der Layer weckt ihn: "off" / "all" (jedes VR-Spiel) / "selected" (nur daemon_apps)
    "daemon": "all",
    "daemon_apps": [],
}

DAEMON_MODES = ("off", "all", "selected")

COMBOS = ("left", "right", "both")
ICON_POSITIONS = ("bottom_left", "bottom_right", "top_left", "top_right")
ASPECTS = ("free", "1:1", "16:9")


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
