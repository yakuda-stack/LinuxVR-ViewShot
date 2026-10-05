"""
core/output.py – Übersetzung nach außen geben, z. B. an ein Plugin in OSC-DreamChatbox.

Zwei Wege, jeder einzeln an/aus (Optionen → Übersetzung → Ausgabe):

    📡 OSC        UDP an out_osc_host:out_osc_port (Standard 127.0.0.1:9025)
                  Adresse  /viewshot/translation
                  Argumente  1. Übersetzung  2. erkannter Originaltext  3. Quelle "photo" / "lens"
                  (alles Strings, UTF-8)
    📄 Datei      out_file_path (leer = ~/.local/state/linuxvr-viewshot/translation.json)
                  dieselben Infos wie OSC, als JSON – immer nur die LETZTE Übersetzung:
                    {"id": 1791198594286, "time": "2026-10-05T12:34:56",
                     "translation": "…", "original": "…", "source": "photo"}
                  "id" (ms seit 1970) ist bei jeder neuen Übersetzung anders – so merkt ein
                  Plugin auch eine neue Übersetzung mit gleichem Text. Die Datei wird in einem
                  Schritt ersetzt (nie halb geschrieben).

Gesendet wird nach jedem neuen Foto-Ergebnis und bei 🔁 Lens nur, wenn sich der
Text geändert hat. Der ⚙ Dienst (daemon/src/output.rs) macht genau dasselbe, wenn die App zu ist.
"""

import json
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

from core.paths import LOG_FILE

OSC_ADDRESS = "/viewshot/translation"
DEFAULT_FILE = LOG_FILE.parent / "translation.json"
MAX_ARG_BYTES = 16000  # pro Text – ein UDP-Paket darf höchstens ~64 KB groß sein

DEFAULTS = {
    "out_osc": False,            # 📡 Übersetzung per OSC senden
    "out_osc_host": "127.0.0.1",
    "out_osc_port": 9025,        # nicht 9000 (VRChat selbst) – hier hört z. B. ein Chatbox-Plugin
    "out_file": False,           # 📄 Übersetzung als JSON-Datei schreiben (gleiche Infos wie OSC)
    "out_file_path": "",         # leer = DEFAULT_FILE
}


def _osc_string(text: str) -> bytes:
    """OSC-String: UTF-8, mit 0-Bytes auf ein Vielfaches von 4 aufgefüllt (mindestens eins)."""
    data = text.encode("utf-8")
    return data + b"\0" * (4 - len(data) % 4)


def _clip(text: str) -> str:
    """Zu lange Texte kürzen, ohne ein UTF-8-Zeichen zu zerschneiden."""
    data = text.encode("utf-8")
    return text if len(data) <= MAX_ARG_BYTES else data[:MAX_ARG_BYTES].decode("utf-8", "ignore")


def osc_message(address: str, *args: str) -> bytes:
    """Eine OSC-Nachricht nur mit String-Argumenten (reicht hier, kein Extra-Paket nötig)."""
    msg = _osc_string(address) + _osc_string("," + "s" * len(args))
    for arg in args:
        msg += _osc_string(_clip(arg))
    return msg


def send_osc(host: str, port: int, translated: str, original: str, source: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(osc_message(OSC_ADDRESS, translated, original, source), (host, int(port)))


def file_path(cfg: dict) -> Path:
    custom = str(cfg.get("out_file_path") or "").strip()
    return Path(os.path.expanduser(custom)) if custom else DEFAULT_FILE


def file_entry(translated: str, original: str, source: str) -> dict:
    """Inhalt der Datei – gleiche Felder wie die OSC-Nachricht + id/time."""
    return {"id": time.time_ns() // 1_000_000, "time": datetime.now().isoformat(timespec="seconds"),
            "translation": translated, "original": original, "source": source}


def write_file(path: Path, translated: str, original: str = "", source: str = "photo") -> None:
    """Erst Hilfsdatei, dann umbenennen → wer die Datei liest, sieht nie eine halbe."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(file_entry(translated, original, source), indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def publish(cfg: dict, translated: str, original: str = "", source: str = "photo") -> str:
    """Neue Übersetzung ausgeben (was eingeschaltet ist). Gibt Fehlertext zurück ("" = ok)."""
    translated = (translated or "").strip()
    if not translated:
        return ""
    errors = []
    if cfg.get("out_osc"):
        try:
            send_osc(cfg.get("out_osc_host") or DEFAULTS["out_osc_host"],
                     cfg.get("out_osc_port") or DEFAULTS["out_osc_port"], translated, original or "", source)
        except (OSError, ValueError, OverflowError) as e:
            errors.append(f"OSC: {e}")
    if cfg.get("out_file"):
        try:
            write_file(file_path(cfg), translated, original or "", source)
        except OSError as e:
            errors.append(f"{file_path(cfg)}: {e}")
    if errors:
        print("[output] " + "; ".join(errors), file=sys.stderr)
    return "; ".join(errors)
