"""
core/vision.py – 🖼 Lokales Bild-LLM (VLM) über Ollama.

Anders als die anderen KI-Dienste bekommt das Bild-LLM das FOTO mit – es sieht
schräge Schrift, Layout und Knöpfe und kann Fehler der Texterkennung (OCR)
ausbessern oder Text lesen, den die OCR gar nicht gefunden hat.
Läuft komplett auf dem eigenen PC (keine Daten ins Internet).

Ollama:  https://ollama.com  ·  Arch: pacman -S ollama-cuda (NVIDIA) / ollama-rocm (AMD)
         systemctl enable --now ollama   ·   ollama pull qwen2.5vl:7b
Die App spricht nur über HTTP (localhost:11434) mit Ollama – Grafikkarte egal.

Übersetzen: Die OCR-Zeilen gehen nummeriert mit, die Antwort kommt Zeile für Zeile
zurück → das 🥽 VR-Overlay kann jede Übersetzung über ihre Zeile legen.
"""

import base64
import json
import re
import time
from pathlib import Path
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"
# Vorschläge im Dropdown (installierte Bild-Modelle kommen automatisch dazu)
SUGGESTED = ["qwen2.5vl:7b", "qwen2.5vl:3b", "gemma3:4b", "gemma3:12b", "llama3.2-vision"]
# Wie lange Ollama das Modell nach der letzten Anfrage im Grafikspeicher behält.
# Kurz = VR hat den Speicher schnell wieder, lang = nächste Anfrage schneller.
KEEP_ALIVE = ["30s", "2m", "10m", "-1"]  # -1 = immer
NO_TEXT = "NO_TEXT"
MAX_IMAGE = 1600  # längere Seite fürs Bild-LLM (größer bringt nichts, kostet nur Zeit)
# Namen typischer Bild-Modelle (falls Ollama zu alt ist, um "capabilities" zu melden)
_VISION_HINTS = ("vl", "vision", "llava", "gemma3", "minicpm-v", "moondream", "bakllava", "pixtral")


# ---------------------------------------------------------------- Installieren
# Arch/CachyOS: Paket passend zur Grafikkarte (bleibt über pacman -Syu aktuell).
# Andere Distros: das offizielle Skript von ollama.com (erkennt die Karte selbst).
ARCH_PACKAGES = {"nvidia": "ollama-cuda", "amd": "ollama-rocm", "": "ollama"}
OFFICIAL_SCRIPT = "curl -fsSL https://ollama.com/install.sh | sh"
_VENDORS = {"0x10de": "nvidia", "0x1002": "amd"}


def gpu_vendor(drm: Path = Path("/sys/class/drm")) -> str:
    """"nvidia" / "amd" / "" (keine passende Karte). Zwei Karten (z. B. AMD-Onboard +
    NVIDIA): NVIDIA gewinnt – die Onboard-Grafik ist fürs LLM zu schwach."""
    found = set()
    for vendor in drm.glob("card*/device/vendor"):
        try:
            found.add(_VENDORS.get(vendor.read_text().strip().lower(), ""))
        except OSError:
            pass
    return "nvidia" if "nvidia" in found else "amd" if "amd" in found else ""


def install_script(os_release: str | None = None, vendor: str | None = None) -> str:
    """Shell-Befehl, der Ollama installiert und startet (läuft im Terminal – sudo fragt dort)."""
    from core import pkginstall
    vendor = gpu_vendor() if vendor is None else vendor
    ids = pkginstall.distro_ids(os_release)
    if any(i.startswith(n) for i in ids for n in ("arch", "cachyos", "endeavouros", "manjaro")):
        return (f"sudo pacman -S --needed {ARCH_PACKAGES.get(vendor, 'ollama')} && "
                f"sudo systemctl enable --now ollama")
    return OFFICIAL_SCRIPT  # richtet den Dienst selbst ein


def url_of(cfg: dict) -> str:
    return ((cfg.get("tr_vision_url") or "").strip() or DEFAULT_URL).rstrip("/")


def _request(url: str, path: str, payload: dict | None = None, timeout: float = 5):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url + path, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 – nur localhost/eigene URL


def running(url: str = DEFAULT_URL, timeout: float = 0.5) -> bool:
    """Antwortet Ollama?"""
    try:
        with _request(url, "/api/version", timeout=timeout) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


_models_cache: dict[str, tuple[float, list[str]]] = {}


def vision_models(url: str = DEFAULT_URL, timeout: float = 0.8) -> list[str]:
    """Installierte Modelle, die Bilder verstehen ([] = Ollama läuft nicht)."""
    hit = _models_cache.get(url)
    if hit and time.monotonic() - hit[0] < 20:
        return hit[1]
    found = []
    try:
        with _request(url, "/api/tags", timeout=timeout) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
        for name in names:
            try:
                with _request(url, "/api/show", {"model": name}, timeout=timeout) as r:
                    caps = json.load(r).get("capabilities")
            except (OSError, ValueError):
                caps = None
            if caps is not None:
                if "vision" in caps:
                    found.append(name)
            elif any(h in name.lower() for h in _VISION_HINTS):
                found.append(name)
    except (OSError, ValueError):
        found = []
    _models_cache[url] = (time.monotonic(), found)
    return found


def model_list(url: str = DEFAULT_URL) -> list[str]:
    """Fürs Dropdown: installierte Bild-Modelle zuerst, dann Vorschläge."""
    installed = vision_models(url)
    return installed + [m for m in SUGGESTED if m not in installed]


def image_b64(path) -> str:
    """Foto als Base64 – große Bilder vorher verkleinern."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QImage
    img = QImage(str(path))
    if img.isNull():
        raise OSError(f"Bild nicht lesbar: {path}")
    if max(img.width(), img.height()) > MAX_IMAGE:
        img = img.scaled(MAX_IMAGE, MAX_IMAGE, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return base64.b64encode(bytes(data)).decode("ascii")


def build_prompt(text: str, source: str, target: str, mode: str, has_image: bool) -> str:
    """Prompt fürs Bild-LLM. Übersetzen: nummerierte OCR-Zeilen → genauso viele Zeilen zurück."""
    from core import llm_translator as L
    tgt = L._NAMES.get((target or "").lower(), target)
    ocr = text.strip() or "(nothing found – read the text from the image yourself)"
    where = "the image and the OCR text" if has_image else "the OCR text"
    # Kleine lokale Modelle: KURZE Prompts, klare Ja/Nein-Entscheidung, Zielsprache am Ende
    # (die langen Prompts für Claude & Co. überfordern z. B. qwen2.5vl:7b – es antwortete
    # dann in der Sprache des Textes, statt zu übersetzen)
    if mode == L.MODE_ANSWER:  # nur nach „JA, ist ein Quiz“ (classify_prompt)
        numbered = L.numbered_lines(ocr)
        # „Erst nachdenken, dann antworten“: kleine Modelle raten sonst oft die erste Option.
        # Zuerst das Sprichwort/Wissen VOLLSTÄNDIG hinschreiben, dann erst die Nummer wählen.
        return (f"This is a quiz, riddle or task from a VR game. Look at {where}. The numbered lines "
                f"are the question and the answer options – the player sees the SAME numbers.\n"
                f"<<<\n{numbered}\n>>>\n\n"
                f"Think first, then answer. Do NOT just pick the first option.\n"
                f"Line 1: 💡 what is asked – e.g. write the complete proverb/idiom/fact it refers to "
                f"and what it means, in {tgt}.\n"
                f"Line 2: ➜ <number>) <the option that fits line 1, exactly as written> "
                f"(<its meaning in {tgt}>)\n"
                f"Reply with exactly these two lines.")
    if mode != L.MODE_TRANSLATE:  # Kontext erklären
        return (f"Look at {where}. Explain in {tgt}, in at most 4 short lines, what it is about "
                f"and what it means for the player. No introduction.\n\n"
                f"OCR text:\n<<<\n{ocr}\n>>>\n\nReply in {tgt}.")
    lines = [t for t in text.splitlines() if t.strip()]
    intro = ("The attached image is a photo taken in a VR game (e.g. VRChat). " if has_image else "")
    if not lines:
        return (intro + f"Read ALL text in the image and translate it into {tgt}. One output line per "
                f"text line, top to bottom. Reply with the translations only. If there is no text at "
                f"all, reply exactly: {NO_TEXT}")
    numbered = "\n".join(f"{i}) {t}" for i, t in enumerate(lines, 1))
    return (intro + f"OCR read these {len(lines)} lines from it (they may contain OCR mistakes – "
            + ("use the image to correct them" if has_image else "fix obvious mistakes") + "):\n"
            f"{numbered}\n\n"
            f"Translate each line into {tgt}. Reply with EXACTLY {len(lines)} lines in the same "
            f"order – only the translations, no numbers, no quotes, no explanations. "
            f"If a line is already in {tgt} or is a name, repeat it unchanged.")


def classify_prompt(text: str, has_image: bool) -> str:
    """Schritt 1 bei „Frage beantworten“: nur JA/NEIN – das schafft auch ein kleines Modell."""
    where = "the image and the OCR text" if has_image else "the OCR text"
    ocr = text.strip() or "(nothing found – look at the image)"
    return (f"Look at {where}. Is there a question, quiz, riddle, fill-in-the-blank or task that the "
            f"player has to solve (for example with answer buttons)? Normal text, signs, stories and "
            f"dialogue are NO.\n\nOCR text:\n<<<\n{ocr}\n>>>\n\nReply with exactly one word: YES or NO.")


def task_prompt(text: str, has_image: bool) -> str:
    """🤖 Auto: welche Aufgabe passt zu diesem Foto? Antwort: ein Wort (siehe parse_task)."""
    where = "the image and the OCR text" if has_image else "the text"
    ocr = text.strip() or "(nothing found – look at the image)"
    return (f"Look at {where} from a VR game. What does the player need?\n"
            f"QUIZ = there is a question, quiz, riddle, fill-in-the-blank or task to solve "
            f"(for example with answer buttons).\n"
            f"EXPLAIN = a joke, meme, pun, wordplay or cultural reference that a plain translation "
            f"would not make understandable.\n"
            f"TEXT = everything else (signs, menus, dialogue, stories, rules) – just translate.\n\n"
            f"Text:\n<<<\n{ocr}\n>>>\n\nReply with exactly one word: QUIZ, EXPLAIN or TEXT.")


def parse_task(verdict: str) -> str:
    """Antwort von task_prompt → Aufgabe (im Zweifel übersetzen)."""
    from core import llm_translator as L
    v = verdict.upper()
    if "QUIZ" in v:
        return L.MODE_ANSWER
    if "EXPLAIN" in v:
        return L.MODE_EXPLAIN
    return L.MODE_TRANSLATE


def classify(cfg: dict, text: str, image=None, timeout: float = 60) -> str:
    """🤖 Auto mit dem lokalen Bild-LLM: kurze Ein-Wort-Frage → Aufgabe."""
    from core import llm_translator as L
    model = L.model_of(L.METHOD_VISION, cfg)
    payload = {"model": model, "system": system_prompt(cfg.get("tr_target", "")),
               "keep_alive": cfg.get("tr_vision_keep_alive") or "2m",
               "prompt": task_prompt(text, image is not None), "stream": False,
               "options": {"temperature": 0.0, "num_predict": 4}}
    if image is not None:
        payload["images"] = [image_b64(image)]
    return parse_task(_generate(url_of(cfg), model, payload, None, timeout))


def system_prompt(target: str) -> str:
    from core import llm_translator as L
    tgt = L._NAMES.get((target or "").lower(), target)
    return (f"You help a player inside a VR game (e.g. VRChat). ALWAYS write your reply in {tgt}. "
            f"Only quote text in its original language when it is a button or option the player "
            f"has to click. Plain text, no Markdown, short.")


_NUMBER = re.compile(r"^\s*\d{1,3}\s*[).:\]-]\s*")


def clean_answer(out: str, mode: str) -> str:
    from core import llm_translator as L
    out = out.strip()
    if out == NO_TEXT or out.upper().startswith(NO_TEXT):
        return ""
    # „YES“ / „NO“ als erste Zeile (Modell hat die Entscheidung mit ausgegeben) → weg
    first, _, rest = out.partition("\n")
    if first.strip().strip(".:!").upper() in ("YES", "NO", "JA", "NEIN") and rest.strip():
        out = rest.strip()
    if mode == L.MODE_TRANSLATE:
        # Manche Modelle nummerieren trotzdem ("1) Hallo") → weg damit
        out = "\n".join(_NUMBER.sub("", line) for line in out.splitlines())
    return out.strip()


def translate(cfg: dict, text: str, source: str, target: str, image=None, on_partial=None,
              timeout: float = 300) -> str:
    """Anfrage an Ollama (Streaming). Wirft LLMError mit lesbarem Grund.
    „Frage beantworten“: erst JA/NEIN (Quiz?), dann Quiz-Prompt mit Nummern oder normal übersetzen –
    zwei kleine Aufgaben schafft ein 7B-Modell viel besser als eine große."""
    from core import llm_translator as L
    mode = cfg.get("tr_llm_mode") or L.MODE_TRANSLATE
    url = url_of(cfg)
    model = L.model_of(L.METHOD_VISION, cfg)
    base = {
        "model": model,
        # Systemanweisung – kleine Modelle halten sich daran stärker als an den Prompt
        "system": system_prompt(target),
        "keep_alive": cfg.get("tr_vision_keep_alive") or "2m",
        "options": {"temperature": 0.2},
    }
    if image is not None:
        base["images"] = [image_b64(image)]
    # „Frage beantworten“ von Hand gewählt: erst „Quiz?“ (bei 🤖 Auto schon entschieden)
    if mode == L.MODE_ANSWER and not cfg.get("_routed") and not is_quiz(cfg, text, image, timeout):
        mode = L.MODE_TRANSLATE  # kein Quiz → einfach Zeile für Zeile übersetzen
    payload = dict(base, prompt=build_prompt(text, source, target, mode, image is not None), stream=True)
    out = _generate(url, model, payload, lambda s: on_partial(clean_answer(s, mode) or s.strip())
                    if on_partial is not None else None, timeout)
    result = clean_answer(out, mode)
    if on_partial is not None and result:
        on_partial(result)
    return result


def is_quiz(cfg: dict, text: str, image=None, timeout: float = 60) -> bool:
    """Schritt 1 bei „Frage beantworten“: Ist das ein Quiz? (kurze JA/NEIN-Frage ans lokale Modell)"""
    from core import llm_translator as L
    model = L.model_of(L.METHOD_VISION, cfg)
    payload = {"model": model, "system": system_prompt(cfg.get("tr_target", "")),
               "keep_alive": cfg.get("tr_vision_keep_alive") or "2m",
               "prompt": classify_prompt(text, image is not None), "stream": False,
               "options": {"temperature": 0.0, "num_predict": 4}}
    if image is not None:
        payload["images"] = [image_b64(image)]
    verdict = _generate(url_of(cfg), model, payload, None, timeout).upper()
    return "YES" in verdict or "JA" in verdict


def _generate(url: str, model: str, payload: dict, on_partial, timeout: float) -> str:
    """Eine Anfrage an /api/generate – gestreamt oder am Stück. Gibt den Rohtext zurück."""
    from core import llm_translator as L
    out, last = "", 0.0
    try:
        with _request(url, "/api/generate", payload, timeout=timeout) as r:
            for raw in r:
                if not raw.strip():
                    continue
                try:
                    ev = json.loads(raw)
                except ValueError:
                    continue
                if ev.get("error"):
                    raise L.LLMError(f"Ollama: {ev['error']}")
                out += ev.get("response", "")
                now = time.monotonic()
                if on_partial is not None and now - last >= 0.15:
                    last = now
                    on_partial(out)
                if ev.get("done"):
                    break
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if e.code == 404 or "not found" in body.lower():
            raise L.LLMError(f"Ollama: Modell „{model}“ fehlt – Optionen → Übersetzung → "
                             f"📥 Modell laden (ollama pull {model})") from None
        raise L.LLMError(f"Ollama: HTTP {e.code} {body[:160]}") from None
    except urllib.error.URLError as e:
        raise L.LLMError(f"Ollama nicht erreichbar ({url}) – läuft es? "
                         f"systemctl enable --now ollama ({e.reason})") from None
    except TimeoutError:
        raise L.LLMError(f"Ollama hat länger als {int(timeout)} s gebraucht") from None
    return out
