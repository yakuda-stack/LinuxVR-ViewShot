#!/usr/bin/env bash
# Startet die UI (auch über den Befehl `linuxvr-viewshot` = Symlink hierher).
# Voller Pfad zu starter.py = genug Platz für den Prozessnamen
# "LinuxVR-ViewShot" im Taskmanager (siehe starter.py).
DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
cd "$DIR" && exec python3 "$DIR/starter.py" "$@"
