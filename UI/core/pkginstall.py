"""
core/pkginstall.py – ein Systempaket per Knopf installieren (Arch, Fedora, Debian/Ubuntu, openSUSE).

Welche Distro? → /etc/os-release (ID + ID_LIKE, z. B. "cachyos arch" oder "nobara fedora").
Das Passwort fragt pkexec in einem normalen Fenster ab (Polkit) – kein Terminal nötig.

    cmd = install_command("wl-clipboard")   # ["pkexec", "pacman", "-S", "--needed", ...] oder None
    text = manual_command("wl-clipboard")   # "sudo pacman -S wl-clipboard" zum Anzeigen/Kopieren
"""

import shutil
from pathlib import Path

# (Distro-Kennung in os-release, Paketmanager, Befehl zum Installieren)
MANAGERS = [
    (("arch", "cachyos", "endeavouros", "manjaro"), "pacman", ["pacman", "-S", "--needed", "--noconfirm"]),
    (("fedora", "nobara", "bazzite", "rhel"), "dnf", ["dnf", "install", "-y"]),
    (("debian", "ubuntu", "linuxmint", "pop"), "apt-get", ["apt-get", "install", "-y"]),
    (("opensuse", "suse"), "zypper", ["zypper", "--non-interactive", "install"]),
]

# Paketnamen, falls sie je Distro anders heißen (wl-clipboard heißt überall gleich)
NAMES = {("dnf", "npm"): "nodejs-npm"}


def distro_ids(os_release: str | None = None) -> list[str]:
    """IDs aus /etc/os-release, z. B. ["nobara", "fedora"]."""
    if os_release is None:
        try:
            os_release = Path("/etc/os-release").read_text(encoding="utf-8")
        except OSError:
            return []
    ids = []
    for line in os_release.splitlines():
        key, _, value = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids += value.strip().strip('"').lower().split()
    return ids


def _manager(os_release: str | None = None):
    ids = distro_ids(os_release)
    for names, binary, cmd in MANAGERS:
        if any(i.startswith(n) for i in ids for n in names):
            return binary, cmd
    # os-release unbekannt → einfach nachsehen, welcher Paketmanager da ist
    for _names, binary, cmd in MANAGERS:
        if shutil.which(binary):
            return binary, cmd
    return None


def manual_command(package: str, os_release: str | None = None) -> str:
    """Befehl zum Selbst-Eintippen (wird angezeigt, falls der Knopf nicht geht)."""
    if os_release is None and Path("/run/ostree-booted").exists():
        return f"rpm-ostree install {package}   (+ Neustart / reboot)"
    found = _manager(os_release)
    if found is None:
        return package
    binary, _cmd = found
    name = NAMES.get((binary, package), package)
    short = {"pacman": "pacman -S", "dnf": "dnf install", "apt-get": "apt install",
             "zypper": "zypper install"}[binary]
    return f"sudo {short} {name}"


def install_command(package: str, os_release: str | None = None) -> list[str] | None:
    """Befehl für den Knopf (mit pkexec), oder None wenn das nicht geht
    (kein pkexec, unbekannte Distro, rpm-ostree-System wie Bazzite …)."""
    if not shutil.which("pkexec"):
        return None
    if Path("/run/ostree-booted").exists():
        return None  # unveränderliches System (Silverblue, Bazzite): dnf geht dort nicht
    found = _manager(os_release)
    if found is None:
        return None
    binary, cmd = found
    exe = shutil.which(binary)
    if not exe:
        return None
    return ["pkexec", exe] + cmd[1:] + [NAMES.get((binary, package), package)]
