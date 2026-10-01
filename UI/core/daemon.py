"""
core/daemon.py – ⚙ Hintergrund-Dienst (viewshot-daemon, Rust) – LinuxVR-ViewShot ohne offene App.

Der Dienst macht, was sonst die App macht: neues Foto → Text lesen → übersetzen
(gleiche Dienste, gleicher Cache) → 🪟 Panel und 🔁 Lens in VR. Die App ist dann
hauptsächlich zum Einstellen – und zum Ansehen (Galerie, Verlauf).

Wer macht was?
    App offen  → sie hält app.lock, der Dienst wartet nur (alles wie gewohnt)
    App zu     → der Dienst übernimmt
Start: Der Layer schickt beim VR-Spiel „hello“ an 127.0.0.1:47932 – systemd
(Socket-Aktivierung) startet den Dienst dann von selbst. Kein Spiel mehr → er beendet sich.
Welche Spiele: layer.json "daemon" = "off" / "all" / "selected" (+ "daemon_apps").

Installiert (setup(), bei jedem App-Start – kopiert nur, was sich geändert hat):
    ~/.local/lib/linuxvr-viewshot/viewshot-daemon          (baut install-layer.sh / liegt bei)
    ~/.local/lib/linuxvr-viewshot/libonnxruntime.so.*      (aus dem Python-Paket onnxruntime)
    ~/.local/lib/linuxvr-viewshot/ocr-models/*.onnx        (die Modelle von RapidOCR)
    ~/.config/systemd/user/linuxvr-viewshot-daemon.{socket,service}
"""

import fcntl
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from core import paths

BINARY = paths.USER_LIB.parent / "viewshot-daemon"
LIB_DIR = paths.USER_LIB.parent
MODELS_DIR = LIB_DIR / "ocr-models"
LOCK_FILE = paths.LOG_FILE.parent / "app.lock"
LOG = paths.LOG_FILE.parent / "daemon.log"
PORT = 47932
UNIT = "linuxvr-viewshot-daemon"
UNIT_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or paths.HOME / ".config") / "systemd" / "user"

# Fertig gebauter Dienst in der AppImage / im AUR-Paket (neben dem Layer)
APPIMAGE_BINARY = paths.APPIMAGE_LAYER.parent / "viewshot-daemon"
PACKAGE_BINARY = paths.PACKAGE_LAYER.parent / "viewshot-daemon"
BUILT_BINARY = paths.PROJECT_DIR / "target" / "release" / "viewshot-daemon"

SOCKET_UNIT = f"""[Unit]
Description=LinuxVR-ViewShot – Hintergrund-Dienst (startet beim VR-Spiel)

[Socket]
ListenDatagram=127.0.0.1:{PORT}

[Install]
WantedBy=sockets.target
"""

SERVICE_UNIT = f"""[Unit]
Description=LinuxVR-ViewShot – Übersetzen + VR-Panel ohne offene App

[Service]
ExecStart={BINARY}
# RAM/CPU nie wichtiger als das Spiel
Nice=5
"""

_lock_fd = None


def hold_app_lock() -> None:
    """App läuft → Sperre halten (bis die App endet). Der Dienst wartet solange."""
    global _lock_fd
    import time
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        _lock_fd = open(LOCK_FILE, "a")  # noqa: SIM115 – muss offen bleiben
    except OSError:
        return
    # Der Dienst prüft die Sperre ab und zu ganz kurz selbst → dann gleich nochmal versuchen
    for _ in range(40):
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            time.sleep(0.05)  # zweite App-Instanz o. Ä. → nach 2 s aufgeben


def source_binary() -> Path | None:
    """Woher kommt der Dienst? (AppImage / Paket / selbst gebaut)"""
    for p in (APPIMAGE_BINARY, PACKAGE_BINARY, BUILT_BINARY):
        if p.is_file():
            return p
    return None


def installed() -> bool:
    return BINARY.is_file() and (UNIT_DIR / f"{UNIT}.socket").is_file()


def _copy_if_changed(src: Path, dst: Path, mode: int = 0o644) -> bool:
    try:
        if dst.is_file() and dst.stat().st_size == src.stat().st_size \
                and dst.stat().st_mtime >= src.stat().st_mtime:
            return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".new")
        shutil.copyfile(src, tmp)
        tmp.chmod(mode)
        os.replace(tmp, dst)  # ein laufender Dienst behält die alte Datei
        return True
    except OSError as e:
        logging.warning("Dienst: %s → %s: %s", src, dst, e)
        return False


def _ocr_sources() -> tuple[Path | None, Path | None]:
    """libonnxruntime.so aus dem Python-Paket + Ordner mit den RapidOCR-Modellen."""
    lib = models = None
    try:
        import onnxruntime
        capi = Path(onnxruntime.__file__).resolve().parent / "capi"
        found = sorted(capi.glob("libonnxruntime.so*"))
        lib = found[-1] if found else None
    except Exception:  # noqa: BLE001 – Texterkennung ist optional
        pass
    try:
        from core import ocr
        root = Path(ocr._model_params()["Global.model_root_dir"])
        if any(root.glob("*.onnx")):
            models = root
    except Exception:  # noqa: BLE001
        pass
    return lib, models


def systemctl(*args: str) -> bool:
    try:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True,
                              timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def setup() -> None:
    """Dienst + Texterkennung nach ~/.local kopieren, systemd-Socket einrichten.
    BLOCKIERT kurz (Kopieren, systemctl) → im Hintergrund-Thread aufrufen."""
    src = source_binary()
    if src is None:
        return  # z. B. noch nie gebaut
    _copy_if_changed(src, BINARY, 0o755)
    lib, models = _ocr_sources()
    if lib is not None:
        _copy_if_changed(lib, LIB_DIR / lib.name, 0o755)
    if models is not None:
        for m in models.glob("*.onnx"):
            _copy_if_changed(m, MODELS_DIR / m.name)
    changed = False
    for name, text in ((f"{UNIT}.socket", SOCKET_UNIT), (f"{UNIT}.service", SERVICE_UNIT)):
        f = UNIT_DIR / name
        try:
            if not f.is_file() or f.read_text(encoding="utf-8") != text:
                UNIT_DIR.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8")
                changed = True
        except OSError as e:
            logging.warning("Dienst: %s: %s", f, e)
            return
    if changed:
        systemctl("daemon-reload")
    systemctl("enable", "--now", f"{UNIT}.socket")


def uninstall() -> None:
    systemctl("disable", "--now", f"{UNIT}.socket")
    systemctl("stop", f"{UNIT}.service")
    for f in (UNIT_DIR / f"{UNIT}.socket", UNIT_DIR / f"{UNIT}.service", BINARY):
        f.unlink(missing_ok=True)
    shutil.rmtree(MODELS_DIR, ignore_errors=True)
    for lib in LIB_DIR.glob("libonnxruntime.so*"):
        lib.unlink(missing_ok=True)
    systemctl("daemon-reload")


def running() -> bool:
    return systemctl("is-active", "--quiet", f"{UNIT}.service")


def recent_apps(limit: int = 12) -> list[str]:
    """Spiele, in denen der Layer zuletzt lief (aus layer.log) – zum Auswählen."""
    try:
        text = paths.LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    for name in reversed(re.findall(r"Instanz erstellt für App: (.+)", text)):
        name = name.strip()
        if name and "test instance" not in name and name not in found:
            found.append(name)
    return found[:limit]
