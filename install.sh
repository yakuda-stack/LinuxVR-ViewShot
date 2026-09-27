#!/usr/bin/env bash
# LinuxVR-ViewShot – Installer / installer
#
#   curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash
#   curl -fsSL …/install.sh | bash -s -- uninstall
#
# Aus einem geklonten Ordner / from a cloned folder:
#   ./install.sh            installieren oder aktualisieren / install or update
#   ./install.sh uninstall  entfernen (Fotos + Einstellungen bleiben) / remove (photos + settings stay)
#
# Was passiert / what it does:
#   1. prüft git, python3 + PyQt6, cargo (zeigt den Befehl für deine Distro)
#   2. lädt das Projekt nach ~/.local/share/linuxvr-viewshot/app (oder nutzt diesen Ordner)
#   3. baut den OpenXR-Layer und meldet ihn an (scripts/install-layer.sh)
#   4. Startmenü-Eintrag, Icon und Befehl `linuxvr-viewshot`
# Kein sudo nötig – alles landet in deinem Home-Ordner.
set -euo pipefail

REPO_URL="${VIEWSHOT_REPO:-https://github.com/yakuda-stack/LinuxVR-ViewShot.git}"
BRANCH="main"
APP_ID="linuxvr-viewshot"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEFAULT_DIR="$DATA/linuxvr-viewshot/app"
BIN_DIR="$HOME/.local/bin"
DESKTOP_FILE="$DATA/applications/$APP_ID.desktop"
ICON_FILE="$DATA/icons/hicolor/512x512/apps/$APP_ID.png"

if [[ -t 1 ]]; then
    B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'
else
    B=""; G=""; Y=""; R=""; N=""
fi
ok()   { echo "${G}✔${N} $*"; }
warn() { echo "${Y}⚠${N} $*"; }
fail() { echo "${R}✘${N} $*" >&2; exit 1; }
step() { echo; echo "${B}▶ $*${N}"; }

# Läuft das Skript aus einem geklonten Ordner? Dann den benutzen (kein Download).
SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/UI/starter.py" && -f "$SCRIPT_DIR/scripts/install-layer.sh" ]]; then
    APP_DIR="$SCRIPT_DIR"
    FROM_CHECKOUT=1
else
    APP_DIR="${VIEWSHOT_DIR:-$DEFAULT_DIR}"
    FROM_CHECKOUT=0
fi

# ───────────────────────── Entfernen / uninstall ─────────────────────────
if [[ "${1:-}" == "uninstall" ]]; then
    step "Entferne LinuxVR-ViewShot / removing"
    if [[ -x "$APP_DIR/scripts/install-layer.sh" ]]; then
        "$APP_DIR/scripts/install-layer.sh" uninstall
    else
        rm -f "$DATA/openxr/1/api_layers/implicit.d/linuxvr_viewshot.json" \
              "$HOME/.local/lib/linuxvr-viewshot/liblinuxvr_viewshot_layer.so"
        rmdir "$HOME/.local/lib/linuxvr-viewshot" 2>/dev/null || true
    fi
    rm -f "$DESKTOP_FILE" "$ICON_FILE" "$BIN_DIR/$APP_ID"
    if [[ "$FROM_CHECKOUT" == 0 && -d "$DEFAULT_DIR" && "$APP_DIR" == "$DEFAULT_DIR" ]]; then
        rm -rf "$DEFAULT_DIR"
        rmdir "$DATA/linuxvr-viewshot" 2>/dev/null || true
    fi
    command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" 2>/dev/null || true
    ok "Entfernt. Fotos (~/Bilder/LinuxVR-ViewShot) und Einstellungen (~/.config/linuxvr-viewshot) bleiben."
    ok "Removed. Photos and settings (~/.config/linuxvr-viewshot) are kept."
    exit 0
fi

# ───────────────────────── Abhängigkeiten / dependencies ─────────────────────────
step "Prüfe Abhängigkeiten / checking dependencies"

DISTRO=""
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    DISTRO="$(. /etc/os-release; echo "${ID:-} ${ID_LIKE:-}")"
fi
install_hint() {
    case " $DISTRO " in
        *" arch "*|*" cachyos "*|*" endeavouros "*|*" manjaro "*)
            echo "sudo pacman -S --needed git python-pyqt6 rust" ;;
        *" fedora "*|*" rhel "*|*" nobara "*|*" bazzite "*)
            echo "sudo dnf install git python3-pyqt6 cargo" ;;
        *" debian "*|*" ubuntu "*|*" pop "*|*" linuxmint "*)
            echo "sudo apt install git python3-pyqt6 cargo" ;;
        *" opensuse"*|*" suse "*)
            echo "sudo zypper install git python3-PyQt6 cargo" ;;
        *)
            echo "git, python3 + PyQt6, rust/cargo (https://rustup.rs)" ;;
    esac
}

missing=()
command -v git >/dev/null || [[ "$FROM_CHECKOUT" == 1 ]] || missing+=("git")
command -v python3 >/dev/null || missing+=("python3")
if command -v python3 >/dev/null && ! python3 -c "import PyQt6.QtWidgets" 2>/dev/null; then
    missing+=("PyQt6")
fi
# rustup legt cargo oft nach ~/.cargo/bin – das fehlt in manchen Shells im PATH
[[ -d "$HOME/.cargo/bin" ]] && PATH="$HOME/.cargo/bin:$PATH"
command -v cargo >/dev/null || missing+=("cargo")

if (( ${#missing[@]} )); then
    echo "${R}✘${N} Fehlt / missing: ${missing[*]}"
    echo "  Installieren / install:  ${B}$(install_hint)${N}"
    echo "  Danach diesen Befehl nochmal ausführen / then run this again."
    exit 1
fi
ok "git, python3, PyQt6, cargo"

# optional: Texterkennung (Übersetzung) / text recognition (translation)
if python3 -c "import rapidocr, onnxruntime" 2>/dev/null; then
    ok "RapidOCR (Übersetzung / translation)"
else
    warn "Optional – Texterkennung für die Übersetzung fehlt / text recognition for translation missing:"
    echo "    pip install --user rapidocr onnxruntime"
    echo "    (Arch: sudo pacman -S python-onnxruntime-cpu && pip install --user --break-system-packages rapidocr)"
fi

# ───────────────────────── Projekt holen / get the project ─────────────────────────
if [[ "$FROM_CHECKOUT" == 1 ]]; then
    step "Benutze diesen Ordner / using this folder: $APP_DIR"
elif [[ -d "$APP_DIR/.git" ]]; then
    step "Aktualisiere / updating: $APP_DIR"
    git -C "$APP_DIR" pull --ff-only origin "$BRANCH" || fail "git pull fehlgeschlagen / failed"
else
    step "Lade herunter / downloading → $APP_DIR"
    [[ -e "$APP_DIR" ]] && fail "$APP_DIR existiert schon, ist aber kein git-Ordner / exists but is not a git folder"
    mkdir -p "$(dirname "$APP_DIR")"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$APP_DIR" || fail "git clone fehlgeschlagen / failed"
fi
ok "Projekt / project: $APP_DIR"

# ───────────────────────── Layer bauen / build the layer ─────────────────────────
step "Baue den OpenXR-Layer (1–2 Minuten) / building the OpenXR layer (1–2 minutes)"
bash "$APP_DIR/scripts/install-layer.sh"

# ───────────────────────── Startmenü / app menu ─────────────────────────
step "Startmenü, Icon und Befehl / app menu, icon and command"
chmod +x "$APP_DIR/UI/start.sh"
install -Dm644 "$APP_DIR/UI/assets/$APP_ID.png" "$ICON_FILE"
mkdir -p "$BIN_DIR" "$(dirname "$DESKTOP_FILE")"
ln -sf "$APP_DIR/UI/start.sh" "$BIN_DIR/$APP_ID"
sed "s|@START@|$APP_DIR/UI/start.sh|" "$APP_DIR/packaging/$APP_ID.desktop.in" > "$DESKTOP_FILE"
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$DATA/icons/hicolor" 2>/dev/null || true
ok "Startmenü / app menu: LinuxVR-ViewShot"
ok "Befehl / command:     $APP_ID"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR ist nicht im PATH – Befehl dann über den vollen Pfad starten / not in PATH" ;;
esac

echo
echo "${G}${B}✔ Fertig! / Done!${N}"
echo "  Starten / start:  ${B}$APP_ID${N}  (oder im Startmenü / or from the app menu)"
echo "  VR-Spiel neu starten, damit der Layer geladen wird / restart your VR game to load the layer."
echo "  Update:   dieselbe Zeile nochmal ausführen / run the same line again"
echo "  Entfernen / remove:  ${B}curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash -s -- uninstall${N}"
