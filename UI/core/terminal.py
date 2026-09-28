"""
core/terminal.py – einen Befehl in einem Terminal-Fenster öffnen (z. B. zum Anmelden bei Claude Code).

Sucht das Terminal des Desktops (Konsole, GNOME, Ptyxis, …). Das Fenster bleibt nach dem
Befehl offen ("Enter zum Schließen"), damit man Fehlermeldungen lesen kann.
"""

import shlex
import shutil
import subprocess

# (Programm, Argumente vor dem Befehl) – Reihenfolge = Vorrang
TERMINALS = [
    ("konsole", ["-e"]),
    ("ptyxis", ["-x"]),            # Fedora 41+ Standard (Befehl als EIN String)
    ("gnome-terminal", ["--"]),
    ("kgx", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("alacritty", ["-e"]),
    ("kitty", []),
    ("foot", []),
    ("wezterm", ["start", "--"]),
    ("x-terminal-emulator", ["-e"]),
    ("xterm", ["-e"]),
]


def find() -> str | None:
    for name, _args in TERMINALS:
        if shutil.which(name):
            return name
    return None


def command(argv: list[str], pause_text: str = "Enter …") -> list[str] | None:
    """Befehlsliste zum Starten, oder None ohne Terminal."""
    name = find()
    if name is None:
        return None
    script = f"{shlex.join(argv)}; echo; read -r -p {shlex.quote(pause_text)} _"
    shell = ["bash", "-c", script]
    args = dict(TERMINALS)[name]
    if name == "ptyxis":
        return [name] + args + [shlex.join(shell)]
    return [name] + args + shell


def run(argv: list[str], pause_text: str = "Enter …") -> bool:
    """Öffnet das Terminal mit dem Befehl. False = kein Terminal gefunden."""
    cmd = command(argv, pause_text)
    if cmd is None:
        return False
    try:
        # im Home-Ordner starten – nicht im Projekt-/App-Ordner (Gemini & Co.
        # würden den sonst als "Arbeitsordner" ansehen)
        from pathlib import Path
        subprocess.Popen(cmd, start_new_session=True, cwd=str(Path.home()))
    except OSError:
        return False
    return True
