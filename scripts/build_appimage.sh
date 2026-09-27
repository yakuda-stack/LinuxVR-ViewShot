#!/bin/bash
# LinuxVR-ViewShot — AppImage Builder (gleicher Aufbau wie bei OSC-DreamChatbox)
# Benötigt: python3, pip, cargo (appimagetool + Runtime werden automatisch geladen)
# Verwendung:  bash scripts/build_appimage.sh   (egal von wo aus)
#
# Ergebnis:    build/LinuxVR-ViewShot-<version>-x86_64.AppImage (+ .zsync)
#              build/ wird bei JEDEM Lauf komplett geleert.
#
# Besonderheit gegenüber den anderen Projekten: der OpenXR-Layer (Rust, .so)
# liegt FERTIG GEBAUT in der AppImage. Das Spiel kann ihn dort aber nicht
# laden (die AppImage hängt sich bei jedem Start unter einem anderen Pfad
# ein) – die App kopiert ihn deshalb beim Klick auf "Installieren" nach
# ~/.local/lib/linuxvr-viewshot/ (UI/core/layer_install.py) und zieht ihn
# nach einem AppImage-Update von selbst nach.
#
# Schalter:
#   VS_NO_OCR=1     ohne Texterkennung (RapidOCR/onnxruntime/OpenCV) → ~100 MB kleiner,
#                   Übersetzung + QR-Codes gehen dann nur mit Paketen vom System
#   VS_PYVERS="3.12 3.13"   andere Python-Versionen
#   VS_NO_ZSYNC=1   ohne Delta-Update-Datei

set -e

# immer vom Projekt-Root aus arbeiten
cd "$(dirname "$0")"
for _ in 1 2 3; do
    [ -f UI/core/version.py ] && break
    cd ..
done
if [ ! -f UI/core/version.py ]; then
    echo "FEHLER: Projekt-Root nicht gefunden (UI/core/version.py fehlt)."
    exit 1
fi

APP="LinuxVR-ViewShot"
ID="linuxvr-viewshot"
VERSION="$(sed -n 's/^VERSION *= *"v\{0,1\}\([^"]*\)".*/\1/p' UI/core/version.py)"
if [ -z "$VERSION" ]; then
    echo "FEHLER: VERSION in UI/core/version.py nicht gefunden."
    exit 1
fi
ARCH="x86_64"
OUT_DIR="$(pwd)/build"
BUILD_DIR="$OUT_DIR/AppDir"
OUT="$OUT_DIR/${APP}-${VERSION}-${ARCH}.AppImage"
SHARE="$BUILD_DIR/usr/share/$ID"          # = PROJECT_DIR der App (UI/core/paths.py)

echo "=== LinuxVR-ViewShot AppImage Builder ==="
echo "Version: $VERSION"
echo ""

for f in UI/starter.py UI/main.py UI/core/paths.py UI/assets/$ID.png \
         manifest/linuxvr_viewshot.json.in packaging/$ID.desktop.in CHANGELOG.md; do
    if [ ! -e "$f" ]; then
        echo "FEHLER: $f nicht gefunden — bitte aus dem Projekt-Root bauen."
        exit 1
    fi
done
command -v cargo >/dev/null || [ -x "$HOME/.cargo/bin/cargo" ] || {
    echo "FEHLER: cargo fehlt (sudo pacman -S rust) – der Layer muss gebaut werden."
    exit 1
}
[ -d "$HOME/.cargo/bin" ] && PATH="$HOME/.cargo/bin:$PATH"

# 0. build/ frisch anlegen
echo "[0/6] Leere build/ ..."
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

# 1. appimagetool + statische Runtime (fuse2 UND fuse3) – wie bei DreamChatbox
if [ -z "${APPIMAGETOOL:-}" ]; then
    APPIMAGETOOL="/tmp/appimagetool-new-${ARCH}"
    if [ ! -s "$APPIMAGETOOL" ]; then
        echo "[Info] Lade appimagetool (github.com/AppImage/appimagetool)..."
        wget -q "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage" \
            -O "$APPIMAGETOOL" || {
            echo "FEHLER: appimagetool konnte nicht geladen werden."
            rm -f "$APPIMAGETOOL"
            exit 1
        }
    fi
    if ! head -c 4 "$APPIMAGETOOL" | grep -q "ELF"; then
        echo "FEHLER: $APPIMAGETOOL ist keine ELF-Datei — Download kaputt."
        rm -f "$APPIMAGETOOL"
        exit 1
    fi
    chmod +x "$APPIMAGETOOL"
fi
export APPIMAGE_EXTRACT_AND_RUN=1

RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-${ARCH}"
RUNTIME="/tmp/appimage-runtime-${ARCH}"
if [ ! -s "$RUNTIME" ]; then
    echo "[Info] Lade statische AppImage-Runtime (fuse2+fuse3)..."
    wget -q "$RUNTIME_URL" -O "$RUNTIME" || {
        echo "FEHLER: Runtime konnte nicht geladen werden ($RUNTIME_URL)."
        exit 1
    }
fi
if ! head -c 4 "$RUNTIME" | grep -q "ELF"; then
    echo "FEHLER: $RUNTIME ist keine ELF-Datei — Download kaputt."
    rm -f "$RUNTIME"
    exit 1
fi
chmod +x "$RUNTIME"

# 2. OpenXR-Layer bauen
echo "[1/6] Baue den OpenXR-Layer (Rust)..."
cargo build --release --locked
SO="target/release/liblinuxvr_viewshot_layer.so"
[ -s "$SO" ] || { echo "FEHLER: $SO fehlt nach cargo build."; exit 1; }

# glibc-Check: die .so läuft nur auf Systemen mit mindestens dieser glibc.
# Auf Arch gebaut ist das meist 2.34 – passt für Ubuntu 22.04 / Mint 21+.
if command -v objdump >/dev/null; then
    GLIBC_MAX="$(objdump -T "$SO" | grep -o 'GLIBC_[0-9.]*' | sed 's/GLIBC_//' | sort -V | tail -1)"
    echo "[Info] Layer braucht mindestens glibc $GLIBC_MAX"
    if [ "$(printf '%s\n2.35\n' "$GLIBC_MAX" | sort -V | tail -1)" != "2.35" ]; then
        echo "[Warn] glibc $GLIBC_MAX ist neuer als 2.35 – auf Ubuntu 22.04 / Mint 21 lädt der Layer dann nicht."
    fi
fi

# 3. AppDir: App + Layer + Manifest-Vorlage
echo "[2/6] Erstelle AppDir..."
mkdir -p "$BUILD_DIR/usr/bin" "$SHARE/UI" "$SHARE/lib" "$SHARE/manifest" \
         "$BUILD_DIR/usr/share/applications" "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps"
cp UI/main.py UI/starter.py UI/start.sh "$SHARE/UI/"
cp -r UI/core UI/ui UI/assets "$SHARE/UI/"
install -m 755 "$SO" "$SHARE/lib/liblinuxvr_viewshot_layer.so"   # → paths.APPIMAGE_LAYER
cp manifest/linuxvr_viewshot.json.in "$SHARE/manifest/"          # → paths.MANIFEST_TEMPLATE
cp CHANGELOG.md LICENSE README.md "$SHARE/" 2>/dev/null || true
find "$SHARE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# Wrapper: voller Pfad zu starter.py = Platz für den Prozessnamen im Taskmanager
cat > "$BUILD_DIR/usr/bin/$ID" << 'WRAPPER'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "${VIEWSHOT_PYTHON:-python3}" "$HERE/../share/linuxvr-viewshot/UI/starter.py" "$@"
WRAPPER
chmod +x "$BUILD_DIR/usr/bin/$ID"

# 4. Icon + Desktop-Datei
echo "[3/6] Setze Icon und Desktop-Eintrag..."
cp "UI/assets/$ID.png" "$BUILD_DIR/usr/share/icons/hicolor/512x512/apps/$ID.png"
cp "UI/assets/$ID.png" "$BUILD_DIR/$ID.png"
sed "s|@START@|$ID|" "packaging/$ID.desktop.in" > "$BUILD_DIR/usr/share/applications/$ID.desktop"
cp "$BUILD_DIR/usr/share/applications/$ID.desktop" "$BUILD_DIR/$ID.desktop"

# 5. Python-Abhängigkeiten für mehrere Python-Versionen (wie DreamChatbox)
echo "[4/6] Bundele Python-Abhängigkeiten..."
PYVERS="${VS_PYVERS:-3.12 3.13 3.14}"
DEPS=(PyQt6 setproctitle)
# Texterkennung + QR-Codes. rapidocr selbst ohne seine Abhängigkeiten: es
# will opencv-python (mit eigenem Qt5 → beißt sich mit PyQt6), wir nehmen
# opencv-python-headless.
OCR_DEPS=(numpy opencv-python-headless onnxruntime pyclipper shapely omegaconf
          PyYAML requests colorlog six tqdm Pillow)
PLAT_ARGS=()
for g in 17 24 27 28 31 34 35; do
    PLAT_ARGS+=(--platform "manylinux_2_${g}_${ARCH}")
done
PLAT_ARGS+=(--platform "manylinux2014_${ARCH}")

if python3 -m pip --version >/dev/null 2>&1; then
    PIP=(python3 -m pip)
else
    PIP=(pip)
fi
pipi() {   # pip install – bei "externally managed" (Arch) mit --break-system-packages
    "${PIP[@]}" install "$@" 2>>"$PIPLOG" || "${PIP[@]}" install --break-system-packages "$@" 2>>"$PIPLOG"
}

SITE="$BUILD_DIR/usr/lib/python3"
STAGE="$OUT_DIR/pystage"
mkdir -p "$SITE"
DONE_VERS=""
OCR_VERS=""
for V in $PYVERS; do
    echo "      → Python $V"
    PIPLOG="$OUT_DIR/pip-$V.log"
    rm -rf "$STAGE"
    XARGS=(--quiet --no-compile --target="$STAGE" --python-version "$V"
           --implementation cp --only-binary=:all: "${PLAT_ARGS[@]}")
    if pipi "${XARGS[@]}" "${DEPS[@]}"; then
        if [ -z "${VS_NO_OCR:-}" ]; then
            # OCR getrennt: fehlt z. B. onnxruntime für eine Python-Version,
            # läuft die App dort trotzdem (nur ohne Texterkennung)
            if pipi "${XARGS[@]}" "${OCR_DEPS[@]}" \
               && pipi "${XARGS[@]}" --no-deps rapidocr; then
                OCR_VERS="$OCR_VERS $V"
            else
                echo "[Warn] Texterkennung für Python $V nicht gebundelt (Log: build/pip-$V.log)."
            fi
        fi
        cp -a "$STAGE/." "$SITE/"
        DONE_VERS="$DONE_VERS $V"
    else
        echo "[Warn] Python $V übersprungen — keine passenden Wheels (Log: build/pip-$V.log)."
    fi
done
rm -rf "$STAGE"
rm -f "$OUT_DIR"/pip-*.log 2>/dev/null || true
DONE_VERS="${DONE_VERS# }"
OCR_VERS="${OCR_VERS# }"
if [ -z "$DONE_VERS" ]; then
    echo "FEHLER: Für keine Python-Version konnten Abhängigkeiten gebundelt werden."
    exit 1
fi

# RapidOCR lädt seine Modelle beim ersten Start IN seinen Paketordner – in
# der AppImage ist der schreibgeschützt. Also jetzt schon laden.
if [ -n "$OCR_VERS" ]; then
    SYSV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
    case " $OCR_VERS " in
        *" $SYSV "*)
            echo "      → lade OCR-Modelle vorab (Python $SYSV)"
            # model_root_dir als TEXT – ein Path-Objekt lehnt neueres omegaconf ab
            PYTHONPATH="$SITE" python3 -c "
import logging, pathlib; logging.disable(logging.INFO)
import rapidocr
from rapidocr import RapidOCR
models = pathlib.Path(rapidocr.__file__).resolve().parent / 'models'
RapidOCR(params={'Global.model_root_dir': str(models)})
print('      ✔ OCR-Modelle liegen in der AppImage')" \
            || echo "[Warn] OCR-Modelle nicht vorab geladen – die App lädt sie beim ersten Mal nach ~/.cache (Internet nötig)."
            ;;
        *)
            echo "[Warn] python3 dieses Systems ($SYSV) ist nicht unter: $OCR_VERS – OCR-Modelle nicht vorab geladen."
            ;;
    esac
fi
find "$SITE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# Alle Python-Versionen landen in EINEM Ordner. Hat pip für zwei Versionen
# verschiedene Paket-Versionen genommen (z. B. numpy), liegen .py-Dateien der
# einen neben .so-Dateien der anderen → Absturz beim Import. Hier warnen.
MIXED="$(find "$SITE" -maxdepth 1 -name '*.dist-info' -printf '%f\n' \
    | sed -E 's/-[0-9][^-]*\.dist-info$//' | sort | uniq -d | tr '\n' ' ')"
if [ -n "$MIXED" ]; then
    echo "[Warn] Gemischte Paket-Versionen: $MIXED– VS_PYVERS einschränken (z. B. \"3.12 3.13\")."
fi

echo "$DONE_VERS" > "$SHARE/.python-versions"
echo "[Info] Gebundelt für Python: $DONE_VERS"
[ -z "${VS_NO_OCR:-}" ] && echo "[Info] Texterkennung für Python: ${OCR_VERS:-keine}"

# AppRun: passenden Python suchen, fehlende Qt-Bibliotheken im Klartext melden
cat > "$BUILD_DIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/lib/python3:$PYTHONPATH"
export PATH="$HERE/usr/bin:$PATH"

if ! command -v python3 >/dev/null 2>&1; then
    echo "LinuxVR-ViewShot: python3 nicht gefunden." >&2
    echo "  Debian/Ubuntu/Mint:  sudo apt install python3" >&2
    echo "  Fedora:              sudo dnf install python3" >&2
    exit 1
fi

SUPPORTED="$(cat "$HERE/usr/share/linuxvr-viewshot/.python-versions" 2>/dev/null)"
pyver() { "$1" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null; }
HAVE="$(pyver python3)"
VIEWSHOT_PYTHON="python3"
if [ -n "$SUPPORTED" ]; then
    case " $SUPPORTED " in
        *" $HAVE "*) ;;
        *)
            VIEWSHOT_PYTHON=""
            for V in $(printf '%s\n' $SUPPORTED | sort -rV); do
                if command -v "python$V" >/dev/null 2>&1 \
                   && [ "$(pyver "python$V")" = "$V" ]; then
                    VIEWSHOT_PYTHON="python$V"
                    break
                fi
            done
            if [ -z "$VIEWSHOT_PYTHON" ]; then
                echo "LinuxVR-ViewShot: diese AppImage läuft mit Python $SUPPORTED," >&2
                echo "  auf diesem System ist python3 = $HAVE." >&2
                echo "  This AppImage needs Python $SUPPORTED (you have $HAVE)." >&2
                exit 1
            fi
            ;;
    esac
fi
export VIEWSHOT_PYTHON

missing=""
if command -v ldconfig >/dev/null 2>&1; then
    libs="$(ldconfig -p 2>/dev/null)"
    case "$libs" in *libxcb-cursor.so.0*) ;; *) missing="$missing libxcb-cursor0";; esac
    case "$libs" in *libxkbcommon-x11.so.0*) ;; *) missing="$missing libxkbcommon-x11-0";; esac
    case "$libs" in *libEGL.so.1*) ;; *) missing="$missing libegl1";; esac
fi
if [ -n "$missing" ]; then
    echo "LinuxVR-ViewShot: es fehlen Systembibliotheken für Qt6:$missing" >&2
    echo "  Debian/Ubuntu/Mint:  sudo apt install$missing" >&2
    echo "Versuche trotzdem zu starten ..." >&2
fi

exec "$HERE/usr/bin/linuxvr-viewshot" "$@"
APPRUN
chmod +x "$BUILD_DIR/AppRun"

# 6. AppImage bauen – mit Update-Info für Delta-Updates (zsync)
#   gh-releases-zsync | Benutzer | Repo | latest | Dateimuster
# BEIDE Dateien (AppImage + .zsync) gehören ins GitHub-Release.
UPDATE_INFO="gh-releases-zsync|yakuda-stack|LinuxVR-ViewShot|latest|LinuxVR-ViewShot-*${ARCH}.AppImage.zsync"
UPDATE_ARGS=()
if [ -z "${VS_NO_ZSYNC:-}" ]; then
    UPDATE_ARGS=(-u "$UPDATE_INFO")
fi
echo "[5/6] Baue AppImage..."
(cd "$OUT_DIR" && ARCH="$ARCH" "$APPIMAGETOOL" --runtime-file "$RUNTIME" \
    "${UPDATE_ARGS[@]}" "$BUILD_DIR" "$OUT")

# 7. Gegenproben
echo ""
echo "[6/6] Prüfe das Ergebnis..."
if head -c 400000 "$OUT" | strings | grep -q "libfuse\.so\.2"; then
    echo "WARNUNG: Die AppImage verweist noch auf libfuse.so.2 — Runtime nicht statisch."
else
    echo "✔ Runtime ist statisch (läuft mit fuse2 UND fuse3)"
fi
if [ -z "${VS_NO_ZSYNC:-}" ]; then
    EMBEDDED="$(env -u APPIMAGE_EXTRACT_AND_RUN "$OUT" \
        --appimage-updateinformation 2>/dev/null || true)"
    if [ "$EMBEDDED" = "$UPDATE_INFO" ]; then
        echo "✔ Update-Info eingebettet: $EMBEDDED"
    else
        echo "WARNUNG: Update-Info fehlt in der AppImage (gelesen: '$EMBEDDED')."
    fi
    if [ -s "$OUT.zsync" ]; then
        echo "✔ Delta-Update-Datei: build/$(basename "$OUT").zsync"
    else
        echo "WARNUNG: keine .zsync erzeugt — Delta-Updates gehen so nicht."
    fi
fi

rm -rf "$BUILD_DIR"

echo "✔ Fertig: build/$(basename "$OUT")  ($(du -h "$OUT" | cut -f1))"
if [ -s "$OUT.zsync" ]; then
    echo "   Ins GitHub-Release: $(basename "$OUT") UND $(basename "$OUT").zsync"
fi
echo "   Zum Starten: chmod +x \"$OUT\" && \"$OUT\""
echo "   Ohne FUSE testen: APPIMAGE_EXTRACT_AND_RUN=1 \"$OUT\""
