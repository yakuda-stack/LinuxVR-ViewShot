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
from core import vision
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
    if method == L.METHOD_VISION:  # Ollama installiert oder eigene Adresse (z. B. Docker)
        return L.installed(method) or bool((cfg.get("tr_vision_url") or "").strip())
    if L.is_llm(method):
        return L.installed(method)
    return False


def privacy(method: str) -> str:
    """Wohin geht der erkannte Text? (Hinweis in der UI) – verschickt wird nur Text, nie das Foto.
    "local" = bleibt auf dem PC · "cloud" = Internet-Dienst · "custom" = hängt von der Einrichtung ab"""
    if method in (T.METHOD_LIBRE, L.METHOD_VISION):
        return "local"
    if method in (T.METHOD_CUSTOM, L.METHOD_LLM_CUSTOM):
        return "custom"
    return "cloud"


def privacy_text(method: str) -> str:
    from core.i18n import tr
    return tr("privacy_" + privacy(method), service=tr("tr_m_" + method))


def method_groups(methods: list[str]) -> list[tuple[str, list[str]]]:
    """Dienste für Menüs gliedern: [(Text-Key der Überschrift, Dienste)] –
    erst normale Übersetzer, dann die KIs (Reihenfolge bleibt)."""
    return [("tr_group_plain", [m for m in methods if not L.is_llm(m)]),
            ("tr_group_ai", [m for m in methods if L.is_llm(m)])]


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
         progress=lambda step, arg="": None, image=None) -> tuple[str | None, str]:
    """Ein Dienst, ein Versuch. (Übersetzung oder None, Fehlertext)."""
    src, tgt = cfg.get("tr_source", ""), cfg["tr_target"]  # "" = automatisch erkennen
    if L.is_llm(method):
        try:
            return L.translate(method, cfg, text, src, tgt,
                               on_retry=lambda n: progress("retry", f"{method}:{n}"),
                               # Antwort schon beim Schreiben zeigen (Statuszeile/Feld)
                               on_partial=lambda s: progress("partial", s), image=image), ""
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
                        progress=lambda step, arg="": None, image=None,
                        info: dict | None = None) -> tuple[str, str]:
    """Wie translate_text, gibt aber zusätzlich zurück, WELCHER Dienst es geschafft hat
    (z. B. "lingva", wenn Claude Code nicht ging). progress("service", Dienst) vor jedem Versuch."""
    main = cfg["tr_method"]
    cfg = route(cfg, text, image, log, progress)  # 🤖 Auto / Dienst je Aufgabe
    chain = _chain(cfg["tr_method"])
    if main not in chain:  # Kontext-/Rätsel-Dienst geht nicht → Haupt-Dienst übersetzt
        chain.insert(1, main)
    for method in chain:
        if method != cfg["tr_method"]:
            cfg = dict(cfg, tr_llm_mode=L.MODE_TRANSLATE)  # Ersatz: einfach übersetzen
        if not text.strip() and method != L.METHOD_VISION:
            continue  # ohne erkannten Text kann nur das Bild-LLM selbst lesen
        progress("service", method)
        start = time.monotonic()
        out, error = _try(method, text, cfg, progress, image=image)
        logging.info("%s %s: %.1f s, %s", cfg.get("tr_llm_mode") or "translate", method,
                     time.monotonic() - start,
                     "ok" if out else f"Fehler: {error}")
        if out:
            if info is not None:  # „Letzte KI“: wer + welche Aufgabe
                info.update(method=method, task=cfg.get("tr_llm_mode") or L.MODE_TRANSLATE)
            return out, method
        log(error or f"{method}: keine Antwort")
    raise TranslationError("kein Dienst hat geantwortet")


ROUTE_AUTO, ROUTE_MANUAL = "auto", "manual"


def route_mode(cfg: dict) -> str:
    """🤖 Auto geht nur mit einer KI als Haupt-Dienst (LibreTranslate & Co. können nicht entscheiden)."""
    if cfg.get("tr_route", ROUTE_AUTO) == ROUTE_AUTO and L.is_llm(cfg.get("tr_method", "")):
        return ROUTE_AUTO
    return ROUTE_MANUAL


def set_main(cfg: dict, method: str) -> None:
    """Main-Dienst wechseln. Springt der Modus dadurch auf ✋ Manuell (z. B. LibreTranslate),
    Aufgabe auf „Übersetzen“ – sonst hinge noch „Kontext“ o. Ä. von früher dran → Cloud-KI."""
    was_auto = route_mode(cfg) == ROUTE_AUTO
    cfg["tr_method"] = method
    if was_auto and route_mode(cfg) == ROUTE_MANUAL:
        cfg["tr_llm_mode"] = L.MODE_TRANSLATE


def set_route(cfg: dict, route: str) -> None:
    """Modus umstellen. → ✋ Manuell: mit „Übersetzen“ anfangen (nichts Altes erbt)."""
    was_auto = route_mode(cfg) == ROUTE_AUTO
    cfg["tr_route"] = route
    if was_auto and route_mode(cfg) == ROUTE_MANUAL:
        cfg["tr_llm_mode"] = L.MODE_TRANSLATE


def task_cfg(cfg: dict) -> dict:
    """cfg mit der Aufgabe, die JETZT gilt: Manuell = die gewählte; Auto = „auto“ (Haupt-KI
    entscheidet) oder die einmal von Hand gewählte (tr_auto_once)."""
    if route_mode(cfg) == ROUTE_MANUAL:
        mode = cfg.get("tr_llm_mode")
        return dict(cfg, tr_llm_mode=mode if mode in L.MODES else L.MODE_TRANSLATE)
    once = cfg.get("tr_auto_once") or ""
    return dict(cfg, tr_llm_mode=once if once in L.MODES else L.MODE_AUTO)


def photo_task_cfg(cfg: dict, photo_name: str) -> tuple[dict, bool]:
    """Wie task_cfg, aber für ein bestimmtes Foto: die Hand-Auswahl bei 🤖 Auto gilt fürs Foto,
    bei dem sie gewählt wurde, und das NÄCHSTE – danach wieder Auto.
    Ändert cfg (tr_auto_once…); (Aufgaben-cfg, ob cfg geändert wurde → speichern)."""
    changed = False
    if route_mode(cfg) == ROUTE_AUTO and cfg.get("tr_auto_once") and photo_name:
        if photo_name not in (cfg.get("tr_auto_once_photo"), cfg.get("tr_auto_once_next")):
            if not cfg.get("tr_auto_once_next"):
                cfg["tr_auto_once_next"] = photo_name  # das nächste Foto – gilt noch
            else:
                cfg["tr_auto_once"] = ""  # übernächstes → wieder 🤖 Auto
                cfg["tr_auto_once_photo"] = cfg["tr_auto_once_next"] = ""
            changed = True
    return task_cfg(cfg), changed


def route(cfg: dict, text: str, image=None, log=lambda s: None,
          progress=lambda step, arg="": None) -> dict:
    """Welche Aufgabe, welcher Dienst? → cfg mit tr_method / tr_llm_mode dafür.
    🤖 Auto: bei jedem Foto neu – die Haupt-KI teilt zu (Übersetzen macht sie selbst,
    Kontext / Frage gehen an den dort eingestellten Dienst). Sonst: Aufgabe von Hand,
    Dienst fest je Aufgabe. Der Haupt-Dienst wird dabei NIE umgestellt."""
    mode = cfg.get("tr_llm_mode") or L.MODE_TRANSLATE
    auto = mode == L.MODE_AUTO  # _routed: Bild-LLM muss „Quiz?“ nicht nochmal fragen
    if auto:
        mode = classify(cfg, text, image, log, progress) if L.has_tasks(cfg) else L.MODE_TRANSLATE
        progress("auto", mode)
    method = L.task_method(cfg, mode)
    if mode != L.MODE_TRANSLATE and (not method or not is_configured(method, cfg)
                                     or (not text.strip() and method != L.METHOD_VISION)):
        method, mode = cfg["tr_method"], L.MODE_TRANSLATE  # kann der Dienst nicht → übersetzen
    return dict(cfg, tr_method=method or cfg["tr_method"], tr_llm_mode=mode, _routed=auto)


_QUIZ_MARKS = ("?", "？", "○", "〇", "＿", "___", "□")


def looks_like_quiz(text: str) -> bool:
    """Ohne KI zum Entscheiden: Fragezeichen/Lücke + mehrere Zeilen (Antworten) = Quiz."""
    lines = [t for t in text.splitlines() if t.strip()]
    return len(lines) >= 3 and any(m in text for m in _QUIZ_MARKS)


def classify(cfg: dict, text: str, image=None, log=lambda s: None,
             progress=lambda step, arg="": None) -> str:
    """🤖 Auto: Aufgabe für dieses Foto. Die Haupt-KI entscheidet (kurze Ein-Wort-Frage);
    ist der Haupt-Dienst keine KI (z. B. LibreTranslate) → einfache Regel (looks_like_quiz)."""
    main = cfg["tr_method"]
    if L.is_llm(main) and is_configured(main, cfg) and (text.strip() or main == L.METHOD_VISION):
        progress("classify", main)
        try:
            if main == L.METHOD_VISION:
                return vision.classify(cfg, text, image)
            verdict = L.translate(main, dict(cfg, tr_llm_mode=L.MODE_CLASSIFY), text,
                                  cfg.get("tr_source", ""), cfg["tr_target"])
            return vision.parse_task(verdict)
        except L.LLMError as e:
            log(str(e))
    return L.MODE_ANSWER if looks_like_quiz(text) else L.MODE_TRANSLATE


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
    # erst Hilfsdatei, dann umbenennen → der ⚙ Dienst liest nie eine halbe Datei
    tmp = CACHE_FILE.with_name(CACHE_FILE.name + ".tmp")
    tmp.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_FILE)


def _svc(method: str, cfg: dict) -> str:
    model = L.model_of(method, cfg)
    # "@" (nicht mehr ":"): alte Einträge enthielten evtl. Lingva-Ergebnisse
    # unter dem KI-Namen → werden so nicht mehr als "KI-Übersetzung" gezeigt
    return method + ("@" + model if model else "")  # anderes KI-Modell = andere Übersetzung


def _key(cfg: dict) -> str:
    main = cfg["tr_method"]
    method = _svc(main, cfg)
    mode = cfg.get("tr_llm_mode") or L.MODE_TRANSLATE
    if mode == L.MODE_AUTO and L.has_tasks(cfg):  # 🤖 alle beteiligten Dienste gehören dazu
        method += "#auto" + "".join(f"|{m}={_svc(L.task_method(cfg, m), cfg)}"
                                    f"{L.prompt_version(L.task_method(cfg, m), m)}"
                                    for m in L.TASK_KEYS if L.task_method(cfg, m))
    elif mode in L.TASK_KEYS and L.task_method(cfg, mode):  # Kontext / Antwort ≠ Übersetzung
        svc = L.task_method(cfg, mode)
        method += f"#{mode}{L.prompt_version(svc, mode)}"
        if svc != main:
            method += "=" + _svc(svc, cfg)
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


def last_ai(photo: Path, cfg: dict) -> tuple[str, str] | None:
    """(Dienst, Aufgabe), die die gespeicherte Antwort geschrieben haben – für „Letzte KI“."""
    with _cache_lock:
        who = (_load_cache().get(photo.name) or {}).get("who", {}).get(_key(cfg))
    return tuple(who) if who else None


def set_ocr(photo: Path, text: str) -> None:
    """Von Hand korrigierter Text fürs Foto: ersetzt die Erkennung, alte
    Übersetzungen (vom falsch gelesenen Text) fliegen raus."""
    with _cache_lock:
        cache = _load_cache()
        cache[photo.name] = {"ocr": text, "tr": {}, "lines": []}  # Positionen passen nicht mehr
        _save_cache(cache)


def ocr_text(photo: Path, priority: bool = False) -> str:
    """Erkannter Text im Foto (aus dem Cache, sonst OCR). BLOCKIERT → nur im Thread!"""
    with _cache_lock:
        entry = _load_cache().get(photo.name)
    if entry and "ocr" in entry:
        return entry["ocr"]
    return _run_ocr(photo, priority)["ocr"]


def _run_ocr(photo: Path, priority: bool) -> dict:
    """OCR ausführen, Text + Zeilen mit Position im Cache merken."""
    lines = ocr.read_lines(photo, priority)  # langsam – ohne Lock, damit andere weiterkommen
    text = "\n".join(line["text"] for line in lines)
    with _cache_lock:
        cache = _load_cache()
        entry = cache.setdefault(photo.name, {})
        entry["ocr"], entry["lines"] = text, lines
        _save_cache(cache)
    return entry


def cached_lines(photo: Path) -> list[dict]:
    """Zeilen mit Position aus dem Cache – blockiert NICHT (für das 🪟 VR-Panel)."""
    with _cache_lock:
        return list((_load_cache().get(photo.name) or {}).get("lines") or [])


def ocr_lines(photo: Path, priority: bool = False) -> list[dict]:
    """Zeilen mit Position [{"text", "box"}] – fürs VR-Overlay. BLOCKIERT → nur im Thread!
    Hat man den Text von Hand korrigiert, passen die Positionen nicht mehr → []."""
    with _cache_lock:
        entry = _load_cache().get(photo.name) or {}
    if "lines" in entry:
        return entry["lines"]  # [] = Text von Hand geändert → kein Overlay
    return _run_ocr(photo, priority)["lines"]  # neu oder alter Cache ohne Positionen


def translate_photo(photo: Path, cfg: dict, log=lambda s: None,
                    progress=lambda step, arg="": None, force: bool = False) -> tuple[str, str, str]:
    """Liest den Text im Foto und übersetzt ihn. BLOCKIERT → nur im Thread!
    Gibt (erkannter Text, Übersetzung, benutzter Dienst) zurück;
    ("", "", Dienst) = kein Text im Bild. Der Dienst ist ein anderer als in cfg,
    wenn der gewählte ausgefallen ist und Lingva/Google übernommen hat."""
    method = cfg["tr_method"]
    # "ocr_wait" = die Bild-Erkennung liest gerade ein anderes Foto (max. 1 abwarten)
    progress("ocr_wait" if ocr.busy() else "ocr")
    text = ocr_text(photo, priority=True)  # Vorrang vor der Bild-Erkennung
    if not text and method != L.METHOD_VISION:  # das Bild-LLM liest notfalls selbst
        return "", "", method
    with _cache_lock:
        # force (↻ Nochmal senden): gespeicherte Antwort NICHT nehmen → neu fragen
        translated = None if force else _load_cache().get(photo.name, {}).get("tr", {}).get(_key(cfg))
    if translated is None:
        try:
            info = {}
            translated, method = translate_text_used(text, cfg, log, progress, image=photo, info=info)
        except TranslationError:
            if text:
                raise
            return "", "", method  # auch das Bild-LLM hat keinen Text gefunden
        # unter dem Dienst merken, der es wirklich übersetzt hat (Ersatz wie Lingva → eigener
        # Eintrag; Kontext-/Rätsel-Dienst gehört zu den Einstellungen → normaler Schlüssel)
        planned = {cfg["tr_method"]} | {L.task_method(cfg, m) for m in L.TASK_KEYS}
        used = cfg if method in planned else dict(cfg, tr_method=method, tr_llm_mode=L.MODE_TRANSLATE)
        with _cache_lock:
            cache = _load_cache()
            entry = cache.setdefault(photo.name, {})
            entry.setdefault("tr", {})[_key(used)] = translated
            entry.setdefault("who", {})[_key(used)] = [info.get("method", method),
                                                        info.get("task", L.MODE_TRANSLATE)]
            _save_cache(cache)
    return text, translated, method
