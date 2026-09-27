#!/usr/bin/env bash
# LinuxVR-ViewShot – Layer bauen und für den aktuellen Benutzer installieren
#   ./scripts/install-layer.sh            → bauen + installieren
#   ./scripts/install-layer.sh uninstall  → entfernen
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB_DIR="$HOME/.local/lib/linuxvr-viewshot"
LIB="$LIB_DIR/liblinuxvr_viewshot_layer.so"
MANIFEST_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/openxr/1/api_layers/implicit.d"
MANIFEST="$MANIFEST_DIR/linuxvr_viewshot.json"

if [[ "${1:-}" == "uninstall" ]]; then
    rm -f "$MANIFEST" "$LIB" "$LIB_DIR/VERSION"
    rmdir "$LIB_DIR" 2>/dev/null || true
    echo "✔ LinuxVR-ViewShot entfernt / removed"
    exit 0
fi

command -v cargo >/dev/null || { echo "✘ cargo fehlt / missing (sudo pacman -S rust)"; exit 1; }

cd "$ROOT"
cargo build --release
mkdir -p "$LIB_DIR" "$MANIFEST_DIR"
install -m 755 target/release/liblinuxvr_viewshot_layer.so "$LIB"
sed "s|@LIBRARY_PATH@|$LIB|" manifest/linuxvr_viewshot.json.in > "$MANIFEST"
# Version merken – eine AppImage erkennt daran, ob dieser Layer zu ihr passt
sed -n 's/^VERSION *= *"v\{0,1\}\([^"]*\)".*/\1/p' UI/core/version.py > "$LIB_DIR/VERSION"

PICS="$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")/LinuxVR-ViewShot"
mkdir -p "$PICS"

echo "✔ Layer:    $LIB"
echo "✔ Manifest: $MANIFEST"
echo "  Log:      ~/.local/state/linuxvr-viewshot/layer.log"
echo "✔ Fotos:    $PICS"
