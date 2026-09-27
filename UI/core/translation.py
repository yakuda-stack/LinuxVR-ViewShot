"""
core/translation.py – Foto → Text (OCR) → Übersetzung.

Die eigentlichen Übersetzer kommen 1:1 aus OSC-DreamChatbox
(core/translators.py + core/custom_translator.py). Hier wird nur
zusammengesteckt:  Einstellungen aus ui.json  →  translate_with_fallback().

Ergebnisse werden in translations.json gemerkt, damit ein Foto nicht bei
jedem Öffnen neu gelesen/übersetzt wird:
    { "ViewShot_….png": { "ocr": "…", "tr": { "lingva|de": "…" } } }
"""

import json
import threading
import urllib.request
from pathlib import Path

from core import ocr
from core import translators as T
from core.custom_translator import LIBRE_EXAMPLE
from core.paths import CONFIG_DIR

CACHE_FILE = CONFIG_DIR / "translations.json"
# Übersetzung (Main) und Bild-Erkennung (Tags) schreiben beide in den Cache –
# gleichzeitig aus zwei Threads. Lesen-Ändern-Speichern also nur mit Lock.
_cache_lock = threading.RLock()

# Reihenfolge = Reihenfolge im Dropdown (Optionen → Übersetzung)
METHODS = [T.METHOD_LINGVA, T.METHOD_GOOGLE, T.METHOD_LIBRE,
           T.METHOD_LIBRE_ONLINE, T.METHOD_DEEPL, T.METHOD_CUSTOM]

# Zielsprachen (Code, Deutsch, Englisch)
LANGUAGES = [
    ("de", "Deutsch", "German"), ("en", "Englisch", "English"),
    ("fr", "Französisch", "French"), ("es", "Spanisch", "Spanish"),
    ("it", "Italienisch", "Italian"), ("pt", "Portugiesisch", "Portuguese"),
    ("nl", "Niederländisch", "Dutch"), ("pl", "Polnisch", "Polish"),
    ("ru", "Russisch", "Russian"), ("uk", "Ukrainisch", "Ukrainian"),
    ("tr", "Türkisch", "Turkish"), ("ja", "Japanisch", "Japanese"),
    ("ko", "Koreanisch", "Korean"), ("zh-CN", "Chinesisch", "Chinese"),
]

# Standardwerte – werden in core/config.py mit eingetragen
# Quellsprache: "" = automatisch erkennen (versteht jeder Dienst)
AUTO = ("", "Automatisch erkennen", "Detect automatically")

DEFAULTS = {
    "tr_method": T.METHOD_LINGVA,
    "tr_source": "",             # "" = automatisch erkennen
    "tr_target": "de",
    "tr_auto": True,             # neues Foto automatisch übersetzen
    "tr_google_key": "",
    "tr_deepl_key": "",
    "tr_libre_url": T.DEFAULT_LIBRE_URL,
    "tr_libre_online_url": "",   # "" = Vorlage de.libretranslate.com
    "tr_libre_online_key": "",
    "tr_custom_snippet": LIBRE_EXAMPLE,
}


class TranslationError(Exception):
    pass


def translate_text(text: str, cfg: dict, log=lambda s: None) -> str:
    """Übersetzt mit dem gewählten Dienst. Fällt der aus, automatisch
    Lingva, dann Google (macht translate_with_fallback aus DreamChatbox)."""
    out = T.translate_with_fallback(
        cfg["tr_method"], text,
        cfg.get("tr_source", ""),  # "" = automatisch erkennen
        cfg["tr_target"],
        deepl_key=cfg["tr_deepl_key"],
        libre_url=cfg["tr_libre_url"],
        google_key=cfg["tr_google_key"],
        libre_online_url=cfg["tr_libre_online_url"],
        libre_online_key=cfg["tr_libre_online_key"],
        custom_snippet=cfg["tr_custom_snippet"],
        log=log,
    )
    if out is None:
        raise TranslationError("kein Dienst hat geantwortet")
    return out


# ----------------------------------------------------------------------
# Foto übersetzen (mit Cache)
# ----------------------------------------------------------------------
def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")


def _key(cfg: dict) -> str:
    return f"{cfg['tr_method']}|{cfg.get('tr_source', '') or 'auto'}|{cfg['tr_target']}"


# ----------------------------------------------------------------------
# Läuft ein LibreTranslate-Server? (z. B. in Docker – dann ist nichts
# "installiert", aber Port 5000 antwortet trotzdem)
# ----------------------------------------------------------------------
LIBRE_PORT_URLS = ["http://127.0.0.1:5000", "http://localhost:5000"]


def libre_answers(url: str, timeout: float = 2.0) -> bool:
    """True, wenn unter url ein LibreTranslate antwortet (GET /languages)."""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/languages",
                                     headers={"User-Agent": "LinuxVR-ViewShot"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200 and resp.read(1) == b"["
    except Exception:  # noqa: BLE001 – aus/zu/falscher Dienst: alles "nein"
        return False


def find_libre(configured: str) -> str | None:
    """Prüft erst die eingestellte Adresse, dann zusätzlich Port 5000.
    Gibt die Adresse zurück, die antwortet (oder None). BLOCKIERT kurz."""
    for url in [configured or T.DEFAULT_LIBRE_URL] + LIBRE_PORT_URLS:
        if libre_answers(url):
            return url
    return None


def cached(photo: Path, cfg: dict) -> tuple[str, str] | None:
    """(erkannter Text, Übersetzung) aus dem Cache, sonst None."""
    with _cache_lock:
        entry = _load_cache().get(photo.name)
    if not entry or "ocr" not in entry:
        return None
    if not entry["ocr"]:
        return "", ""  # kein Text im Foto – muss nicht übersetzt werden
    translated = entry.get("tr", {}).get(_key(cfg))
    return (entry["ocr"], translated) if translated is not None else None


def ocr_text(photo: Path) -> str:
    """Erkannter Text im Foto (aus dem Cache, sonst OCR). BLOCKIERT → nur im Thread!"""
    with _cache_lock:
        entry = _load_cache().get(photo.name)
    if entry and "ocr" in entry:
        return entry["ocr"]
    text = ocr.read_text(photo)  # langsam – ohne Lock, damit andere weiterkommen
    with _cache_lock:
        cache = _load_cache()
        cache.setdefault(photo.name, {})["ocr"] = text
        _save_cache(cache)
    return text


def translate_photo(photo: Path, cfg: dict, log=lambda s: None) -> tuple[str, str]:
    """Liest den Text im Foto und übersetzt ihn. BLOCKIERT → nur im Thread!
    Gibt (erkannter Text, Übersetzung) zurück; ("", "") = kein Text im Bild."""
    text = ocr_text(photo)
    if not text:
        return "", ""
    with _cache_lock:
        translated = _load_cache().get(photo.name, {}).get("tr", {}).get(_key(cfg))
    if translated is None:
        translated = translate_text(text, cfg, log)
        with _cache_lock:
            cache = _load_cache()
            cache.setdefault(photo.name, {}).setdefault("tr", {})[_key(cfg)] = translated
            _save_cache(cache)
    return text, translated
