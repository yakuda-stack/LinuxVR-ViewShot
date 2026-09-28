<p align="center">
  <img src="UI/assets/linuxvr-viewshot.png" width="128" alt="LinuxVR-ViewShot icon">
</p>

<h1 align="center">LinuxVR-ViewShot</h1>

<p align="center">
  <b>Take photos in VR with a hand-frame gesture – on Linux (WiVRn / Monado).</b><br>
  A Linux alternative to VRHandsFrame: an OpenXR API layer + a desktop app for your photos.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="License: GPL-3.0"></a>
  <img src="https://img.shields.io/badge/platform-Linux-informational" alt="Platform: Linux">
  <img src="https://img.shields.io/badge/OpenXR-API%20layer-orange" alt="OpenXR API layer">
  <a href="https://github.com/yakuda-stack/LinuxVR-ViewShot/releases"><img src="https://img.shields.io/github/v/tag/yakuda-stack/LinuxVR-ViewShot?label=version&color=success" alt="Version"></a>
  <a href="https://discord.gg/ShNKvvZu74"><img src="https://img.shields.io/badge/Discord-join-5865F2" alt="Discord"></a>
</p>

<p align="center"><a href="#-english">🇬🇧 English</a> · <a href="#-deutsch">🇩🇪 Deutsch</a> · <a href="#-screenshots">📷 Screenshots</a></p>

<p align="center">
  <img src="assets/main.png" width="900" alt="Main page: last photo with text recognition and translation">
</p>

---

## 🇬🇧 English

### ⚡ Quick install
```bash
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash
```
- **No sudo** – everything goes into your home folder
- Checks the dependencies and prints the install command for your distro if something is missing
- Builds the OpenXR layer, adds **LinuxVR-ViewShot** to your app menu and the command `linuxvr-viewshot`
- **Update:** run the same line again
- **Arch Linux (AUR):** `yay -S linuxvr-viewshot`, then open the app once and press **Install**
- **AppImage** (any distro, no Rust needed): download it from [Releases](https://github.com/yakuda-stack/LinuxVR-ViewShot/releases), `chmod +x`, start it and press **Install**

**Needs:** `git`, `python3` + **PyQt6**, **rust/cargo** – Arch: `sudo pacman -S --needed git python-pyqt6 rust`
**Optional:** text recognition for the translation – `pip install --user rapidocr onnxruntime`

After installing, **restart your VR game** so the layer gets loaded.

<details><summary>Uninstall · install from a clone</summary>

```bash
# uninstall (photos + settings stay)
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash -s -- uninstall

# install from a clone
git clone https://github.com/yakuda-stack/LinuxVR-ViewShot.git
cd LinuxVR-ViewShot && ./install.sh          # ./install.sh uninstall
```
</details>

### 🙌 How it works
1. Hold **grip on both controllers** – don't touch trigger, A/B/X/Y or thumbstick
2. Hands at least ~15 cm apart for 0.4 s → short vibration, **red frame** appears
3. Press the **shutter trigger** (default: right) → **photo!** The frame flashes white
4. The area between your hands lands as PNG in `~/Pictures/LinuxVR-ViewShot/`

### ✨ Features

**In VR**

- 📸 Photo of the area **between** your hands – fingers stay outside, like a camera frame
- 👀 Frame matches what you see with both eyes; the red frame is never in the photo
- 🎮 Shutter on left / right / both triggers
- ✋ **Manual mode:** an icon (🖼 / 📝 / 🔳) in the frame corner (corner selectable: bottom-left/right, top-left/right), a second trigger switches the type – the photo is tagged with it
- ⚙️ Frame size and eye change **live**, even while the game is running
- Works with OpenXR games and OpenVR games via xrizer / OpenComposite · Quest/Touch, Pico, Index, Vive, WMR

**Desktop app**

- 🏠 **Main:** newest photo, status in one row (📁 photo folder · 🔧 rebuild · 🗑 remove layer), pick another photo with 📁 / 🖼
- 🌐 **Translation:** text in the photo is recognised (RapidOCR) and translated – Lingva, Google, LibreTranslate (local/Docker on port 5000 is found automatically), DeepL or your own API; *From → To* and *Service* right next to the photo – the dropdown only lists services that are set up – or only your ⭐ **favourites** (Options → Translation)
- 🤖 **AI translation:** Claude Code (Opus / Sonnet / Haiku), Gemini CLI, ChatGPT (Codex CLI) with your own login – or any command (e.g. `ollama run … {prompt}`). **Install** and **Sign in** buttons (npm, no sudo), model choice right next to *Service*; if the AI fails, the service switches to the one that translated
- 🧠 **AI task** next to it: translate · explain context · answer a question in the photo (quiz, riddle …)
- 📋 **Copy** button right above the translation · *Recognised text* folds away (▸, folded by default)
- ↻ **Send again** (fresh answer); stuck AI requests are re-sent automatically (optional, per AI)
- 🕘 **History** (optional): past translations, tap to show them again, ⧉ opens it in its own window · ✏ fix the **recognised text** yourself and translate it again
- ⧉ **Pop out** the translation into its own window (in VR: its own panel)
- 🔳 **QR codes** in a photo appear as **clickable links** right in the translation (📋 copy)
- 📋 **Clipboard from WayVR:** copied things also land on the desktop (via `wl-copy`, package `wl-clipboard` – **install button** in Options for Arch, Fedora, Debian/Ubuntu, openSUSE) – Ctrl+V works there
- 🖼 **Gallery:** equal tiles with size slider, large view with ‹ ›, **Copy · Share · Upload & copy link** ([directupload.eu](https://www.directupload.eu/), incl. delete link) **· Info · Delete** (trash)
- 🏷️ **Image detection:** every photo gets 📝 text / 🔳 QR / 🖼 image – VRChat nameplates don't count as text; filter the gallery, change tags in *Info*
- ☑ **Bulk select:** tap tiles → delete them all or set their type
- 🧹 **Clean up on exit** (optional): QR / text photos go to the trash when you close the app
- 🎨 **WayVR:** installs [Cubee's WayVR theme](https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr) + a watch button that opens this app **inside VR**
- 🥽 Made for the VR laser: big buttons, wide sidebar, the mouse wheel never changes dropdowns by accident · EN / DE

### 💡 Tips
- Turn it off for one game: `DISABLE_LINUXVR_VIEWSHOT=1 %command%`
- Excluded apps (default `wayvr`): Options → Shot → *Exceptions*
- Log file: `~/.local/state/linuxvr-viewshot/layer.log` · settings: `~/.config/linuxvr-viewshot/`

### ⚠️ Limits
- The VR layer always lives in `~/.local` – Steam/Proton games (VRChat) run in Steam's container and can't see a layer in `/usr`
- Vulkan games only, 8-bit colour formats (RGBA8 / BGRA8)
- The trigger press also reaches the game

---

## 🇩🇪 Deutsch

### ⚡ Schnell-Installation
```bash
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash
```
- **Kein sudo** – alles landet in deinem Home-Ordner
- Prüft die Abhängigkeiten und zeigt den Installationsbefehl für deine Distro, falls etwas fehlt
- Baut den OpenXR-Layer, legt **LinuxVR-ViewShot** ins Startmenü und den Befehl `linuxvr-viewshot` an
- **Update:** dieselbe Zeile nochmal ausführen
- **Arch Linux (AUR):** `yay -S linuxvr-viewshot`, dann die App einmal öffnen und **Installieren** drücken
- **AppImage** (jede Distro, ohne Rust): unter [Releases](https://github.com/yakuda-stack/LinuxVR-ViewShot/releases) laden, `chmod +x`, starten und **Installieren** drücken

**Braucht:** `git`, `python3` + **PyQt6**, **rust/cargo** – Arch: `sudo pacman -S --needed git python-pyqt6 rust`
**Optional:** Texterkennung für die Übersetzung – `pip install --user rapidocr onnxruntime`

Nach der Installation das **VR-Spiel neu starten**, damit der Layer geladen wird.

<details><summary>Entfernen · aus einem Klon installieren</summary>

```bash
# entfernen (Fotos + Einstellungen bleiben)
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash -s -- uninstall

# aus einem Klon installieren
git clone https://github.com/yakuda-stack/LinuxVR-ViewShot.git
cd LinuxVR-ViewShot && ./install.sh          # ./install.sh uninstall
```
</details>

### 🙌 So funktioniert's
1. **Grip an beiden Controllern** halten – Trigger, A/B/X/Y und Stick nicht anfassen
2. Hände mind. ~15 cm auseinander, 0,4 s halten → kurzes Vibrieren, **roter Rahmen** erscheint
3. **Auslöser-Trigger** drücken (Standard: rechts) → **Foto!** Der Rahmen blitzt weiß
4. Der Bereich zwischen den Händen landet als PNG in `~/Bilder/LinuxVR-ViewShot/`

### ✨ Funktionen

**In VR**

- 📸 Foto vom Bereich **zwischen** den Händen – Finger bleiben draußen, wie bei einem Kamera-Rahmen
- 👀 Ausschnitt passt zu dem, was du mit beiden Augen siehst; der rote Rahmen ist nie im Foto
- 🎮 Auslöser auf linkem / rechtem / beiden Triggern
- ✋ **Manueller Modus:** Symbol in der Rahmen-Ecke (🖼 / 📝 / 🔳, Ecke wählbar: unten links/rechts, oben links/rechts), ein zweiter Trigger schaltet den Typ um – das Foto wird damit getaggt
- ⚙️ Rahmengröße und Auge ändern sich **live**, auch während das Spiel läuft
- Läuft mit OpenXR-Spielen und OpenVR-Spielen über xrizer / OpenComposite · Quest/Touch, Pico, Index, Vive, WMR

**Desktop-App**

- 🏠 **Main:** neuestes Foto, Status in einer Zeile (📁 Foto-Ordner · 🔧 Neu bauen · 🗑 Layer entfernen), anderes Foto über 📁 / 🖼 wählen
- 🌐 **Übersetzung:** Text im Foto wird erkannt (RapidOCR) und übersetzt – Lingva, Google, LibreTranslate (lokal/Docker auf Port 5000 wird automatisch gefunden), DeepL oder eigene API; *Von → Nach* und *Dienst* direkt neben dem Foto – im Dropdown stehen nur eingerichtete Dienste – oder nur deine ⭐ **Favoriten** (Optionen → Übersetzung)
- 🤖 **KI-Übersetzung:** Claude Code (Opus / Sonnet / Haiku), Gemini CLI, ChatGPT (Codex CLI) mit deinem Login – oder ein beliebiger Befehl (z. B. `ollama run … {prompt}`). Knöpfe **Installieren** und **Anmelden** (npm, ohne sudo), Modell direkt neben *Dienst*; geht die KI nicht, stellt sich der Dienst auf den um, der übersetzt hat
- 🧠 **KI-Aufgabe** daneben: übersetzen · Kontext erklären · Frage im Foto beantworten (Quiz, Rätsel …)
- 📋 **Kopieren**-Knopf direkt über der Übersetzung · *Erkannter Text* einklappbar (▸, standardmäßig zu)
- ↻ **Nochmal senden** (neue Antwort); hängt die KI, wird automatisch neu gesendet (optional, je KI)
- 🕘 **Verlauf** (optional): frühere Übersetzungen, antippen zeigt sie wieder, ⧉ öffnet ihn in einem eigenen Fenster · ✏ **erkannten Text** selbst korrigieren und neu übersetzen
- ⧉ Übersetzung in ein **eigenes Fenster** ausklinken (in VR: eigenes Panel)
- 🔳 **QR-Codes** im Foto stehen als **anklickbare Links** direkt in der Übersetzung (📋 kopieren)
- 📋 **Zwischenablage aus WayVR:** Kopiertes landet auch auf dem Desktop (per `wl-copy`, Paket `wl-clipboard` – **Installier-Knopf** in den Optionen für Arch, Fedora, Debian/Ubuntu, openSUSE) – Strg+V klappt dort
- 🖼 **Galerie:** gleich große Kacheln mit Größen-Slider, große Ansicht mit ‹ ›, **Kopieren · Teilen · Hochladen & Link kopieren** ([directupload.eu](https://www.directupload.eu/), inkl. Lösch-Link) **· Info · Löschen** (Papierkorb)
- 🏷️ **Bild-Erkennung:** jedes Foto bekommt 📝 Text / 🔳 QR / 🖼 Bild – VRChat-Namensschilder zählen nicht als Text; Galerie danach filtern, Tags unter *Info* ändern
- ☑ **Mehrfach-Auswahl:** Kacheln antippen → alle löschen oder ihren Typ setzen
- 🧹 **Beim Beenden aufräumen** (optional): QR- / Text-Fotos kommen beim Schließen in den Papierkorb
- 🎨 **WayVR:** installiert [Cubees WayVR-Design](https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr) + einen Uhr-Knopf, der diese App **in VR** öffnet
- 🥽 Für den VR-Laser gemacht: große Knöpfe, breite Seitenleiste, das Mausrad verstellt keine Dropdowns aus Versehen · EN / DE

### 💡 Tipps
- Für ein Spiel abschalten: `DISABLE_LINUXVR_VIEWSHOT=1 %command%`
- Ausgenommene Programme (Standard `wayvr`): Optionen → Shot → *Ausnahmen*
- Log-Datei: `~/.local/state/linuxvr-viewshot/layer.log` · Einstellungen: `~/.config/linuxvr-viewshot/`

### ⚠️ Grenzen
- Der VR-Layer liegt immer in `~/.local` – Steam-/Proton-Spiele (VRChat) laufen im Steam-Container und sehen einen Layer in `/usr` nicht
- Nur Vulkan-Spiele, 8-Bit-Farbformate (RGBA8 / BGRA8)
- Der Trigger-Druck kommt auch im Spiel an

---

## 📷 Screenshots

<table>
  <tr>
    <td width="50%"><img src="assets/gallery.png" alt="Gallery with filter and size slider"></td>
    <td width="50%"><img src="assets/galerybig.png" alt="Large view with copy, share, upload, info and delete"></td>
  </tr>
  <tr>
    <td align="center"><b>Gallery / Galerie</b> – filter 📝 🔳 🖼, size slider, bulk select</td>
    <td align="center"><b>Large view / Große Ansicht</b> – copy, share, upload, info, delete</td>
  </tr>
  <tr>
    <td width="50%"><img src="assets/trans.png" alt="Translation options"></td>
    <td width="50%"><img src="assets/shot%20settings.png" alt="Shot options: frame size, eye, triggers"></td>
  </tr>
  <tr>
    <td align="center"><b>Translation / Übersetzung</b> – LibreTranslate, DeepL, Google, Lingva, own API</td>
    <td align="center"><b>Shot</b> – frame size, eye, triggers, manual mode</td>
  </tr>
  <tr>
    <td colspan="2"><img src="assets/general.png" alt="General options: community, language, folders, clean up, WayVR"></td>
  </tr>
  <tr>
    <td colspan="2" align="center"><b>General</b> – language, folders, clean up on exit, WayVR theme + watch button</td>
  </tr>
</table>

---

## 🗂️ Project layout / Aufbau
```
install.sh        curl | bash installer (install / update / uninstall)
layer/            OpenXR API layer (Rust)
  src/lib.rs        OpenXR hooks (entry point)
  src/gesture.rs    gesture + trigger state machine (tested)
  src/frame.rs      hands → image rectangle, frame + icon quads (tested)
  src/capture.rs    Vulkan copy GPU ↔ RAM
  src/save.rs       pixel conversion + PNG (with photo type)
  src/icons.rs      manual photo type + frame icons
  src/config.rs     layer.json (reloaded live)
  assets/           frame icons (image / text / QR)
UI/               desktop app (PyQt6)
  start.sh          start (sets the process name, see starter.py)
  core/             paths, config, EN/DE texts, OCR, translation, tags, WayVR theme
  ui/               window, style, pages (main / gallery / options)
manifest/         OpenXR layer manifest template
packaging/        .desktop template, aur/PKGBUILD (+ README-AUR.md)
scripts/          install-layer.sh, build_appimage.sh, bump_version.py
tests/            pytest + smoke test (python3 -m pytest -q, python3 tests/smoke.py)
assets/           README screenshots
```

## 🙏 Credits
- Inspired by **VRHandsFrame**
- WayVR theme: [**Cubee**](https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr) (GPL-3.0) – downloaded on demand, not bundled
- Translators shared with [**OSC-DreamChatbox**](https://github.com/yakuda-stack/OSC-DreamChatbox)
- Text recognition: [RapidOCR](https://github.com/RapidAI/RapidOCR) · Image hosting: [directupload.eu](https://www.directupload.eu/)

## 📄 License
[GPL-3.0](LICENSE) © Yakuda

> 🤖 **Transparency Note:** This project is developed with the support of AI coding assistants (**Claude by Anthropic**).
