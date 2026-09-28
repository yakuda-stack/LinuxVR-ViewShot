"""
core/history.py – Verlauf der Übersetzungen (Main-Seite, Karte "Verlauf").

Nur aktiv, wenn in den Optionen eingeschaltet (config "history", Standard: aus).
Gespeichert wird NUR Text – kein Bild (das Foto kann ja inzwischen gelöscht sein):

    history.json = [ {"time": "2026-09-28 14:32", "photo": "ViewShot_….png",
                      "ocr": "…", "tr": "…", "method": "llm_gemini"}, … ]   neueste zuerst
"""

import json
import threading
from datetime import datetime

from core.paths import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "history.json"
MAX_ENTRIES = 200  # ältere fallen raus – die Datei bleibt klein

_lock = threading.Lock()


def load() -> list[dict]:
    with _lock:
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    return data if isinstance(data, list) else []


def _save(entries: list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")


def add(photo: str, ocr: str, translated: str, method: str) -> dict | None:
    """Neuen Eintrag vorne anfügen. Gibt es dasselbe Foto mit derselben Übersetzung
    schon im Verlauf → nichts Neues (z. B. Foto nochmal angesehen, ↻ mit gleicher Antwort)."""
    if not translated:
        return None
    entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "photo": photo,
             "ocr": ocr, "tr": translated, "method": method}
    entries = load()
    if any(e.get("photo") == photo and e.get("tr") == translated for e in entries):
        return None
    entries.insert(0, entry)
    with _lock:
        _save(entries[:MAX_ENTRIES])
    return entry


def clear() -> None:
    with _lock:
        try:
            HISTORY_FILE.unlink()
        except OSError:
            pass
