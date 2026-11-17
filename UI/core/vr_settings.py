"""
core/vr_settings.py – Was auf der ⚙ Einstellungs-Seite im VR-Panel steht.

Gilt für BEIDE Panels: ui/vr_panel.py (App offen) und den Rust-Dienst
(daemon/src/panel.rs) – der bekommt diese Liste über daemon/contract.json
(python3 scripts/make_daemon_contract.py).

Zwei Tabs (📸 Shot | 🥽 VR), darin einklappbare Gruppen – gleiche Reihenfolge wie
in Optionen → Shot / VR der Desktop-App. Neue Einstellung = eine Zeile hier.

Einträge (alle Werte aus layer.json):
    toggle   key, label                        ✔ / ✕ an/aus
    choice   key, label, options, cols         Knöpfe nebeneinander (cols = pro Zeile)
    slider   key, label, min, max, step, unit  Leiste; fmt = eigener Text mit {v} / {inv}
             key "@button_cm" = 🔘 Knopf-Größe (button_pose.json, nicht layer.json)
    size     –                                 Panel-Größe je Seite (Übersetzung/Galerie/⚙)
    actions  actions [[name, label]]           ✥ Verschieben, ⟲ Position
    colors   key                               🔘 Farben zum Antippen
    list     key, hint, empty                  Liste, antippen = entfernen
Texte in options: "=1:1" = genau so anzeigen, sonst i18n-Schlüssel.
"""

from core import layer_config


def _toggle(key: str, label: str) -> dict:
    return {"type": "toggle", "key": key, "label": label}


def _choice(key: str, label: str | None, options: list, cols: int = 0) -> dict:
    return {"type": "choice", "key": key, "label": label, "options": [list(o) for o in options], "cols": cols}


def _slider(key: str, label: str | None, lo: int, hi: int, step: int = 1, unit: str = "", fmt: str = "") -> dict:
    return {"type": "slider", "key": key, "label": label, "min": lo, "max": hi, "step": step,
            "unit": unit, "fmt": fmt}


def _group(gid: str, icon: str, title: str, items: list) -> dict:
    return {"id": gid, "icon": icon, "title": title, "items": items}


COMBOS = [(c, "combo_short_" + c) for c in layer_config.COMBOS]

TABS = [
    {"id": "shot", "label": "vr_tab_shot", "groups": [
        _group("gif", "🎞", "gif_card", [
            _toggle("gif_hold", "vr_gif_hold"),
            _slider("gif_max_s", "gif_max", 1, 15, 1, " s"),
            _choice("gif_stabilize", "gif_stab", [(m, "gif_stab_short_" + m) for m in layer_config.STABILIZE]),
            _toggle("pin_lock", "vr_pin_lock"),
        ]),
        _group("buttons", "🎮", "buttons_title", [
            _choice("detect_mode", "detect_mode", [("auto", "detect_short_auto"), ("manual", "detect_short_manual")]),
            _choice("shutter", "shutter", COMBOS),
            _choice("mode_button", "mode_button", COMBOS),
        ]),
        _group("icon", "🔣", "icon_position", [
            _choice("icon_position", None, [(p, p) for p in ("top_left", "top_right", "bottom_left", "bottom_right")],
                    cols=2),
        ]),
        _group("aspect", "📐", "aspect_card", [
            _choice("aspect", None, [("free", "aspect_free"), ("1:1", "=1:1"), ("16:9", "=16:9")]),
        ]),
        _group("frame", "🔲", "frame_size", [_slider("frame_inset_cm", None, 0, 15, 1, fmt="vr_frame_value")]),
        _group("eye", "👁", "eye", [_slider("eye_mix", None, 0, 100, 5, fmt="vr_eye_value")]),
        _group("excluded", "🚫", "excluded", [
            {"type": "list", "key": "excluded_apps", "hint": "vr_excluded_hint", "empty": "vr_excluded_empty"},
        ]),
    ]},
    {"id": "vr", "label": "vr_tab_vr", "groups": [
        _group("panel", "🪟", "vr_panel_group", [
            {"type": "size"},
            _slider("panel_opacity", "panel_opacity", 30, 100, 10, " %"),
            _choice("panel_anchor", "panel_anchor", [(a, "panel_anchor_short_" + a)
                                                     for a in ("left", "right", "head", "world")]),
            {"type": "actions", "actions": [["move", "panel_move"], ["reset", "panel_reset"]]},
        ]),
        _group("button", "", "panel_button", [
            _toggle("panel_button", "panel_button_short"),
            _toggle("panel_open_on_shot", "panel_open_on_shot_short"),
            _slider("@button_cm", "panel_button_size", 2, 20, 1, " cm"),
            {"type": "colors", "key": "panel_button_color"},
        ]),
        _group("lens", "", "vr_lens_group", [_slider("live_interval_s", None, 1, 10, 1, fmt="vr_live_value")]),
        _group("overlay", "", "overlay_card", [_toggle("overlay", "overlay_on")]),
    ]},
]

# Seiten, deren Größe man unter 🪟 einstellen kann (wie vr_panel.PAGES)
SIZE_PAGES = [("translate", "vr_page_translate"), ("gallery", "nav_gallery"), ("settings", "panel_settings")]


def layer_keys() -> list[str]:
    """Alle layer.json-Schlüssel, die die Seite liest (für den Vertrag mit dem Dienst)."""
    keys = []
    for tab in TABS:
        for group in tab["groups"]:
            for item in group["items"]:
                key = item.get("key", "")
                if key and not key.startswith("@") and key not in keys:
                    keys.append(key)
    return keys


def text_keys() -> list[str]:
    """Alle i18n-Schlüssel der Seite (für den Vertrag mit dem Dienst)."""
    keys = ["panel_settings", "panel_size", "panel_size_later"] + [k for _, k in SIZE_PAGES]
    for tab in TABS:
        keys.append(tab["label"])
        for group in tab["groups"]:
            keys.append(group["title"])
            for item in group["items"]:
                for k in ("label", "fmt", "hint", "empty"):
                    if item.get(k):
                        keys.append(item[k])
                for _, label in item.get("options", []):
                    if not label.startswith("="):
                        keys.append(label)
                for _, label in item.get("actions", []):
                    keys.append(label)
    return list(dict.fromkeys(keys))


def find(key: str) -> dict | None:
    for tab in TABS:
        for group in tab["groups"]:
            for item in group["items"]:
                if item.get("key") == key:
                    return item
    return None


def snap(item: dict, value: float) -> int:
    """Schieber-Wert auf Schrittweite + Grenzen bringen."""
    lo, hi, step = item["min"], item["max"], max(1, item["step"])
    v = lo + round((value - lo) / step) * step
    return int(max(lo, min(hi, v)))
