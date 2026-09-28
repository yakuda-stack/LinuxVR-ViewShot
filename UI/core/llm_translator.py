"""
core/llm_translator.py – Übersetzen mit einer KI (LLM) über deren Kommandozeilen-Programm.

Vorlagen (das Programm muss installiert und einmal angemeldet sein):

    Claude Code   claude -p "<prompt>" --model sonnet        (opus / sonnet / haiku)
    Gemini CLI    gemini -m flash -p "<prompt>" --output-format json   (Antwort in "response")
    ChatGPT       codex exec -m gpt-5.6-luna -c model_reasoning_effort=low -   (Prompt über stdin,
                  Antwort per --output-last-message in eine Datei; Codex CLI, ChatGPT-Login)

Dazu "Eigener Befehl" für alles andere (z. B. Ollama):

    ollama run llama3.2 {prompt}

Platzhalter im eigenen Befehl: {prompt} {text} {source} {target} {model}.
Kommt {prompt}/{text} nicht vor, wird der Prompt über stdin übergeben.

Alles BLOCKIERT (die KI braucht ein paar Sekunden) → nur im Hintergrund-Thread!
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

METHOD_CLAUDE = "llm_claude"
METHOD_GEMINI = "llm_gemini"
METHOD_CHATGPT = "llm_chatgpt"
METHOD_LLM_CUSTOM = "llm_custom"

METHODS = [METHOD_CLAUDE, METHOD_GEMINI, METHOD_CHATGPT, METHOD_LLM_CUSTOM]

# Programm, das installiert sein muss (None = eigener Befehl)
BINARIES = {METHOD_CLAUDE: "claude", METHOD_GEMINI: "gemini", METHOD_CHATGPT: "codex"}

# npm-Pakete für den Installier-Knopf (npm install -g --prefix ~/.local …)
NPM_PACKAGES = {METHOD_CLAUDE: "@anthropic-ai/claude-code",
                METHOD_GEMINI: "@google/gemini-cli",
                METHOD_CHATGPT: "@openai/codex"}

# Einmal im Terminal anmelden (danach läuft es ohne Nachfrage)
LOGIN_COMMANDS = {METHOD_CLAUDE: "claude", METHOD_GEMINI: "gemini", METHOD_CHATGPT: "codex login"}

# Dorthin installiert der Knopf – ohne sudo, liegt im Home-Ordner
NPM_PREFIX = Path.home() / ".local"

# Modelle im Dropdown. Neue Modellnamen: "✏ Anderes Modell …" im Dropdown.
MODELS = {
    METHOD_CLAUDE: ["sonnet", "opus", "haiku"],
    # flash / pro / flash-lite = Kurznamen der Gemini CLI, zeigen immer aufs aktuelle Modell
    METHOD_GEMINI: ["flash", "pro", "flash-lite", "gemini-2.5-flash", "gemini-3-flash-preview"],
    # luna = schnell (ideal für kurze Übersetzungen), terra = ausgewogen, sol = am stärksten
    METHOD_CHATGPT: ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"],
}

# Einstellung in ui.json, in der das Modell steht
MODEL_KEYS = {METHOD_CLAUDE: "tr_llm_claude_model", METHOD_GEMINI: "tr_llm_gemini_model",
              METHOD_CHATGPT: "tr_llm_chatgpt_model"}

CUSTOM_EXAMPLE = "ollama run llama3.2 {prompt}"

DEFAULTS = {
    "tr_llm_claude_model": "sonnet",
    "tr_llm_gemini_model": "flash",
    "tr_llm_chatgpt_model": "gpt-5.6-luna",
    "tr_llm_custom_cmd": "",
    "tr_llm_mode": "translate",  # MODE_TRANSLATE (Aufgabe der KI, siehe MODES)
    # "Neu senden, wenn länger als … s" – Gemini hängt manchmal (Anfrage-Limit),
    # ein zweiter Versuch ist dann oft in Sekunden fertig. Standard überall: aus.
    "tr_llm_gemini_retry": False, "tr_llm_gemini_retry_s": 60,
    "tr_llm_claude_retry": False, "tr_llm_claude_retry_s": 60,
    "tr_llm_chatgpt_retry": False, "tr_llm_chatgpt_retry_s": 60,
}

# Einstellungs-Namen für "Neu senden" je Vorlage
RETRY_KEYS = {METHOD_CLAUDE: ("tr_llm_claude_retry", "tr_llm_claude_retry_s"),
              METHOD_GEMINI: ("tr_llm_gemini_retry", "tr_llm_gemini_retry_s"),
              METHOD_CHATGPT: ("tr_llm_chatgpt_retry", "tr_llm_chatgpt_retry_s")}
RETRIES = 2       # so oft neu senden (also max. 3 Versuche), danach Lingva/Google

# Obergrenze, wenn "Neu senden" aus ist – damit nichts ewig hängt
TIMEOUT = 300

# Englische Sprachnamen für den Prompt (KI versteht Namen besser als Codes)
_NAMES = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian",
          "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "ru": "Russian", "uk": "Ukrainian",
          "tr": "Turkish", "ja": "Japanese", "ko": "Korean", "zh": "Chinese (Simplified)",
          "zh-cn": "Chinese (Simplified)"}


class LLMError(Exception):
    pass


def is_llm(method: str) -> bool:
    return method in METHODS


def find_binary(name: str) -> str | None:
    """Programm im PATH suchen – und in ~/.local/bin (dort landet der Installier-Knopf;
    aus dem Startmenü gestartet fehlt der Ordner oft im PATH)."""
    found = shutil.which(name)
    if found:
        return found
    for folder in (NPM_PREFIX / "bin", Path.home() / ".npm-global" / "bin"):
        path = folder / name
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def installed(method: str) -> bool:
    """Ist das Programm für diese Vorlage da?"""
    binary = BINARIES.get(method)
    return binary is not None and find_binary(binary) is not None


# Dateien, die nach der Anmeldung da sind (oder API-Key in der Umgebung)
_LOGIN_FILES = {METHOD_CLAUDE: [".claude/.credentials.json"],
                METHOD_GEMINI: [".gemini/oauth_creds.json"],
                METHOD_CHATGPT: [".codex/auth.json"]}
_LOGIN_ENV = {METHOD_CLAUDE: ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN"],
              METHOD_GEMINI: ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
              METHOD_CHATGPT: ["OPENAI_API_KEY"]}

# Antworten, die keine Übersetzung sind, sondern "bitte anmelden"
_LOGIN_HINTS = ("/login", "invalid api key", "not logged in", "please log in", "please login",
                "codex login", "authentication required", "native binary not installed")


def _gemini_auth_chosen() -> bool:
    """Gemini: Anmeldeart in ~/.gemini/settings.json gewählt (z. B. API-Key, der im
    Schlüsselbund oder in ~/.gemini/.env liegt) – dann gilt es als eingerichtet."""
    gemini = Path.home() / ".gemini"
    try:
        if "GEMINI_API_KEY" in (gemini / ".env").read_text(encoding="utf-8"):
            return True
    except OSError:
        pass
    try:
        text = (gemini / "settings.json").read_text(encoding="utf-8")
    except OSError:
        return False
    return "selectedType" in text or "selectedAuthType" in text


def logged_in(method: str) -> bool | None:
    """True = angemeldet, None = nicht erkennbar (Codex kann im Schlüsselbund speichern)."""
    if any(os.environ.get(var) for var in _LOGIN_ENV.get(method, [])):
        return True
    if any((Path.home() / f).is_file() for f in _LOGIN_FILES.get(method, [])):
        return True
    if method == METHOD_GEMINI and _gemini_auth_chosen():
        return True
    return None if method == METHOD_CHATGPT else False


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _clean(text: str) -> str:
    """Farb-Codes (\\x1b[31m …) aus Programm-Ausgaben entfernen."""
    return _ANSI.sub("", text or "")


def login_argv(method: str) -> list[str] | None:
    """Befehl fürs Terminal zum Anmelden (mit vollem Pfad, falls ~/.local/bin nicht im PATH)."""
    parts = LOGIN_COMMANDS[method].split()
    exe = find_binary(parts[0])
    return [exe] + parts[1:] if exe else None


# Claude Code: offizieller Installer (eigenes Programm nach ~/.local/bin, braucht kein npm).
# Die npm-Version lädt das eigentliche Programm erst in einem Extra-Schritt nach –
# fehlt der, kommt "claude native binary not installed".
CLAUDE_INSTALLER = "curl -fsSL https://claude.ai/install.sh | bash"


def _npm_claude() -> bool:
    """Liegt (noch) die npm-Version von Claude Code in ~/.local?"""
    return (NPM_PREFIX / "lib" / "node_modules" / "@anthropic-ai" / "claude-code").is_dir()


def broken(method: str) -> bool:
    """Programm da, startet aber nicht (z. B. npm-Claude ohne Programm-Datei).
    Prüft nur Installationen aus npm – dauert dann kurz (Programm-Start)."""
    exe = find_binary(BINARIES.get(method, "")) if method in BINARIES else None
    if not exe or "node_modules" not in os.path.realpath(exe):
        return False
    try:
        res = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return True
    return res.returncode != 0


def install_steps(method: str) -> list:
    """Schritte für den Installier-Knopf – jeweils eine Funktion, die den Befehl liefert
    (erst beim Ausführen, weil npm evtl. erst im Schritt davor installiert wird)."""
    if method == METHOD_CLAUDE and shutil.which("curl"):
        steps = []
        if _npm_claude() and shutil.which("npm"):
            # kaputte/alte npm-Version zuerst weg, sonst liegt sie im Weg
            steps.append(lambda: [shutil.which("npm"), "uninstall", "-g", "--prefix",
                                  str(NPM_PREFIX), NPM_PACKAGES[METHOD_CLAUDE]])
        steps.append(lambda: ["bash", "-c", CLAUDE_INSTALLER])
        return steps
    return [lambda: npm_install_command(method)]


def needs_npm(method: str) -> bool:
    return not (method == METHOD_CLAUDE and shutil.which("curl"))


def npm_install_command(method: str) -> list[str] | None:
    """npm-Befehl (ohne sudo, nach ~/.local), oder None ohne npm.
    --include=optional / --ignore-scripts=false: sonst fehlt bei Codex & Co. das
    eigentliche Programm, wenn npm so eingestellt ist, dass es das weglässt."""
    npm = shutil.which("npm")
    if npm is None or method not in NPM_PACKAGES:
        return None
    return [npm, "install", "-g", "--prefix", str(NPM_PREFIX), "--include=optional",
            "--ignore-scripts=false", NPM_PACKAGES[method]]


def manual_install_command(method: str) -> str:
    if method == METHOD_CLAUDE:
        return CLAUDE_INSTALLER
    return f"npm install -g --prefix ~/.local {NPM_PACKAGES[method]}"


def model_of(method: str, cfg: dict) -> str:
    """Eingestelltes Modell; leer (alte Einstellung) → Standard-Modell der Vorlage."""
    key = MODEL_KEYS.get(method)
    if not key:
        return ""
    return (cfg.get(key) or "").strip() or DEFAULTS[key]


# Aufgabe der KI (Dropdown "Aufgabe" auf der Main-Seite)
MODE_TRANSLATE = "translate"   # übersetzen (wie Lingva & Co.)
MODE_EXPLAIN = "explain"       # Kontext: worum geht es, was bedeutet das?
MODE_ANSWER = "answer"         # steht eine Frage/Aufgabe drin → beantworten
MODES = [MODE_TRANSLATE, MODE_EXPLAIN, MODE_ANSWER]
# Bei geändertem Prompt hochzählen → alte gespeicherte Antworten werden neu erfragt
PROMPT_VERSION = {MODE_EXPLAIN: 3, MODE_ANSWER: 3}
# ChatGPT hat bei "Frage beantworten" einen Zusatz (siehe CHATGPT_ANSWER_EXTRA) → eigene Version
PROMPT_VERSION_CHATGPT = {MODE_ANSWER: 4}


def prompt_version(method: str, mode: str):
    """Prompt-Version für den Cache-Schlüssel (ChatGPT kann abweichen)."""
    if method == METHOD_CHATGPT and mode in PROMPT_VERSION_CHATGPT:
        return PROMPT_VERSION_CHATGPT[mode]
    return PROMPT_VERSION.get(mode, "")

_OCR_NOTE = "The text was read from a screenshot by OCR, so ignore obvious OCR mistakes. "
# Die App zeigt reinen Text – Markdown (**fett**, # Titel) würde als Zeichen dastehen
_PLAIN = "Plain text only, no Markdown (no ** or #); simple '- ' lists are fine. "
# Gemini CLI / Claude Code / Codex sind "Agenten": ohne diesen Satz suchen sie evtl.
# im Netz oder lesen Dateien – das kostet Minuten. Die Antwort steht im Text.
_FAST = ("Answer immediately from your own knowledge: do NOT use any tools, do NOT search "
         "the web, do NOT read files, do not think for long. Keep it SHORT – no essay. ")


# "Frage beantworten": oft Quiz-/Rätsel-/Escape-Räume in VRChat. Wichtig ist, WAS man
# anklicken oder eintragen muss – genau so geschrieben wie im Bild, damit man es findet.
ANSWER_PROMPT = (
    "The following text was photographed in a VR game (e.g. VRChat) – often a quiz, "
    "puzzle, riddle or escape room. {ocr}"
    "The lines are in reading order; answer choices / buttons usually come as separate "
    "short lines after the question.\n"
    "What to do:\n"
    "- Multiple choice (buttons, options): say which option is correct. Quote it EXACTLY as "
    "written in the photo (original language and script), so the user can find and click it.\n"
    "- Fill in the blank (○○, __, ??, □, …): say exactly what to enter, in the original "
    "script, and the complete word/phrase.\n"
    "- Riddle, question, math, code: give the solution.\n"
    "- If there is no question or task at all: reply ONLY with the translation into "
    "{tgt} (no ➜, no comment).\n"
    "Answer format (only when there is a question/task):\n"
    "First line: '➜ ' followed ONLY by what to click / enter / the answer "
    "(original script, then its meaning in {tgt} in brackets).\n"
    "Then ONE short line in {tgt}: why (e.g. the full phrase and what it means). "
    "Nothing else – no introduction, no translation of the whole text. {plain}{fast}"
)

# Nur ChatGPT: nannte bei Lücke + Buttons nur das fehlende Zeichen ("下" statt "下暗し")
CHATGPT_ANSWER_EXTRA = (
    "\nImportant: if there is a blank AND answer buttons, the answer is the button to click – "
    "quote the WHOLE button text exactly, never only the missing characters or the first "
    "letters. Example: '灯台○○' with buttons '足元暗し', '下暗し' → '➜ 下暗し', not '➜ 下'."
)


def make_prompt(text: str, source: str, target: str, mode: str = MODE_TRANSLATE,
                method: str = "") -> str:
    tgt = _NAMES.get((target or "").lower(), target)
    src = _NAMES.get((source or "").lower(), source) if source else ""
    frm = f"from {src} " if src else ""
    if mode == MODE_EXPLAIN:
        return ("The following text was photographed in a VR game (e.g. VRChat). "
                + _OCR_NOTE +
                f"Explain in {tgt} in at most 4 short lines what it is about and what it means: "
                "context, important terms, what the user can do. No introduction. "
                + _PLAIN + _FAST
                + f"\n\nText from the photo:\n<<<\n{text}\n>>>")
    if mode == MODE_ANSWER:
        # Text klar abgrenzen – sonst hält die KI kurze Texte evtl. für Teil der Anweisung
        extra = CHATGPT_ANSWER_EXTRA if method == METHOD_CHATGPT else ""
        return (ANSWER_PROMPT.format(tgt=tgt, ocr=_OCR_NOTE, plain=_PLAIN, fast=_FAST) + extra
                + f"\n\nText from the photo:\n<<<\n{text}\n>>>")
    return (f"Translate the following text {frm}into {tgt}. "
            "The text was read from a screenshot by OCR, so fix obvious OCR mistakes. "
            "Keep the line breaks. Reply with the translation ONLY – "
            "no explanations, no quotes, no notes. " + _FAST + "\n\n"
            f"{text}")


def build_command(method: str, cfg: dict, prompt: str, text: str, source: str,
                  target: str, stream: bool = False) -> tuple[list[str], str | None]:
    """(argv, stdin) für die gewählte Vorlage.
    stream=True: Ausgabe als JSON-Ereignisse, damit die Antwort schon beim Schreiben
    angezeigt werden kann (siehe _Stream)."""
    model = model_of(method, cfg)
    if method == METHOD_CLAUDE:
        argv = ["claude", "-p", prompt]
        if model:
            argv += ["--model", model]
        if stream:
            argv += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        return argv, None
    if method == METHOD_GEMINI:
        argv = ["gemini"]
        if model:
            argv += ["-m", model]
        # JSON: sonst können Status-/Statistik-Zeilen mit in der Ausgabe landen
        return argv + ["-p", prompt, "--output-format", "stream-json" if stream else "json"], None
    if method == METHOD_CHATGPT:
        argv = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                "-c", "model_reasoning_effort=low"]  # Übersetzen braucht kein langes Nachdenken
        if model:
            argv += ["-m", model]
        if stream:
            argv += ["--json"]  # Ereignisse als JSON-Zeilen
        return argv + ["-"], prompt  # "-" = Prompt kommt über stdin
    # eigener Befehl
    cmd = (cfg.get("tr_llm_custom_cmd") or "").strip()
    if not cmd:
        raise LLMError("kein Befehl eingetragen")
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        raise LLMError(f"Befehl nicht lesbar ({e})")
    values = {"{prompt}": prompt, "{text}": text, "{source}": source or "auto",
              "{target}": target, "{model}": model}
    uses_input = any("{prompt}" in p or "{text}" in p for p in parts)
    argv = []
    for part in parts:
        for ph, value in values.items():
            part = part.replace(ph, value)
        argv.append(part)
    return argv, None if uses_input else prompt


def _gemini_response(output: str) -> str:
    """--output-format json → {"response": "...", "stats": …, "error": …}"""
    start = output.find("{")  # evtl. Hinweiszeilen vor dem JSON überspringen
    try:
        data = json.loads(output[start:]) if start >= 0 else None
    except ValueError:
        return output  # alte CLI ohne JSON → Text so nehmen
    if not isinstance(data, dict):
        return output
    if data.get("error") and not data.get("response"):
        err = data["error"]
        raise LLMError("gemini: " + str(err.get("message") if isinstance(err, dict) else err))
    return (data.get("response") or "").strip()


def _run(argv, stdin, timeout, cwd, env) -> subprocess.CompletedProcess:
    """Wie subprocess.run – aber bei Zeitüberschreitung wird die GANZE Prozessgruppe
    beendet. Gemini/Codex starten Unterprozesse; die würden sonst weiterlaufen und
    das Neu-Senden blockieren."""
    import signal
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", cwd=cwd, env=env,
                            start_new_session=True)
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


class _Stream:
    """Liest die Ausgabe der KI Stück für Stück und meldet den bisherigen Text
    über on_partial(text) – so sieht man die Antwort schon, während sie entsteht.

    Claude:  {"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": …}}}
             … am Ende {"type": "result", "result": "…", "is_error": false}
    Gemini:  {"type": "message", "role": "assistant", "content": "…", "delta": true}
             … bei Fehler {"type": "result", "status": "error", "error": {"message": …}}
    ChatGPT: {"type": "item.completed", "item": {"type": "agent_message", "text": …}}
             (Codex liefert die Antwort meist erst am Stück)
    eigener Befehl: normaler Text (z. B. ollama run schreibt Wort für Wort)"""

    EVERY = 0.15  # höchstens so oft an die UI melden (Sekunden)

    def __init__(self, method: str, on_partial):
        self.method = method
        self.on_partial = on_partial
        self.buf = ""        # angefangene JSON-Zeile
        self.text = ""       # bisherige Antwort
        self.result = None   # Endergebnis (Claude "result")
        self.error = ""      # Fehler aus dem Stream
        self.saw_json = False
        self._last = 0.0

    def feed(self, chunk: str):
        if self.method == METHOD_LLM_CUSTOM:
            self.text += chunk
            self._emit()
            return
        self.buf += chunk
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self._line(line)

    def _line(self, line: str):
        line = line.strip()
        if not line.startswith("{"):
            return  # Hinweiszeilen (z. B. "Loaded cached credentials.")
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        self.saw_json = True
        kind = ev.get("type")
        if self.method == METHOD_CLAUDE:
            if kind == "stream_event":
                delta = (ev.get("event") or {}).get("delta") or {}
                if delta.get("type") == "text_delta":
                    self.text += delta.get("text", "")
                    self._emit()
            elif kind == "assistant" and not self.text:  # ältere CLI ohne Häppchen
                content = (ev.get("message") or {}).get("content") or []
                parts = [c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text"]
                if parts:
                    self.text = "".join(parts)
                    self._emit()
            elif kind == "result":
                if ev.get("is_error"):
                    self.error = str(ev.get("result") or ev.get("subtype") or "Fehler")
                elif isinstance(ev.get("result"), str):
                    self.result = ev["result"]
        elif self.method == METHOD_GEMINI:
            if kind == "message" and ev.get("role") == "assistant":
                content = ev.get("content") or ""
                self.text = self.text + content if ev.get("delta") else content
                self._emit()
            elif kind == "result" and ev.get("status") == "error":
                err = ev.get("error") or {}
                self.error = str(err.get("message") if isinstance(err, dict) else err)
        elif self.method == METHOD_CHATGPT:
            item = ev.get("item") or {}
            if kind in ("item.updated", "item.completed") and item.get("type") == "agent_message":
                self.text = item.get("text") or self.text
                self._emit()

    def _emit(self, force: bool = False):
        now = time.monotonic()
        if force or now - self._last >= self.EVERY:
            self._last = now
            self.on_partial(_clean(self.text).strip())

    def finish(self) -> str:
        """Rest verarbeiten, letzten Stand melden, Endergebnis zurückgeben."""
        if self.buf:
            self._line(self.buf)
            self.buf = ""
        if self.text:
            self._emit(force=True)
        return self.result if self.result is not None else self.text


def _run_stream(argv, stdin, timeout, cwd, env, on_chunk) -> subprocess.CompletedProcess:
    """Wie _run, gibt stdout aber schon WÄHREND des Laufs an on_chunk(text) weiter."""
    import codecs
    import signal
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env,
                            start_new_session=True)
    out, err = [], []

    def read_out():
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            data = os.read(proc.stdout.fileno(), 4096)
            text = dec.decode(data, final=not data)
            if text:
                out.append(text)
                on_chunk(text)
            if not data:
                break

    def read_err():
        err.append(proc.stderr.read().decode("utf-8", errors="replace"))

    def write_in():
        try:
            proc.stdin.write(stdin.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass  # Programm hat stdin nicht gelesen

    threads = [threading.Thread(target=read_out, daemon=True),
               threading.Thread(target=read_err, daemon=True)]
    if stdin is not None:
        threads.append(threading.Thread(target=write_in, daemon=True))
    for th in threads:
        th.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # ganze Gruppe (Unterprozesse!)
        except OSError:
            proc.kill()
        proc.wait()
        for th in threads:
            th.join(timeout=2)
        raise subprocess.TimeoutExpired(argv, timeout, output="".join(out), stderr="".join(err))
    for th in threads:
        th.join(timeout=5)
    return subprocess.CompletedProcess(argv, proc.returncode, "".join(out), "".join(err))


def retry_settings(method: str, cfg: dict) -> tuple[bool, int]:
    """(Neu senden an?, nach wie vielen Sekunden)."""
    keys = RETRY_KEYS.get(method)
    if not keys:
        return False, TIMEOUT
    on = cfg.get(keys[0], DEFAULTS[keys[0]])
    try:
        secs = max(1, int(cfg.get(keys[1]) or DEFAULTS[keys[1]]))
    except (TypeError, ValueError):
        secs = DEFAULTS[keys[1]]
    return bool(on), secs


def translate(method: str, cfg: dict, text: str, source: str, target: str,
              on_retry=lambda attempt: None, on_partial=None) -> str:
    """Übersetzt mit der KI. Wirft LLMError mit lesbarem Grund.
    on_retry(Versuch) wird vor jedem erneuten Senden aufgerufen (für die Statuszeile).
    on_partial(bisheriger Text): Antwort schon beim Schreiben zeigen (None = am Stück wie früher)."""
    prompt = make_prompt(text, source, target, cfg.get("tr_llm_mode") or MODE_TRANSLATE, method)
    streaming = on_partial is not None
    argv, stdin = build_command(method, cfg, prompt, text, source, target, stream=streaming)
    exe = find_binary(argv[0])
    if not exe:
        raise LLMError(f"Programm nicht gefunden: {argv[0]}")
    argv = [exe] + argv[1:]
    # in einem leeren Ordner starten → die KI sieht keine Projektdateien
    with tempfile.TemporaryDirectory(prefix="viewshot-llm-") as tmp:
        last_msg = None
        if method == METHOD_CHATGPT:
            # Codex schreibt Fortschritt mit auf stdout – die letzte Antwort
            # sauber in eine Datei schreiben lassen
            last_msg = Path(tmp) / "answer.txt"
            argv = argv[:2] + ["--output-last-message", str(last_msg)] + argv[2:]
        # Gemini startet ohne Terminal nur in "vertrauenswürdigen" Ordnern (Fehler 55).
        # Unser leerer Temp-Ordner ist harmlos → per Umgebungsvariable erlauben.
        env = dict(os.environ, GEMINI_CLI_TRUST_WORKSPACE="true", NO_COLOR="1")
        retry, secs = retry_settings(method, cfg)
        timeout = secs if retry else TIMEOUT
        attempts = 1 + RETRIES if retry else 1
        res = None
        stream = None
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                on_retry(attempt)  # hängt → abbrechen und nochmal senden
            try:
                if streaming:
                    stream = _Stream(method, on_partial)  # jeder Versuch fängt leer an
                    res = _run_stream(argv, stdin, timeout, tmp, env, stream.feed)
                else:
                    res = _run(argv, stdin, timeout, tmp, env)
                break
            except FileNotFoundError:
                raise LLMError(f"Programm nicht gefunden: {argv[0]}")
            except subprocess.TimeoutExpired as e:
                last = e
        if res is None:
            # Grund aus der bisherigen Ausgabe holen (z. B. 429 = Anfrage-Limit erreicht)
            partial = _clean(str(last.stderr or "") + str(last.stdout or "")).lower()
            hint = ""
            if any(k in partial for k in ("429", "quota", "rate limit", "resource_exhausted",
                                          "too many requests")):
                hint = " – Anfrage-Limit erreicht, kurz warten oder anderes Modell"
            tries = f" ({attempts} Versuche)" if attempts > 1 else ""
            raise LLMError(f"{Path(argv[0]).name} hat länger als {timeout} s gebraucht"
                           f"{tries}{hint}")
        streamed = stream.finish() if stream is not None else ""
        if stream is not None and stream.error and not streamed:
            raise LLMError(f"{Path(argv[0]).name}: {_clean(stream.error).strip()[:200]}")
        if res.returncode != 0:
            err = _clean(res.stderr or res.stdout or "").strip().splitlines()
            raise LLMError(f"{Path(argv[0]).name} beendet mit Fehler {res.returncode}"
                           + (f": {err[-1]}" if err else ""))
        out = ""
        if last_msg is not None and last_msg.is_file():
            out = last_msg.read_text(encoding="utf-8", errors="replace")
        if not out and stream is not None and (stream.saw_json or method == METHOD_LLM_CUSTOM):
            out = streamed
        out = _clean(out or res.stdout or "").strip()
        if method == METHOD_GEMINI and not (stream is not None and stream.saw_json):
            out = _gemini_response(out)
    if not out:
        raise LLMError(f"{Path(argv[0]).name} hat nichts geantwortet")
    low = out.lower()
    if len(out) < 300 and any(hint in low for hint in _LOGIN_HINTS):
        # z. B. claude: "Invalid API key · Please run /login" – keine Übersetzung!
        raise LLMError(f"{Path(argv[0]).name}: nicht angemeldet – Optionen → Übersetzung → "
                       f"Anmelden ({out.splitlines()[0][:120]})")
    return out
