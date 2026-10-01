#!/usr/bin/env python3
"""
scripts/make_daemon_contract.py – schreibt daemon/contract.json.

Der Rust-Dienst (daemon/) macht dasselbe wie die App, wenn sie zu ist. Damit beide
nie auseinanderlaufen, kommt alles, was gleich sein MUSS, aus der App:
    i18n       Texte im VR-Panel (der Dienst baut sie beim Kompilieren ein)
    languages  Sprachen für Von/Nach
    defaults   Standardwerte aus ui.json / layer.json
    keys       Cache-Schlüssel (translations.json) für verschiedene Einstellungen
    prompts    Prompts für die KIs (Rust-Test vergleicht Wort für Wort)

Nach einer Änderung an Texten/Prompts in der App:  python3 scripts/make_daemon_contract.py
(tests/test_core.py meldet, wenn die Datei nicht mehr passt).
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "daemon" / "contract.json"

# Texte, die der Dienst braucht (VR-Panel, Statuszeile)
I18N_KEYS = [
    "back", "tr_service", "tr_source", "tr_target", "tr_task", "tr_last_ai",
    "tr_mode_auto", "tr_mode_translate", "tr_mode_explain", "tr_mode_answer",
    "tr_step_ocr", "tr_step_service", "tr_step_classify", "tr_fallback_once",
    "translating", "no_text", "tr_failed", "live_title", "live_status",
    "panel_opacity", "panel_edit_help", "panel_settings", "panel_size", "panel_size_later",
    "panel_move", "panel_reset", "panel_anchor", "panel_anchor_short_left", "panel_anchor_short_right",
    "panel_anchor_short_head", "panel_anchor_short_world", "buttons_title", "detect_short_auto",
    "detect_short_manual", "shutter", "mode_button", "combo_short_left", "combo_short_right",
    "combo_short_both", "tr_route_auto", "tr_route_manual",
    "nav_gallery", "no_photo", "delete", "translate_btn", "vr_delete_sure",
    "tr_group_plain", "tr_group_ai", "vr_page_translate", "copy", "copy_link", "uploading",
    "upload_copy_link", "share", "info", "share_failed", "delete_failed", "tag_text", "tag_qr", "tag_image",
    "vr_copied_image", "vr_link_copied", "vr_uploading", "vr_upload_failed", "vr_shared_paste", "vr_shared",
    "panel_button", "panel_button_short", "panel_open_on_shot_short", "panel_button_size",
    "vr_share_none", "vr_info_folder", "vr_info_date", "vr_info_size", "vr_info_type", "vr_info_link",
] + [f"month_{m}" for m in range(1, 13)]

# Keys, die der Dienst aus ui.json liest (Standardwerte müssen gleich sein)
UI_KEYS = [
    "language", "gallery_main_subfolders", "gallery_folders", "history", "tr_method", "tr_source", "tr_target", "tr_auto", "tr_google_key",
    "tr_deepl_key", "tr_libre_url", "tr_libre_online_url", "tr_libre_online_key", "tr_libre_seen",
    "tr_llm_claude_model", "tr_llm_gemini_model", "tr_llm_chatgpt_model", "tr_llm_custom_cmd",
    "tr_llm_vision_model", "tr_vision_url", "tr_vision_keep_alive", "tr_explain_method",
    "tr_answer_method", "tr_route", "tr_auto_once", "tr_auto_once_photo", "tr_auto_once_next",
    "tr_llm_mode", "tr_llm_gemini_retry", "tr_llm_gemini_retry_s", "tr_llm_claude_retry",
    "tr_llm_claude_retry_s", "tr_llm_chatgpt_retry", "tr_llm_chatgpt_retry_s",
]
LAYER_KEYS = ["live_interval_s", "overlay", "panel", "panel_edit", "panel_port", "panel_opacity",
              "panel_anchor", "detect_mode", "shutter", "mode_button", "panel_button", "panel_button_color",
              "panel_open_on_shot"]

# Einstellungen → erwarteter Cache-Schlüssel
KEY_CASES = [
    {},
    {"tr_method": "libre", "tr_source": "ja", "tr_target": "en"},
    {"tr_method": "llm_claude", "tr_llm_claude_model": "opus"},
    {"tr_method": "llm_claude", "tr_llm_mode": "explain"},
    {"tr_method": "llm_chatgpt", "tr_llm_mode": "answer"},
    {"tr_method": "llm_vision", "tr_llm_mode": "answer"},
    {"tr_method": "llm_vision", "tr_llm_mode": "auto", "tr_answer_method": "llm_claude",
     "tr_explain_method": "llm_gemini"},
    {"tr_method": "llm_vision", "tr_llm_mode": "auto"},
    {"tr_method": "libre", "tr_llm_mode": "answer", "tr_answer_method": "llm_claude"},
    {"tr_method": "libre", "tr_llm_mode": "explain"},
    {"tr_method": "lingva", "tr_llm_mode": "auto"},
]

PROMPT_TEXT = "鬼の居ぬ間の○○\nせんたく\nすいじ"


def build() -> dict:
    sys.path.insert(0, str(ROOT / "UI"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from core import config, i18n, layer_config, translation, vision
    from core import llm_translator as L

    strings = {k: dict(i18n.TEXTS[k]) for k in I18N_KEYS}
    for m in translation.METHODS:
        strings["tr_m_" + m] = dict(i18n.TEXTS["tr_m_" + m])
    prompts = []
    for method in (L.METHOD_CLAUDE, L.METHOD_GEMINI, L.METHOD_CHATGPT):
        for mode in (L.MODE_TRANSLATE, L.MODE_EXPLAIN, L.MODE_ANSWER, L.MODE_CLASSIFY):
            for src in ("", "ja"):
                prompts.append({"kind": "llm", "method": method, "mode": mode, "source": src,
                                "target": "de", "text": PROMPT_TEXT,
                                "prompt": L.make_prompt(PROMPT_TEXT, src, "de", mode, method)})
    for mode in (L.MODE_TRANSLATE, L.MODE_EXPLAIN, L.MODE_ANSWER):
        for image in (True, False):
            for text in (PROMPT_TEXT, ""):
                prompts.append({"kind": "vision", "mode": mode, "image": image, "target": "en",
                                "text": text, "prompt": vision.build_prompt(text, "", "en", mode, image)})
    for image in (True, False):
        prompts.append({"kind": "classify", "image": image, "text": PROMPT_TEXT,
                        "prompt": vision.classify_prompt(PROMPT_TEXT, image)})
        prompts.append({"kind": "task", "image": image, "text": PROMPT_TEXT,
                        "prompt": vision.task_prompt(PROMPT_TEXT, image)})
    prompts.append({"kind": "system", "target": "ja", "prompt": vision.system_prompt("ja")})
    keys = []
    for case in KEY_CASES:
        cfg = dict(config.DEFAULTS, **case)
        keys.append({"cfg": case, "key": translation._key(cfg)})
    return {
        "_comment": "Erzeugt von scripts/make_daemon_contract.py – nicht von Hand ändern.",
        "i18n": strings,
        "languages": [list(translation.AUTO)] + [list(x) for x in translation.LANGUAGES],
        "defaults": {"ui": {k: config.DEFAULTS[k] for k in UI_KEYS},
                     "layer": {k: layer_config.DEFAULTS[k] for k in LAYER_KEYS}},
        "keys": keys,
        "prompts": prompts,
    }


def render(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(build()), encoding="utf-8")
    print(f"✔ {OUT}")
