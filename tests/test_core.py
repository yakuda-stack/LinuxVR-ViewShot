"""Schnelle Tests für die UI-Logik (ohne Fenster). Start: python3 -m pytest -q"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- Texte
def test_every_text_has_de_and_en():
    from core.i18n import TEXTS
    missing = [k for k, v in TEXTS.items() if not (v.get("de") and v.get("en"))]
    assert not missing, f"ohne de/en: {missing}"


def test_used_text_keys_exist():
    """Jeder tr("…")-Schlüssel im Code steht auch in i18n.py."""
    from core.i18n import TEXTS
    used = set()
    for py in (ROOT / "UI").rglob("*.py"):
        # nur ganze Schlüssel – tr("combo_" + c) wird erst zur Laufzeit zusammengesetzt
        used |= set(re.findall(r'\btr\("([a-z0-9_]+)"\s*[,)]', py.read_text(encoding="utf-8")))
    assert not used - set(TEXTS), f"fehlen in i18n.py: {sorted(used - set(TEXTS))}"


# ------------------------------------------------------ Namensschilder
@pytest.mark.parametrize("lines, expected", [
    (["dkw_cat", "Mýstico_o", "Minoric", "he/him", "lease to Drop"], False),
    (["xX_Fox_Xx", "she / they", "Trusted User", "[NOVA] Club Nova", "Mystic Fox"], False),
    (["Please do not touch", "the artwork"], True),
    (["このワールドへようこそ", "ルールを守ってください"], True),
    (["さくら", "猫丸"], False),
])
def test_nameplates_are_not_text(lines, expected):
    from core.tags import has_real_text
    assert has_real_text(lines) is expected


# --------------------------------------------------------- layer.json
def test_shutter_and_mode_button_never_equal(tmp_path, monkeypatch):
    from core import layer_config
    monkeypatch.setattr(layer_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(layer_config, "LAYER_FILE", tmp_path / "layer.json")
    cfg = layer_config.update("shutter", "left")   # Standard-Typ-Taste ist links
    assert cfg["shutter"] == "left" and cfg["mode_button"] != "left"
    cfg = layer_config.update("mode_button", "left")
    assert cfg["mode_button"] == "left" and cfg["shutter"] != "left"


def _rust_value(src: str):
    """Rust-Standardwert aus config.rs → Python-Wert wie in layer.json.
    7.0 → 7.0 · vec!["wayvr".into()] → ["wayvr"] · IconPosition::BottomLeft → "bottom_left" """
    src = src.strip()
    if src in ("true", "false"):
        return src == "true"
    if src.startswith("vec!["):
        return re.findall(r'"([^"]*)"', src)
    if re.fullmatch(r"-?\d+(\.\d+)?", src):
        return float(src)
    enum = re.fullmatch(r"\w+::(\w+)", src)
    if enum:  # CamelCase → snake_case (wie serde rename_all)
        return re.sub(r"(?<!^)(?=[A-Z])", "_", enum.group(1)).lower()
    raise AssertionError(f"unbekannter Rust-Wert: {src}")


def test_layer_defaults_match_rust():
    """layer_config.py und layer/src/config.rs müssen dieselben Namen + Standardwerte haben –
    sonst liest der Layer eine Einstellung nicht oder startet mit einem anderen Wert."""
    from core import layer_config
    rs = (ROOT / "layer/src/config.rs").read_text(encoding="utf-8")
    body = re.search(r"impl Default for LayerConfig \{.*?Self \{(.*?)\n\s*\}", rs, re.S).group(1)
    rust = {k: _rust_value(v) for k, v in re.findall(r"^\s*(\w+):\s*(.+?),\s*$", body, re.M)}
    struct = re.search(r"pub struct LayerConfig \{(.*?)\n\}", rs, re.S).group(1)
    fields = re.findall(r"pub (\w+):", struct)
    # Zahlen als float vergleichen (Python 7 == Rust 7.0)
    python = {k: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
              for k, v in layer_config.DEFAULTS.items()}
    assert sorted(fields) == sorted(rust), "impl Default in config.rs vergisst ein Feld"
    assert python == rust


def test_layer_choices_match_rust_enums():
    """Auswahl-Listen in Python = Varianten der Rust-Enums."""
    from core import layer_config
    rs = (ROOT / "layer/src/config.rs").read_text(encoding="utf-8")

    def variants(name):
        body = re.search(rf"pub enum {name} \{{(.*?)\}}", rs, re.S).group(1)
        return tuple(_rust_value("X::" + v) for v in re.findall(r"(\w+),", body))

    assert variants("Combo") == layer_config.COMBOS
    assert set(variants("IconPosition")) == set(layer_config.ICON_POSITIONS)


# ------------------------------------------------------- WayVR-Knopf
def test_chat_button_is_replaced():
    from core import wayvr_theme
    xml = ('<div>\n<Button macro="button_style" _press="::OscSend /chatbox/input" _arg0="">\n'
           '  <sprite src="watch/chat.svg" />\n</Button>\n</div>')
    new, n = wayvr_theme.CHAT_BUTTON.subn(wayvr_theme.viewshot_button(Path("/x/open.sh")), xml)
    assert n == 1 and "::ShellExec '/x/open.sh'" in new and "OscSend" not in new


# ----------------------------------------------------------- Version
def test_version_everywhere_the_same():
    from core.version import VERSION
    cargo = (ROOT / "layer/Cargo.toml").read_text(encoding="utf-8")
    assert re.search(r'^version\s*=\s*"([^"]+)"', cargo, re.M).group(1) == VERSION
    pkgbuild = (ROOT / "packaging/aur/PKGBUILD").read_text(encoding="utf-8")
    assert re.search(r"^pkgver=(\S+)", pkgbuild, re.M).group(1) == VERSION.replace("-", "_")


# ------------------------------------------------------ KI-Übersetzer
def test_llm_custom_command_placeholders():
    from core import llm_translator as L
    cfg = {"tr_llm_custom_cmd": "tool --to {target} {prompt}"}
    argv, stdin = L.build_command(L.METHOD_LLM_CUSTOM, cfg, "PROMPT", "t", "", "de")
    assert argv == ["tool", "--to", "de", "PROMPT"] and stdin is None
    cfg = {"tr_llm_custom_cmd": "ollama run llama3.2"}
    argv, stdin = L.build_command(L.METHOD_LLM_CUSTOM, cfg, "PROMPT", "t", "", "de")
    assert stdin == "PROMPT"  # ohne {prompt} → über stdin


def test_llm_claude_model_flag():
    from core import llm_translator as L
    argv, _ = L.build_command(L.METHOD_CLAUDE, {"tr_llm_claude_model": "opus"}, "P", "t", "", "de")
    assert argv == ["claude", "-p", "P", "--model", "opus"]


def test_main_dropdown_only_configured(monkeypatch):
    from core import llm_translator as L, translation
    from core.config import DEFAULTS
    monkeypatch.setattr(L, "installed", lambda m: False)
    monkeypatch.setattr(translation.T, "libretranslate_installed", lambda: False)
    cfg = dict(DEFAULTS)
    assert translation.configured_methods(cfg) == ["lingva", "google"]
    cfg["tr_deepl_key"] = "abc"
    assert "deepl" in translation.configured_methods(cfg)
    cfg["tr_method"] = "llm_gemini"  # gewählt = immer dabei
    assert "llm_gemini" in translation.configured_methods(cfg)


def test_main_dropdown_favorites(monkeypatch):
    from core import llm_translator as L, translation
    from core.config import DEFAULTS
    monkeypatch.setattr(L, "installed", lambda m: False)
    monkeypatch.setattr(translation.T, "libretranslate_installed", lambda: False)
    cfg = dict(DEFAULTS, tr_deepl_key="abc")
    assert translation.menu_methods(cfg) == ["lingva", "google", "deepl"]  # nichts favorisiert
    cfg["tr_favorites"] = ["deepl"]
    assert translation.menu_methods(cfg) == ["lingva", "deepl"]  # lingva = gerade gewählt
    cfg["tr_method"] = "deepl"
    assert translation.menu_methods(cfg) == ["deepl"]
    cfg["tr_favorites"] = ["llm_gemini"]  # Favorit nicht eingerichtet → wie bisher
    assert translation.menu_methods(cfg) == ["lingva", "google", "deepl"]


# ------------------------------------------------------ Zwischenablage
def test_clipboard_finds_other_wayland_displays(tmp_path, monkeypatch):
    import socket
    from core import clipboard
    for name in ("wayland-0", "wayland-1"):
        s = socket.socket(socket.AF_UNIX)
        s.bind(str(tmp_path / name))
    (tmp_path / "wayland-0.lock").touch()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")  # App läuft in WayVR
    assert clipboard.other_displays() == ["wayland-0"]


# ------------------------------------------------------ Paket per Knopf
@pytest.mark.parametrize("os_release, expected", [
    ('ID=arch\n', "sudo pacman -S wl-clipboard"),
    ('ID=cachyos\nID_LIKE="arch"\n', "sudo pacman -S wl-clipboard"),
    ('ID=fedora\n', "sudo dnf install wl-clipboard"),
    ('ID=nobara\nID_LIKE="rhel centos fedora"\n', "sudo dnf install wl-clipboard"),
    ('ID=ubuntu\nID_LIKE=debian\n', "sudo apt install wl-clipboard"),
    ('ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n', "sudo zypper install wl-clipboard"),
])
def test_manual_install_command(os_release, expected):
    from core import pkginstall
    assert pkginstall.manual_command("wl-clipboard", os_release) == expected


def test_install_command_uses_pkexec(monkeypatch):
    from core import pkginstall
    monkeypatch.setattr(pkginstall.shutil, "which", lambda b: f"/usr/bin/{b}")
    monkeypatch.setattr(pkginstall.Path, "exists", lambda self: False)
    cmd = pkginstall.install_command("wl-clipboard", "ID=fedora\n")
    assert cmd == ["pkexec", "/usr/bin/dnf", "install", "-y", "wl-clipboard"]


def test_fallback_reports_used_service(monkeypatch):
    from core import translation
    from core.config import DEFAULTS
    tried = []

    def fake_try(method, text, cfg, progress=None):
        tried.append(method)
        return (None, "kaputt") if method == "llm_claude" else ("Hallo", "")

    monkeypatch.setattr(translation, "_try", fake_try)
    cfg = dict(DEFAULTS, tr_method="llm_claude")
    assert translation.translate_text_used("Hello", cfg) == ("Hallo", "lingva")
    assert tried == ["llm_claude", "lingva"]


def test_gemini_json_answer():
    from core import llm_translator as L
    out = 'Loaded cached credentials.\n{"response": "Hallo Welt", "stats": {}}'
    assert L._gemini_response(out) == "Hallo Welt"
    assert L._gemini_response("nur Text") == "nur Text"


def test_codex_prompt_via_stdin(tmp_path, monkeypatch):
    """Falsches codex: schreibt stdin in die --output-last-message-Datei."""
    from core import llm_translator as L
    fake = tmp_path / "codex"
    fake.write_text('#!/bin/sh\nwhile [ "$1" != "--output-last-message" ]; do shift; done\n'
                    'cat > "$2"\necho "progress noise"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    argv, stdin = L.build_command(L.METHOD_CHATGPT, {"tr_llm_chatgpt_model": "gpt-5.6-luna"},
                                  "P", "t", "", "de")
    assert argv[-1] == "-" and stdin == "P" and "gpt-5.6-luna" in argv
    out = L.translate(L.METHOD_CHATGPT, {"tr_llm_chatgpt_model": "gpt-5.6-luna"}, "Hi", "", "de")
    assert "Translate the following text into German" in out and "progress" not in out


def test_terminal_command(monkeypatch):
    from core import terminal
    monkeypatch.setattr(terminal.shutil, "which", lambda n: "/usr/bin/konsole" if n == "konsole" else None)
    cmd = terminal.command(["/home/x/.local/bin/claude"], "Enter")
    assert cmd[:4] == ["konsole", "-e", "bash", "-c"] and cmd[4].startswith("/home/x/.local/bin/claude;")


def test_logged_in_detects_credentials(tmp_path, monkeypatch):
    from core import llm_translator as L
    monkeypatch.setattr(L.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert L.logged_in(L.METHOD_GEMINI) is False
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}")
    assert L.logged_in(L.METHOD_GEMINI) is True


def test_broken_npm_claude_is_detected(tmp_path, monkeypatch):
    """npm-Claude ohne Programm-Datei ("native binary not installed") → Neu installieren."""
    from core import llm_translator as L
    pkg = tmp_path / "lib" / "node_modules" / "@anthropic-ai" / "claude-code"
    pkg.mkdir(parents=True)
    shim = pkg / "cli.sh"
    shim.write_text("#!/bin/sh\necho 'Error: claude native binary not installed.' >&2\nexit 1\n")
    shim.chmod(0o755)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "claude").symlink_to(shim)
    monkeypatch.setattr(L, "NPM_PREFIX", tmp_path)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert L.installed(L.METHOD_CLAUDE) and L.broken(L.METHOD_CLAUDE)
    monkeypatch.setattr(L.shutil, "which", lambda n: f"/usr/bin/{n}")
    steps = [s() for s in L.install_steps(L.METHOD_CLAUDE)]
    assert steps[0][1] == "uninstall" and steps[-1] == ["bash", "-c", L.CLAUDE_INSTALLER]


def test_ai_task_changes_prompt_and_cache_key():
    from core import llm_translator as L, translation
    from core.config import DEFAULTS
    answer = L.make_prompt("Q?", "", "de", L.MODE_ANSWER)
    assert "EXACTLY as" in answer and "<<<\nQ?\n>>>" in answer
    assert "Explain" in L.make_prompt("x", "", "de", L.MODE_EXPLAIN)
    cfg = dict(DEFAULTS, tr_method="llm_claude")
    plain = translation._key(cfg)
    assert translation._key(dict(cfg, tr_llm_mode="answer")) != plain
    # bei Lingva spielt die Aufgabe keine Rolle
    assert translation._key(dict(cfg, tr_method="lingva", tr_llm_mode="answer")) == \
        translation._key(dict(cfg, tr_method="lingva"))


def test_ocr_translation_has_priority_over_background(monkeypatch):
    """Beim Start erkennt der Hintergrund alle Fotos – die Übersetzung darf
    trotzdem nicht bis zum Ende warten müssen."""
    import threading
    import time
    from core import ocr

    class SlowEngine:
        def __call__(self, path):
            time.sleep(0.05)
            return type("R", (), {"txts": [path]})()

    monkeypatch.setattr(ocr, "_engine", SlowEngine())
    stop = threading.Event()

    def background():
        while not stop.is_set():
            ocr.read_text("bg")

    workers = [threading.Thread(target=background, daemon=True) for _ in range(2)]
    for w in workers:
        w.start()
    time.sleep(0.2)
    start = time.monotonic()
    assert ocr.read_text("main", priority=True) == "main"
    waited = time.monotonic() - start
    stop.set()
    for w in workers:
        w.join(timeout=2)
    assert waited < 0.5  # höchstens das laufende Foto abwarten


def test_gemini_api_key_login_is_detected(tmp_path, monkeypatch):
    from core import llm_translator as L
    monkeypatch.setattr(L.Path, "home", lambda: tmp_path)
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "settings.json").write_text(
        '{"security": {"auth": {"selectedType": "gemini-api-key"}}}')
    assert L.logged_in(L.METHOD_GEMINI) is True


def test_gemini_runs_in_trusted_mode(tmp_path, monkeypatch):
    """Ohne GEMINI_CLI_TRUST_WORKSPACE bricht Gemini mit Fehler 55 ab."""
    from core import llm_translator as L
    fake = tmp_path / "gemini"
    fake.write_text('#!/bin/sh\n[ "$GEMINI_CLI_TRUST_WORKSPACE" = true ] || '
                    '{ printf "\\033[31mnot trusted\\033[0m" >&2; exit 55; }\n'
                    'echo \'{"response": "Hallo"}\'\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    assert L.translate(L.METHOD_GEMINI, {}, "Hello", "", "de") == "Hallo"


def test_llm_timeout_names_rate_limit(tmp_path, monkeypatch):
    from core import llm_translator as L
    fake = tmp_path / "gemini"
    fake.write_text('#!/bin/sh\necho "Attempt 1 failed with status 429" >&2\nsleep 5\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setattr(L, "RETRIES", 1)
    tries = []
    cfg = {"tr_llm_gemini_retry": True, "tr_llm_gemini_retry_s": 1}
    with pytest.raises(L.LLMError, match="Anfrage-Limit"):
        L.translate(L.METHOD_GEMINI, cfg, "Hello", "", "de", on_retry=tries.append)
    assert tries == [2]  # einmal neu gesendet


def test_llm_retry_second_attempt_wins(tmp_path, monkeypatch):
    """Erster Versuch hängt, zweiter antwortet sofort → Antwort vom zweiten."""
    from core import llm_translator as L
    flag = tmp_path / "second"
    fake = tmp_path / "gemini"
    fake.write_text("#!/bin/sh\n"
                    f"if [ -e {flag} ]; then echo '{{\"response\": \"Hallo\"}}'; "
                    f"else touch {flag}; sleep 5; fi\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    cfg = {"tr_llm_gemini_retry": True, "tr_llm_gemini_retry_s": 1}
    assert L.translate(L.METHOD_GEMINI, cfg, "Hello", "", "de") == "Hallo"
    # Claude: Standard aus
    assert L.retry_settings(L.METHOD_CLAUDE, {})[0] is False


def test_history_add_and_limit(tmp_path, monkeypatch):
    from core import history
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(history, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(history, "MAX_ENTRIES", 3)
    assert history.add("a.png", "Hi", "Hallo", "lingva")
    assert history.add("a.png", "Hi", "Hallo", "lingva") is None  # doppelt → nichts
    for i in range(5):
        history.add(f"{i}.png", "x", f"t{i}", "google")
    entries = history.load()
    assert len(entries) == 3 and entries[0]["tr"] == "t4"  # neueste zuerst
    history.add("x.png", "a", "b", "g")
    history.add("y.png", "c", "d", "g")
    assert history.add("x.png", "a", "b", "g") is None  # schon drin (nicht nur ganz oben)
    history.clear()
    assert history.load() == []


def test_corrected_ocr_replaces_old_translations(tmp_path, monkeypatch):
    from core import translation
    monkeypatch.setattr(translation, "CACHE_FILE", tmp_path / "translations.json")
    monkeypatch.setattr(translation, "CONFIG_DIR", tmp_path)
    photo = tmp_path / "p.png"
    translation.set_ocr(photo, "Helo wrld")
    assert translation.ocr_text(photo) == "Helo wrld"
    translation.set_ocr(photo, "Hello world")
    assert translation.ocr_text(photo) == "Hello world"


def test_privacy_note_for_every_service():
    """Jeder Dienst hat einen ☁/🔒-Hinweis; lokales LibreTranslate verschickt nichts."""
    from core import translation
    for m in translation.METHODS:
        text = translation.privacy_text(m)
        assert text and not text.startswith("privacy_") and "{" not in text, m
    assert translation.privacy("libre") == "local"
    assert translation.privacy("llm_chatgpt") == "cloud"


# ------------------------------------------------ KI-Antwort live (Stream)
@pytest.mark.parametrize("method, script, expected", [
    ("llm_claude",
     'echo \'{"type":"system","subtype":"init"}\'\n'
     'echo \'{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Hal"}}}\'\n'
     'sleep 0.3\n'
     'echo \'{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"lo Welt"}}}\'\n'
     'echo \'{"type":"result","subtype":"success","is_error":false,"result":"Hallo Welt"}\'\n',
     "Hallo Welt"),
    ("llm_gemini",
     'echo "Loaded cached credentials."\n'
     'echo \'{"type":"init","session_id":"x"}\'\n'
     'echo \'{"type":"message","role":"user","content":"prompt"}\'\n'
     'echo \'{"type":"message","role":"assistant","content":"Hal","delta":true}\'\n'
     'sleep 0.3\n'
     'echo \'{"type":"message","role":"assistant","content":"lo Welt","delta":true}\'\n'
     'echo \'{"type":"result","status":"success"}\'\n',
     "Hallo Welt"),
    ("llm_custom", 'printf "Hal"; sleep 0.3; printf "lo Welt"\n', "Hallo Welt"),
])
def test_llm_streams_partial_answer(tmp_path, monkeypatch, method, script, expected):
    """Falsche KI-Programme schreiben die Antwort in Häppchen → on_partial sieht Zwischenstände,
    das Endergebnis ist die ganze Antwort."""
    from core import llm_translator as L
    name = {"llm_claude": "claude", "llm_gemini": "gemini", "llm_custom": "fakellm"}[method]
    fake = tmp_path / name
    fake.write_text("#!/bin/sh\n" + script)
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setattr(L._Stream, "EVERY", 0)
    seen = []
    cfg = {"tr_llm_custom_cmd": "fakellm {prompt}"}
    assert L.translate(method, cfg, "Hello", "", "de", on_partial=seen.append) == expected
    assert "Hal" in seen and seen[-1] == expected


def test_llm_stream_error_is_reported(tmp_path, monkeypatch):
    from core import llm_translator as L
    fake = tmp_path / "gemini"
    fake.write_text('#!/bin/sh\necho \'{"type":"result","status":"error","error":{"message":"Quota exceeded"}}\'\nexit 1\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    with pytest.raises(L.LLMError, match="Quota exceeded"):
        L.translate(L.METHOD_GEMINI, {}, "Hello", "", "de", on_partial=lambda s: None)


def test_llm_stream_flags():
    from core import llm_translator as L
    argv, _ = L.build_command(L.METHOD_CLAUDE, {}, "P", "t", "", "de", stream=True)
    assert "stream-json" in argv and "--include-partial-messages" in argv
    argv, _ = L.build_command(L.METHOD_GEMINI, {}, "P", "t", "", "de", stream=True)
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    argv, stdin = L.build_command(L.METHOD_CHATGPT, {}, "P", "t", "", "de", stream=True)
    assert "--json" in argv and argv[-1] == "-" and stdin == "P"
    # ohne Stream wie bisher
    assert "stream-json" not in L.build_command(L.METHOD_CLAUDE, {}, "P", "t", "", "de")[0]
