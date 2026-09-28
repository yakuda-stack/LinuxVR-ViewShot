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
import logging
import threading
import time
import urllib.request
from pathlib import Path

from core import llm_translator as L
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
           T.METHOD_LIBRE_ONLINE, T.METHOD_DEEPL, T.METHOD_CUSTOM] + L.METHODS

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
    "tr_libre_seen": False,      # lokaler Server wurde schon mal gefunden (Docker)
    "tr_favorites": [],          # ⭐ Dienste fürs Main-Dropdown ([] = alle eingerichteten)
    **L.DEFAULTS,                # KI: Modelle + eigener Befehl
}


class TranslationError(Exception):
    pass


def is_configured(method: str, cfg: dict) -> bool:
    """Ist der Dienst eingerichtet? Nur solche stehen im Dropdown auf der Main-Seite."""
    if method in (T.METHOD_LINGVA, T.METHOD_GOOGLE):
        return True  # brauchen nichts
    if method == T.METHOD_LIBRE:
        return (bool(cfg.get("tr_libre_seen")) or T.libretranslate_installed()
                or (cfg.get("tr_libre_url") or T.DEFAULT_LIBRE_URL) != T.DEFAULT_LIBRE_URL)
    if method == T.METHOD_LIBRE_ONLINE:
        return bool(cfg.get("tr_libre_online_key") or cfg.get("tr_libre_online_url"))
    if method == T.METHOD_DEEPL:
        return bool(cfg.get("tr_deepl_key"))
    if method == T.METHOD_CUSTOM:
        snippet = (cfg.get("tr_custom_snippet") or "").strip()
        return bool(snippet) and snippet != LIBRE_EXAMPLE.strip()
    if method == L.METHOD_LLM_CUSTOM:
        return bool((cfg.get("tr_llm_custom_cmd") or "").strip())
    if L.is_llm(method):
        return L.installed(method)
    return False


def configured_methods(cfg: dict) -> list[str]:
    """Eingerichtete Dienste – der gerade gewählte ist immer dabei."""
    return [m for m in METHODS if m == cfg.get("tr_method") or is_configured(m, cfg)]


def menu_methods(cfg: dict) -> list[str]:
    """Dienste fürs Main-Dropdown: nur die ⭐ Favoriten (wenn davon welche eingerichtet
    sind), sonst alle eingerichteten. Der gerade gewählte ist immer dabei."""
    methods = configured_methods(cfg)
    favs = set(cfg.get("tr_favorites") or [])
    if not favs & set(methods):
        return methods  # nichts favorisiert → wie bisher
    return [m for m in methods if m in favs or m == cfg.get("tr_method")]


def _chain(method: str) -> list[str]:
    """Reihenfolge der Versuche: gewählter Dienst, dann Lingva, dann Google."""
    chain = [method]
    for fallback in (T.METHOD_LINGVA, T.METHOD_GOOGLE):
        if fallback not in chain:
            chain.append(fallback)
    return chain


def _try(method: str, text: str, cfg: dict,
         progress=lambda step, arg="": None) -> tuple[str | None, str]:
    """Ein Dienst, ein Versuch. (Übersetzung oder None, Fehlertext)."""
    src, tgt = cfg.get("tr_source", ""), cfg["tr_target"]  # "" = automatisch erkennen
    if L.is_llm(method):
        try:
            return L.translate(method, cfg, text, src, tgt,
                               on_retry=lambda n: progress("retry", f"{method}:{n}")), ""
        except L.LLMError as e:
            return None, str(e)
    tr = T.get_translator(method, deepl_key=cfg["tr_deepl_key"], libre_url=cfg["tr_libre_url"],
                          google_key=cfg["tr_google_key"],
                          libre_online_url=cfg["tr_libre_online_url"],
                          libre_online_key=cfg["tr_libre_online_key"],
                          custom_snippet=cfg["tr_custom_snippet"])
    out = tr.translate(text, src, tgt)
    return out, tr.last_error


def translate_only(method: str, text: str, cfg: dict) -> tuple[str | None, str]:
    """Nur DIESER Dienst, kein Ersatz (für den Test-Knopf beim Einrichten).
    (Übersetzung oder None, Fehlertext)."""
    return _try(method, text, cfg)


def translate_text_used(text: str, cfg: dict, log=lambda s: None,
                        progress=lambda step, arg="": None) -> tuple[str, str]:
    """Wie translate_text, gibt aber zusätzlich zurück, WELCHER Dienst es geschafft hat
    (z. B. "lingva", wenn Claude Code nicht ging). progress("service", Dienst) vor jedem Versuch."""
    for method in _chain(cfg["tr_method"]):
        progress("service", method)
        start = time.monotonic()
        out, error = _try(method, text, cfg, progress)
        logging.info("Übersetzen %s: %.1f s, %s", method, time.monotonic() - start,
                     "ok" if out else f"Fehler: {error}")
        if out:
            return out, method
        log(error or f"{method}: keine Antwort")
    raise TranslationError("kein Dienst hat geantwortet")


def translate_text(text: str, cfg: dict, log=lambda s: None) -> str:
    """Übersetzt mit dem gewählten Dienst. Fällt der aus, automatisch Lingva, dann Google."""
    return translate_text_used(text, cfg, log)[0]


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
    method = cfg["tr_method"]
    model = L.model_of(method, cfg)
    if model:  # anderes KI-Modell = andere Übersetzung
        # "@" (nicht mehr ":"): alte Einträge enthielten evtl. Lingva-Ergebnisse
        # unter dem KI-Namen → werden so nicht mehr als "KI-Übersetzung" gezeigt
        method += "@" + model
    if L.is_llm(cfg["tr_method"]):
        mode = cfg.get("tr_llm_mode") or L.MODE_TRANSLATE
        if mode != L.MODE_TRANSLATE:  # Kontext / Antwort ≠ Übersetzung
            method += f"#{mode}{L.prompt_version(cfg['tr_method'], mode)}"
    return f"{method}|{cfg.get('tr_source', '') or 'auto'}|{cfg['tr_target']}"


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


def set_ocr(photo: Path, text: str) -> None:
    """Von Hand korrigierter Text fürs Foto: ersetzt die Erkennung, alte
    Übersetzungen (vom falsch gelesenen Text) fliegen raus."""
    with _cache_lock:
        cache = _load_cache()
        cache[photo.name] = {"ocr": text, "tr": {}}
        _save_cache(cache)


def ocr_text(photo: Path, priority: bool = False) -> str:
    """Erkannter Text im Foto (aus dem Cache, sonst OCR). BLOCKIERT → nur im Thread!"""
    with _cache_lock:
        entry = _load_cache().get(photo.name)
    if entry and "ocr" in entry:
        return entry["ocr"]
    text = ocr.read_text(photo, priority)  # langsam – ohne Lock, damit andere weiterkommen
    with _cache_lock:
        cache = _load_cache()
        cache.setdefault(photo.name, {})["ocr"] = text
        _save_cache(cache)
    return text


def translate_photo(photo: Path, cfg: dict, log=lambda s: None,
                    progress=lambda step, arg="": None) -> tuple[str, str, str]:
    """Liest den Text im Foto und übersetzt ihn. BLOCKIERT → nur im Thread!
    Gibt (erkannter Text, Übersetzung, benutzter Dienst) zurück;
    ("", "", Dienst) = kein Text im Bild. Der Dienst ist ein anderer als in cfg,
    wenn der gewählte ausgefallen ist und Lingva/Google übernommen hat."""
    method = cfg["tr_method"]
    # "ocr_wait" = die Bild-Erkennung liest gerade ein anderes Foto (max. 1 abwarten)
    progress("ocr_wait" if ocr.busy() else "ocr")
    text = ocr_text(photo, priority=True)  # Vorrang vor der Bild-Erkennung
    if not text:
        return "", "", method
    with _cache_lock:
        translated = _load_cache().get(photo.name, {}).get("tr", {}).get(_key(cfg))
    if translated is None:
        translated, method = translate_text_used(text, cfg, log, progress)
        # unter dem Dienst merken, der es wirklich übersetzt hat
        used = dict(cfg, tr_method=method)
        with _cache_lock:
            cache = _load_cache()
            cache.setdefault(photo.name, {}).setdefault("tr", {})[_key(used)] = translated
            _save_cache(cache)
    return text, translated, method
