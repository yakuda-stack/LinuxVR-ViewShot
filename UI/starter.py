#!/usr/bin/env python3
"""
LinuxVR-ViewShot – Startpunkt mit richtigem Prozessnamen.

Taskmanager (KDE Systemmonitor, htop, ps) sollen "LinuxVR-ViewShot" zeigen
statt "python3". Dafür zwei Stellen:
  1) /proc/self/comm  – der Kernel erlaubt nur 15 Zeichen → "LinuxVR-ViewSho"
  2) /proc/self/cmdline – das erste Wort wird "LinuxVR-ViewShot"
KDE nimmt (2), wenn es mit (1) anfängt → voller Name.

setproctitle (optional, pip/pacman) macht (2) sauber. Ohne das Paket
überschreiben wir den Speicher der Befehlszeile selbst (/proc/self/mem) –
das geht nur so weit, wie die ursprüngliche Befehlszeile lang war; darum
startet start.sh mit dem vollen Pfad zu dieser Datei.
"""

import ctypes
import sys

NAME = "LinuxVR-ViewShot"


def set_cmdline_name(name: str) -> bool:
    """argv[0] in /proc/self/cmdline überschreiben (wie setproctitle, ohne Paket)."""
    try:
        with open("/proc/self/stat", "rb") as f:
            # Felder nach ")" beginnen bei Nr. 3 → arg_start = Feld 48, arg_end = Feld 49
            fields = f.read().rsplit(b")", 1)[1].split()
        start, end = int(fields[48 - 3]), int(fields[49 - 3])
        data = name.encode()[: end - start - 1] + b"\0"
        with open("/proc/self/mem", "r+b", buffering=0) as mem:
            mem.seek(start)
            mem.write(data.ljust(end - start, b"\0"))
        return True
    except (OSError, ValueError, IndexError):
        return False


def set_process_name() -> None:
    sys.argv[0] = NAME
    try:
        from setproctitle import setproctitle
        setproctitle(NAME)
    except ImportError:
        set_cmdline_name(NAME)
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(15, NAME.encode(), 0, 0, 0)  # 15 = PR_SET_NAME (max. 15 Zeichen)
    except OSError:
        pass


if __name__ == "__main__":
    set_process_name()
    import main

    main.run_app()
