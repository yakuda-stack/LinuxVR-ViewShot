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
    text = re.fullmatch(r'"([^"]*)"(?:\.into\(\)|\.to_string\(\))?', src)
    if text:  # "#5b8dc9".into() → "#5b8dc9"
        return text.group(1)
    if re.fullmatch(r"-?\d+(\.\d+)?", src):
        return float(src)
    enum = re.fullmatch(r"(?:\w+::)+(\w+)", src)  # auch crate::panel::Anchor::Left
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
    assert variants("DaemonMode") == layer_config.DAEMON_MODES
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
    for crate in ("layer", "daemon"):
        cargo = (ROOT / crate / "Cargo.toml").read_text(encoding="utf-8")
        assert re.search(r'^version\s*=\s*"([^"]+)"', cargo, re.M).group(1) == VERSION, crate
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

    def fake_try(method, text, cfg, progress=None, image=None):
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


# --------------------------------------------------- VR-Overlay (Bild)
def test_ocr_lines_get_bounding_boxes():
    from core import ocr
    lines = ocr.to_lines(["Hallo", " ", "Welt"],
                         [[[10, 5], [50, 6], [50, 20], [10, 19]], [[0, 0]] * 4, [[3, 30], [40, 30], [41, 45], [2, 44]]])
    assert lines == [{"text": "Hallo", "box": [10, 5, 50, 20]}, {"text": "Welt", "box": [2, 30, 41, 45]}]
    assert ocr.to_lines(["x"], None) == [{"text": "x", "box": None}]


def test_overlay_pairs_lines_or_one_block():
    from core import overlay
    lines = [{"text": "a", "box": [0, 0, 10, 5]}, {"text": "b", "box": [0, 10, 20, 15]}]
    assert overlay.pair_lines(lines, "A\nB") == [([0, 0, 10, 5], "A"), ([0, 10, 20, 15], "B")]
    assert overlay.pair_lines(lines, "nur eine Zeile") is None       # → ein großes Kästchen
    assert overlay.union_box(lines, (100, 50)) == [0, 0, 20, 15]
    assert overlay.union_box([{"text": "x", "box": None}], (100, 50)) == [0, 0, 100, 50]


def test_overlay_image_is_transparent_with_boxes(tmp_path, monkeypatch):
    from PyQt6.QtGui import QGuiApplication, QImage
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 – Schrift braucht eine App
    from core import overlay
    monkeypatch.setattr(overlay, "overlay_file", lambda: tmp_path / "overlay" / "overlay.png")
    lines = [{"text": "Welcome", "box": [20, 20, 300, 60]}]
    path = overlay.write("ViewShot_1.png", (2000, 400), lines, "Willkommen")
    img = QImage(str(path))
    assert (img.width(), img.height()) == (1024, 205)              # verkleinert, Seitenverhältnis bleibt
    assert img.text("ViewShot-For") == "ViewShot_1.png"
    assert img.pixelColor(1000, 200).alpha() == 0                   # außerhalb: durchsichtig
    assert img.pixelColor(12, 20).alpha() > 150                     # im Kästchen: grau
    assert not (tmp_path / "overlay" / ".overlay.png.part").exists()


# ------------------------------------------- 🖼 lokales Bild-LLM (Ollama)
@pytest.fixture
def fake_ollama():
    """Mini-Ollama auf einem freien Port: /api/version, /api/tags, /api/show, /api/generate."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/version":
                self._json({"version": "0.99"})
            elif self.path == "/api/tags":
                self._json({"models": [{"name": "qwen2.5vl:7b"}, {"name": "llama3.2:3b"}]})

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                caps = ["completion", "vision"] if "vl" in req["model"] else ["completion"]
                return self._json({"capabilities": caps})
            seen.update(req)
            seen.setdefault("all", []).append(req)
            if not req.get("stream", True):  # Schritt 1 bei „Frage beantworten“: JA/NEIN
                return self._json({"response": seen.get("verdict", "NO"), "done": True})
            if req["model"] == "fehlt":
                return self._json({"error": "model 'fehlt' not found"}, 404)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for part in ["1) Willkommen", " im Hotel\n2) Bitte nicht", " anfassen"]:
                self.wfile.write((json.dumps({"response": part, "done": False}) + "\n").encode())
                self.wfile.flush()
            self.wfile.write((json.dumps({"response": "", "done": True}) + "\n").encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_vision_lists_only_image_models(fake_ollama):
    from core import vision
    url, _ = fake_ollama
    assert vision.running(url)
    assert vision.vision_models(url) == ["qwen2.5vl:7b"]
    assert vision.model_list(url)[0] == "qwen2.5vl:7b"
    assert not vision.running("http://127.0.0.1:9")  # nichts da → False, kein Hängen


def test_vision_translates_line_by_line_with_photo(fake_ollama, tmp_path):
    from PyQt6.QtGui import QColor, QImage
    from core import llm_translator as L
    url, seen = fake_ollama
    photo = tmp_path / "p.png"
    img = QImage(40, 20, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    img.save(str(photo))
    cfg = {"tr_vision_url": url, "tr_llm_vision_model": "qwen2.5vl:7b"}
    parts = []
    out = L.translate(L.METHOD_VISION, cfg, "Welcome to the hotel\nPlease do not touch", "", "de",
                      on_partial=parts.append, image=photo)
    assert out == "Willkommen im Hotel\nBitte nicht anfassen"      # Nummern entfernt
    assert parts and parts[-1] == out
    assert seen["images"] and seen["stream"] is True and seen["keep_alive"] == "2m"
    assert "1) Welcome to the hotel" in seen["prompt"] and "EXACTLY 2 lines" in seen["prompt"]


def test_vision_errors_are_readable(fake_ollama):
    from core import llm_translator as L
    url, _ = fake_ollama
    with pytest.raises(L.LLMError, match="fehlt"):
        L.translate(L.METHOD_VISION, {"tr_vision_url": url, "tr_llm_vision_model": "fehlt"}, "x", "", "de")
    with pytest.raises(L.LLMError, match="nicht erreichbar"):
        L.translate(L.METHOD_VISION, {"tr_vision_url": "http://127.0.0.1:9"}, "x", "", "de")


def test_vision_reads_text_ocr_missed(tmp_path, monkeypatch):
    """OCR findet nichts → nur das Bild-LLM darf ran (liest selbst); NO_TEXT → kein Text."""
    from core import translation
    from core.config import DEFAULTS
    monkeypatch.setattr(translation, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(translation, "ocr_text", lambda photo, priority=False: "")
    calls = []

    def fake_try(method, text, cfg, progress=None, image=None):
        calls.append((method, text, image))
        return ("Ausgang", "") if method == "llm_vision" else (None, "nein")

    monkeypatch.setattr(translation, "_try", fake_try)
    photo = tmp_path / "x.png"
    cfg = dict(DEFAULTS, tr_method="llm_vision")
    assert translation.translate_photo(photo, cfg) == ("", "Ausgang", "llm_vision")
    assert calls == [("llm_vision", "", photo)]          # Lingva/Google ohne Text gar nicht erst
    # anderer Dienst ohne Text → wie bisher: nichts
    assert translation.translate_photo(photo, dict(DEFAULTS, tr_method="lingva")) == ("", "", "lingva")
    from core import vision
    assert vision.clean_answer("NO_TEXT", "translate") == ""


@pytest.mark.parametrize("cards, expected", [
    ({"card0": "0x1002"}, "amd"),                       # z. B. RX 9070 XT
    ({"card0": "0x1002", "card1": "0x10de"}, "nvidia"),  # AMD-Onboard + NVIDIA → NVIDIA
    ({"card0": "0x8086"}, ""),                          # nur Intel
    ({}, ""),
])
def test_gpu_vendor(tmp_path, cards, expected):
    from core import vision
    for card, vendor in cards.items():
        (tmp_path / card / "device").mkdir(parents=True)
        (tmp_path / card / "device" / "vendor").write_text(vendor + "\n")
    assert vision.gpu_vendor(tmp_path) == expected


@pytest.mark.parametrize("os_release, vendor, expected", [
    ('ID=cachyos\nID_LIKE="arch"\n', "amd", "sudo pacman -S --needed ollama-rocm && sudo systemctl enable --now ollama"),
    ("ID=arch\n", "nvidia", "sudo pacman -S --needed ollama-cuda && sudo systemctl enable --now ollama"),
    ("ID=arch\n", "", "sudo pacman -S --needed ollama && sudo systemctl enable --now ollama"),
    ("ID=fedora\n", "amd", "curl -fsSL https://ollama.com/install.sh | sh"),
])
def test_ollama_install_script(os_release, vendor, expected):
    from core import vision
    assert vision.install_script(os_release, vendor) == expected


def test_vision_answer_prompt_uses_numbers():
    """Quiz-Prompt fürs Bild-LLM: nummerierte Zeilen, Antwort mit Nummer, Zielsprache."""
    from core import llm_translator as L, translation, vision
    from core.config import DEFAULTS
    p = vision.build_prompt("覆水○○\n元に返らず\n盆に返らず", "", "de", L.MODE_ANSWER, True)
    assert "1) 覆水○○" in p and "3) 盆に返らず" in p and "➜ <number>)" in p and "German" in p
    assert "YES or NO" in vision.classify_prompt("x", True)
    assert "ALWAYS write your reply in German" in vision.system_prompt("de")
    assert vision.clean_answer("YES\n➜ 3) 盆に返らず (…)", "answer") == "➜ 3) 盆に返らず (…)"
    # eigene Cache-Version → alte (falsche) Antworten werden neu gefragt
    key = translation._key(dict(DEFAULTS, tr_method="llm_vision", tr_llm_mode=L.MODE_ANSWER))
    assert "#answer4" in key
    assert p.index("💡") < p.index("➜ <number>)")  # erst nachdenken, dann Nummer


@pytest.mark.parametrize("verdict, used, mode", [("TEXT", "llm_vision", "translate"),
                                                  ("QUIZ", "llm_claude", "answer"),
                                                  ("EXPLAIN", "llm_gemini", "explain")])
def test_auto_main_ai_hands_tasks_to_their_service(fake_ollama, monkeypatch, verdict, used, mode):
    """🤖 Auto: Bild-LLM (Haupt) entscheidet je Foto – übersetzt selbst, Quiz → Claude, Kontext → Gemini.
    Der Haupt-Dienst bleibt dabei, wie er ist."""
    from core import llm_translator as L, translation
    from core.config import DEFAULTS
    url, seen = fake_ollama
    seen["verdict"] = verdict
    asked = {}
    real_try = translation._try

    def fake_try(method, text, cfg, progress=lambda *a: None, image=None):
        if method != L.METHOD_VISION:
            asked.update(method=method, model=L.model_of(method, cfg), mode=cfg["tr_llm_mode"])
            return "cloud", ""
        return real_try(method, text, cfg, progress, image)

    monkeypatch.setattr(translation, "_try", fake_try)
    monkeypatch.setattr(translation, "is_configured", lambda m, cfg: True)
    cfg = dict(DEFAULTS, tr_method="llm_vision", tr_vision_url=url, tr_llm_mode=L.MODE_AUTO,
               tr_answer_method="llm_claude", tr_llm_claude_model="opus",
               tr_explain_method="llm_gemini", tr_target="de")
    out, method = translation.translate_text_used("Q?\nA\nB", cfg)
    assert method == used and cfg["tr_method"] == "llm_vision"
    first = seen["all"][0]
    assert first["stream"] is False and "QUIZ, EXPLAIN or TEXT" in first["prompt"]
    if used == "llm_vision":  # normaler Text → Bild-LLM übersetzt selbst (keine 2. Ja/Nein-Frage)
        assert not asked and "EXACTLY 3 lines" in seen["all"][-1]["prompt"] and len(seen["all"]) == 2
    else:
        assert out == "cloud" and asked["method"] == used and asked["mode"] == mode
    if used == "llm_claude":
        assert asked["model"] == "opus"  # Modell = das bei Claude eingestellte
    key = translation._key(cfg)
    assert "#auto" in key and "answer=llm_claude@opus" in key and "explain=llm_gemini" in key


def test_auto_hand_choice_counts_for_this_and_next_photo():
    """🤖 Auto, Aufgabe von Hand umgestellt → aktuelles + nächstes Foto, dann wieder Auto.
    Ohne KI als Main gibt es nur Manuell."""
    from core import translation
    from core.config import DEFAULTS
    cfg = dict(DEFAULTS, tr_method="llm_vision", tr_route="auto", tr_llm_mode="translate",
               tr_auto_once="explain", tr_auto_once_photo="a.png", tr_auto_once_next="")
    mode = lambda name: translation.photo_task_cfg(cfg, name)[0]["tr_llm_mode"]  # noqa: E731
    assert mode("a.png") == "explain" and mode("b.png") == "explain"  # dieses + nächstes
    assert mode("a.png") == "explain"                                 # zurückblättern: gilt noch
    assert mode("c.png") == "auto" and cfg["tr_auto_once"] == ""      # danach wieder Auto
    manual = dict(cfg, tr_route="manual", tr_llm_mode="answer")
    assert translation.task_cfg(manual)["tr_llm_mode"] == "answer"
    libre = dict(cfg, tr_method="libre", tr_llm_mode="auto")          # alter Wert → übersetzen
    assert translation.route_mode(libre) == "manual"
    assert translation.task_cfg(libre)["tr_llm_mode"] == "translate"


def test_switching_to_manual_starts_with_translate():
    """Main → LibreTranslate (= ✋ Manuell) oder Modus → Manuell: Aufgabe „Übersetzen“,
    sonst hinge z. B. „Kontext“ von früher dran und Claude würde gefragt."""
    from core import translation
    from core.config import DEFAULTS
    cfg = dict(DEFAULTS, tr_method="llm_vision", tr_route="auto", tr_llm_mode="explain")
    translation.set_main(cfg, "libre")
    assert cfg["tr_llm_mode"] == "translate" and cfg["tr_route"] == "auto"  # Wunsch bleibt gemerkt
    cfg = dict(DEFAULTS, tr_method="llm_vision", tr_route="auto", tr_llm_mode="answer")
    translation.set_route(cfg, "manual")
    assert cfg["tr_llm_mode"] == "translate"
    cfg["tr_llm_mode"] = "answer"  # in Manuell selbst gewählt → Main-Wechsel ändert nichts
    translation.set_main(cfg, "libre")
    assert cfg["tr_llm_mode"] == "answer"


def test_last_ai_is_remembered_per_photo(tmp_path, monkeypatch):
    """„Letzte KI“: wer die gespeicherte Antwort geschrieben hat (auch beim Zurückblättern)."""
    from core import translation
    from core.config import DEFAULTS
    monkeypatch.setattr(translation, "CACHE_FILE", tmp_path / "translations.json")
    monkeypatch.setattr(translation, "ocr_text", lambda photo, priority=False: "Q?\nA\nB")

    def fake(text, cfg, log, progress, image=None, info=None):
        info.update(method="llm_claude", task="answer")
        return "➜ 2) A", "llm_claude"

    monkeypatch.setattr(translation, "translate_text_used", fake)
    cfg = dict(DEFAULTS, tr_method="llm_vision", tr_route="auto", tr_llm_mode="auto",
               tr_answer_method="llm_claude")
    photo = tmp_path / "a.png"
    translation.translate_photo(photo, cfg)
    assert translation.last_ai(photo, cfg) == ("llm_claude", "answer")
    assert translation.last_ai(tmp_path / "b.png", cfg) is None


def test_manual_task_uses_fixed_service(monkeypatch):
    """Aufgabe von Hand: fester Dienst je Aufgabe – auch wenn der Haupt-Dienst LibreTranslate ist."""
    from core import llm_translator as L, translation
    from core.config import DEFAULTS
    monkeypatch.setattr(translation, "is_configured", lambda m, cfg: True)
    cfg = dict(DEFAULTS, tr_method="libre", tr_answer_method="llm_claude", tr_target="de")
    assert translation.route(dict(cfg, tr_llm_mode="answer"), "x")["tr_method"] == "llm_claude"
    r = translation.route(dict(cfg, tr_llm_mode="explain"), "x")  # kein Kontext-Dienst → übersetzen
    assert (r["tr_method"], r["tr_llm_mode"]) == ("libre", "translate")
    assert L.has_tasks(cfg) and not L.has_tasks(dict(cfg, tr_answer_method=""))
    # Auto ohne KI als Haupt-Dienst: einfache Regel
    auto = dict(cfg, tr_llm_mode="auto")
    assert translation.route(auto, "Welches Tier?\nHund\nKatze")["tr_method"] == "llm_claude"
    assert translation.route(auto, "Willkommen\nim Hotel")["tr_method"] == "libre"
    assert "#answer4=llm_claude@" in translation._key(dict(cfg, tr_llm_mode="answer"))


def test_cloud_answer_prompt_is_numbered():
    from core import llm_translator as L
    p = L.make_prompt("Welche Farbe?\nRot\nBlau", "", "de", L.MODE_ANSWER)
    assert "1) Welche Farbe?\n2) Rot\n3) Blau" in p and "option number" in p


# ------------------------------------------------ 🪟 VR-Panel
def test_panel_numbers_match_photo_lines():
    from ui import vr_panel
    lines = [{"text": "Dog", "box": [0, 0, 5, 5]}, {"text": "Eagle", "box": [0, 9, 5, 14]}]
    assert vr_panel.numbered(lines, "Hund\nAdler") == "①  Hund\n②  Adler"
    assert vr_panel.numbered(lines, "➜ Eagle (Adler)") == "➜ Eagle (Adler)"  # KI-Antwort: so lassen
    assert vr_panel.number(25) == "(26)"


def test_panel_click_from_vr_presses_button(tmp_path, monkeypatch):
    """Klick wie vom Layer (u/v per UDP) → echter Klick auf den Knopf im unsichtbaren Fenster."""
    import os
    monkeypatch.setenv("VIEWSHOT_OUTPUT_DIR", str(tmp_path))
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from core import layer_config
    monkeypatch.setattr(layer_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(layer_config, "LAYER_FILE", tmp_path / "layer.json")
    from ui.mainwindow import MainWindow
    w = MainWindow()
    pw = w.main_page.vr_panel
    pw.refresh(force=True)
    pw.toggle_sheet()          # ⚙ Einstellungen (klappt auf)
    pw.slide.clear()
    c = pw.move_btn.mapTo(pw, pw.move_btn.rect().center())
    pw.click(c.x() / pw.width(), c.y() / pw.height())
    assert layer_config.load()["panel_edit"] is True
    b = pw.shutter_btns["left"]  # Auslöser links → Typ-Taste weicht aus
    c = b.mapTo(pw, b.rect().center())
    pw.click(c.x() / pw.width(), c.y() / pw.height())
    fresh = layer_config.load()
    assert fresh["shutter"] == "left" and fresh["mode_button"] != "left"
    assert (tmp_path / "panel" / "panel.png").exists()
    os.environ.pop("VIEWSHOT_OUTPUT_DIR", None)


def test_panel_gallery_nav_months_and_photo_view(tmp_path, monkeypatch):
    """◀ ▶ unten wechseln Übersetzung ↔ Galerie (je eigene Größe) · Monats-Trenner ·
    weiterer Ordner mit Unterordnern · Kachel → Foto groß · 🗑 zweimal · 📋 · 🌐."""
    import json
    import os
    import time
    photos = tmp_path / "photos"
    photos.mkdir()
    vrc = tmp_path / "VRChat" / "2026-06"
    vrc.mkdir(parents=True)
    monkeypatch.setenv("VIEWSHOT_OUTPUT_DIR", str(photos))
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841

    def make(path, when):
        img = QImage(64, 48, QImage.Format.Format_RGB32)
        img.fill(QColor(90, 90, 160))
        img.save(str(path))
        os.utime(path, (when, when))

    october = time.mktime((2026, 10, 1, 12, 0, 0, 0, 0, -1))
    june = time.mktime((2026, 6, 10, 12, 0, 0, 0, 0, -1))
    for i in range(6):
        make(photos / f"ViewShot_{i:02d}.png", october + i)
    for i in range(15):
        make(vrc / f"VRChat_{i:02d}.png", june + i)
    from core import clipboard, layer_config, paths
    monkeypatch.setattr(layer_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(layer_config, "LAYER_FILE", tmp_path / "layer.json")
    from ui import vr_panel as V
    monkeypatch.setattr(V, "pose_file", lambda: tmp_path / "panel_pose.json")
    monkeypatch.setattr(V, "sizes_file", lambda: tmp_path / "panel_sizes.json")
    (tmp_path / "panel_pose.json").write_text(json.dumps({"anchor": "left", "width": 0.32}))
    from ui.pages import gallery_page
    trashed, copied = [], []
    monkeypatch.setattr(gallery_page, "move_to_trash", lambda p: (trashed.append(p.name), p.unlink(), True)[2])
    monkeypatch.setattr(clipboard, "set_image", lambda p: copied.append(p.name))
    from ui.mainwindow import MainWindow
    win = MainWindow()
    win.cfg["gallery_folders"] = [{"path": str(vrc.parent), "subfolders": True}]
    paths.forget_scan()
    pw = win.main_page.vr_panel
    pw.mode = "translate"
    pw.stack.setCurrentIndex(V.PAGE_MAIN)
    pw.refresh(force=True)

    def tap(widget):  # Klick wie vom Layer (u/v)
        c = widget.mapTo(pw, widget.rect().center())
        pw.click(c.x() / pw.width(), c.y() / pw.height())

    def thumbs():
        items = [pw.gal_grid.itemAt(i).widget() for i in range(pw.gal_grid.count())]
        return [w for w in items if w is not None and w.objectName() == "thumb"]

    assert pw.nav.isVisible()
    tap(pw.nav_next)                                                 # ▶ → Galerie, größer
    assert pw.mode == "gallery" and pw.stack.currentIndex() == V.PAGE_GALLERY
    assert json.loads((tmp_path / "panel_pose.json").read_text())["width"] == V.PAGE_SIZE_DEFAULT["gallery"]
    assert len(paths.gallery_photos(win.cfg)) == 21                  # Foto-Ordner + VRChat/2026-06
    first = [v for k, v in pw.gal_pages_cache[0] if k == "month"]
    assert first[0] == "2026 " + ("Oktober" if V.tr("month_10") == "Oktober" else "October")
    assert len(pw.gal_pages_cache) == 2 and pw.gal_down.isVisible()
    tap(pw.gal_down)
    assert pw.gal_page == 1 and pw.gal_pages_cache[1][0][0] == "month"  # neuer Monat-Trenner oben
    tap(pw.gal_up)
    tap(thumbs()[0])                                                 # neuestes Foto
    assert pw.gal_open.name == "ViewShot_05.png" and not pw.nav.isVisible()
    tap(pw.single_copy)
    assert copied == ["ViewShot_05.png"]
    tap(pw.single_delete)                                            # 1× = nachfragen
    assert pw.gal_confirm and trashed == []
    tap(pw.single_delete)                                            # 2× = in den Papierkorb
    assert trashed == ["ViewShot_05.png"] and pw.gal_open.name == "ViewShot_04.png"
    tap(pw.single_info_btn)
    assert pw.stack.currentIndex() == V.PAGE_INFO
    pw.back_to_single()
    tap(pw.single_translate)                                         # 🌐 → Übersetzung, kleiner
    assert pw.mode == "translate" and pw.stack.currentIndex() == V.PAGE_MAIN
    assert json.loads((tmp_path / "panel_pose.json").read_text())["width"] == 0.32
    assert pw.page.chosen.name == "ViewShot_04.png"
    make(photos / "ViewShot_99.png", october + 999)                  # neues Foto in VR → wieder das neueste
    pw.page.refresh()
    assert pw.page.chosen is None
    os.environ.pop("VIEWSHOT_OUTPUT_DIR", None)


def test_gallery_folders_scan(tmp_path, monkeypatch):
    """Unterordner nur, wenn eingeschaltet · Hilfsordner (panel/ …) nie · doppelte Ordner einmal."""
    monkeypatch.setenv("VIEWSHOT_OUTPUT_DIR", str(tmp_path / "p"))
    from core import paths
    (tmp_path / "p" / "panel").mkdir(parents=True)
    (tmp_path / "p" / "sub").mkdir()
    for f in ("p/a.png", "p/panel/panel.png", "p/sub/b.jpg", "x/c.png", "x/d/e.PNG", "x/.hidden/f.png", "x/n.txt"):
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_bytes(b"x")
    cfg = {"gallery_main_subfolders": False,
           "gallery_folders": [{"path": str(tmp_path / "x"), "subfolders": False},
                               {"path": str(tmp_path / "x"), "subfolders": True}]}
    names = lambda: sorted(p.name for p in paths.gallery_photos(cfg, fresh=True))  # noqa: E731
    assert names() == ["a.png", "c.png"]
    cfg["gallery_main_subfolders"] = True
    cfg["gallery_folders"][0]["subfolders"] = True
    assert names() == ["a.png", "b.jpg", "c.png", "e.PNG"]


def test_panel_long_text_pages():
    """Lange Übersetzung → Seiten (▼ / ▲), leere Zeile am Seitenanfang fällt weg."""
    from ui import vr_panel
    assert vr_panel.paginate(["a", "b", "", "c", "d"], 2) == ["a\nb", "c\nd"]
    assert vr_panel.paginate([], 3) == [""]


def test_panel_size_scales_pose(tmp_path, monkeypatch):
    import json
    from ui import vr_panel
    monkeypatch.setattr(vr_panel, "pose_file", lambda: tmp_path / "panel_pose.json")
    assert vr_panel.set_width_cm(40) is False                      # Layer hat noch keine Datei
    (tmp_path / "panel_pose.json").write_text(json.dumps({"width": 0.4, "height": 0.2}))
    assert vr_panel.set_width_cm(80) and vr_panel.width_cm() == 80
    assert abs(json.loads((tmp_path / "panel_pose.json").read_text())["height"] - 0.4) < 1e-9  # gleiches Verhältnis


def test_build_progress_percent():
    from ui.pages.main_install import build_progress
    percent, text = build_progress("   Compiling a\n\r    Building [===>  ] 50/200: ort\r   Compiling b\n")
    assert percent == 25 and "Building" not in text and "Compiling b" in text


def test_panel_answer_number_matches_photo_badge():
    from ui import vr_panel
    assert vr_panel.numbered([], "➜ 4) 盆に返らず (…)\nGrund") == "➜ ④ 盆に返らず (…)\nGrund"


def test_panel_fixed_height_from_vr(tmp_path, monkeypatch):
    import json
    from ui import vr_panel
    monkeypatch.setattr(vr_panel, "pose_file", lambda: tmp_path / "panel_pose.json")
    assert vr_panel.fixed_height_px() is None                       # keine Datei → automatisch
    (tmp_path / "panel_pose.json").write_text(json.dumps({"width": 0.4}))
    assert vr_panel.fixed_height_px() is None                       # Höhe nicht gezogen
    (tmp_path / "panel_pose.json").write_text(json.dumps({"width": 0.4, "height": 0.3}))
    assert vr_panel.fixed_height_px() == 540                        # 720 × 0.3 / 0.4


# ------------------------------------------------------ ⚙ Hintergrund-Dienst
def test_daemon_contract_is_up_to_date():
    """daemon/contract.json (Texte, Standardwerte, Cache-Schlüssel, Prompts) = App.
    Der Rust-Dienst baut die Texte ein und prüft Schlüssel + Prompts dagegen (cargo test).
    Schlägt das fehl: python3 scripts/make_daemon_contract.py"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("contract", ROOT / "scripts/make_daemon_contract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    on_disk = (ROOT / "daemon/contract.json").read_text(encoding="utf-8")
    assert on_disk == mod.render(mod.build()), "python3 scripts/make_daemon_contract.py ausführen"


def test_daemon_recent_games_and_lock(tmp_path, monkeypatch):
    from core import daemon, paths
    log = tmp_path / "layer.log"
    log.write_text("x Instanz erstellt für App: VRChat\n"
                   "x Instanz erstellt für App: wineopenxr test instance\n"
                   "x Instanz erstellt für App: Beat Saber\n"
                   "x Instanz erstellt für App: VRChat\n", encoding="utf-8")
    monkeypatch.setattr(paths, "LOG_FILE", log)
    assert daemon.recent_apps() == ["VRChat", "Beat Saber"]
    # App-Sperre: solange gehalten, bekommt sie niemand sonst (so erkennt der Dienst die App)
    import fcntl
    monkeypatch.setattr(daemon, "LOCK_FILE", tmp_path / "app.lock")
    monkeypatch.setattr(daemon, "_lock_fd", None)
    daemon.hold_app_lock()
    with open(tmp_path / "app.lock", "a") as other:
        with pytest.raises(OSError):
            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    daemon._lock_fd.close()


def test_daemon_units_start_on_layer_hello():
    """systemd startet den Dienst beim ersten Paket des Layers (gleicher Port wie im Layer)."""
    from core import daemon
    rs = (ROOT / "layer/src/lib.rs").read_text(encoding="utf-8")
    assert f"const DAEMON_PORT: u16 = {daemon.PORT};" in rs
    assert f"ListenDatagram=127.0.0.1:{daemon.PORT}" in daemon.SOCKET_UNIT
    assert str(daemon.BINARY) in daemon.SERVICE_UNIT
    app = (ROOT / "daemon/src/app.rs").read_text(encoding="utf-8")
    assert f"pub const CONTROL_PORT: u16 = {daemon.PORT};" in app


def test_welcome_on_first_start(tmp_path, monkeypatch):
    """👋 1 Info → 2 Jetzt installieren (nur wenn nötig) → 3 OK → Optionen → Übersetzung; nur einmal."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from core import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "ui.json")
    from ui import welcome
    from ui.mainwindow import MainWindow
    win = MainWindow()
    shown, installs = [], []
    monkeypatch.setattr(win.main_page, "run_install", lambda: installs.append(1))
    monkeypatch.setattr(welcome, "needs_install", lambda: True)
    monkeypatch.setattr(welcome, "ask", lambda _w, _t, text, buttons: (shown.append((text, buttons)), 0)[1])
    welcome.run(win)
    assert [b for _t, b in shown] == [[welcome.tr("welcome_next")],
                                      [welcome.tr("welcome_install_now"), welcome.tr("welcome_later")],
                                      [welcome.tr("ok")]]
    assert installs == [1]
    assert win.pages.currentIndex() == 2 and win.options_page.current_tab == welcome.TRANSLATION_TAB
    assert config.load()["welcome_done"] is True
    # schon installiert → Schritt 2 fällt weg; „Später“ installiert nichts
    shown.clear()
    monkeypatch.setattr(welcome, "needs_install", lambda: False)
    welcome.run(win)
    assert len(shown) == 2 and installs == [1]
