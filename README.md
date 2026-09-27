<p align="center">
  <img src="UI/assets/linuxvr-viewshot.png" width="128" alt="LinuxVR-ViewShot icon">
</p>

<h1 align="center">LinuxVR-ViewShot</h1>

<p align="center">
  <b>Take photos in VR with a hand-frame gesture – on Linux (WiVRn / Monado).</b><br>
  A Linux alternative to VRHandsFrame, built as an OpenXR API layer + desktop app.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="License: GPL-3.0"></a>
  <img src="https://img.shields.io/badge/platform-Linux-informational" alt="Platform: Linux">
  <img src="https://img.shields.io/badge/OpenXR-API%20layer-orange" alt="OpenXR API layer">
  <a href="https://discord.gg/ShNKvvZu74"><img src="https://img.shields.io/badge/Discord-join-5865F2" alt="Discord"></a>
</p>

<p align="center"><a href="#-english">🇬🇧 English</a> · <a href="#-deutsch">🇩🇪 Deutsch</a></p>

---

## 🇬🇧 English

### Quick install
```bash
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash
```
No sudo needed – everything goes into your home folder. The script checks the dependencies (and prints the install command for your distro if something is missing), downloads the project to `~/.local/share/linuxvr-viewshot/app`, builds the OpenXR layer and adds **LinuxVR-ViewShot** to your app menu plus the command `linuxvr-viewshot`.

**Needs:** `git`, `python3` + **PyQt6**, **rust/cargo** – e.g. Arch: `sudo pacman -S --needed git python-pyqt6 rust`
**Optional** (text recognition for the translation): `pip install --user rapidocr onnxruntime`

**Update:** run the same line again · **Uninstall** (photos + settings stay):
```bash
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash -s -- uninstall
```
<details><summary>Install from a clone instead</summary>

```bash
git clone https://github.com/yakuda-stack/LinuxVR-ViewShot.git
cd LinuxVR-ViewShot
./install.sh            # or: ./install.sh uninstall
```
</details>

After installing, **restart your VR game** so the layer gets loaded.

### How it works
1. Hold **grip on both controllers** – don't touch trigger, A/B/X/Y or thumbstick.
2. Keep your hands at least ~15 cm apart for 0.4 s → short vibration + **red frame** appears.
3. Press the **shutter trigger** (default: right) → photo! (stronger vibration, frame flashes white)
4. The area between your hands is saved as PNG to `~/Pictures/LinuxVR-ViewShot/`.

### Features
- 📸 Photo of the area **between** your hands – fingers stay outside (like a camera frame)
- 👀 Frame matches what you see with both eyes (center-eye projection)
- 🟥 Visible red frame in VR – never part of the photo
- Works with OpenXR games and OpenVR games via xrizer / OpenComposite
- Controllers: Quest/Touch, Pico 4 / Neo 3, Index, Vive, WMR

### Desktop app
**Main** (status + last photo, 🔧 **Install / Rebuild & install** button for the layer with live output) · **Gallery** (equal tiles, 🔍 size slider – bigger tiles are easier to hit in VR, click = large view with ‹ › / arrow keys) · **Options** (language, folders)

Wide sidebar with large buttons – easy to click with the VR laser.

Large view buttons (big enough for the VR laser):
- 📋 **Copy** – image to clipboard
- ↗ **Share** – Discord (paste with Ctrl+V), Telegram, e-mail
- ☁ **Upload & copy link** – to [directupload.eu](https://www.directupload.eu/), shows image link + delete link
- ⓘ **Info** – date taken, resolution, file size
- 🗑 **Delete** – moves the photo to the trash (asks first), jumps to the next photo instantly
- ↻ **Check upload** – checks whether the uploaded image still exists; if it was deleted online, the links disappear and the upload button returns

Clicking **Gallery** in the sidebar always returns to the tile view – handy in VR.

**Options** tabs: **General** (Discord, Ko-fi, VRChat group, GitHub, language, folders) · **Shot** (frame size slider, left/right eye slider, exception list – `wayvr` by default) · **Translation** (Lingva, Google, LibreTranslate local/online, DeepL, custom API – target language, auto-translate, test button).

🌐 **Translation:** the text in the newest photo is recognised (RapidOCR, PP-OCRv6) and translated – shown on **Main** next to the photo, with **From → To** in one row and **Service** below, right there; keys and servers come from Options. A LibreTranslate server on port 5000 (e.g. Docker) is detected automatically. If the chosen service fails, Lingva/Google take over automatically. The translators are shared with OSC-DreamChatbox.

📁 🖼 **Other photo:** next to *Last photo* on Main, 📁 opens a file picker and 🖼 a small gallery – the chosen image is shown and translated. Without a choice (or after *✕ Last photo*) the newest photo is used.

🔳 **QR codes:** if the photo on Main contains a QR code, a row with its content appears below it – **Open** for links, **Copy** for other text. The photo on Main grows with the window.

🏷️ **Image detection:** every photo is tagged in the background as 📝 text to translate, 🔳 QR code or 🖼 plain image – icons show on the gallery tiles. VRChat nameplates (names, pronouns, ranks, groups) don't count as text. **Info** in the gallery shows the tags; click to change them or *Detect again*.

🔎 **Gallery filter & bulk delete:** filter tiles by 📝 / 🔳 / 🖼. **☑ Select** → tap tiles (red frame + ✓) → **🗑 Delete (n)** moves them all to the trash, or **🏷 Type** sets them all to 📝 / 🔳 / 🖼. **ⓘ** next to the photo on Main opens the same info window with the tags.

🧹 **Clean up on exit** (Options → General, off by default): move QR code and/or text photos to the trash when the app closes – photos also tagged 🖼 Image are kept.

🎮 **Buttons & manual type:** Options → Shot → *Detection & buttons*: choose which trigger takes the photo (left / right / both, default **right**). Detection **🤖 automatic** (the app detects text / QR / image) or **✋ manual** (also switchable next to *Last photo* on Main): the frame shows an icon in its bottom-right corner, the type trigger (default **left**) switches 🖼 → 📝 → 🔳, and the photo is tagged with it (stored in the PNG, no OCR needed). Needs a one-time layer rebuild.

🎨 **WayVR theme by Cubee:** Options → General → *Install WayVR theme + app button on the watch* downloads [Cubee's WayVR theme](https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr) (watch, colours, sounds) into `~/.config/wayvr` (old files are backed up). The watch's *Open Chatbox* button becomes a **LinuxVR-ViewShot** button that opens this app as a window inside WayVR (`wayvrctl process-launch`). Your own WayVR settings and controller bindings are kept.

🖱️ **Mouse wheel:** scrolling over a dropdown or slider scrolls the page and never changes the value by accident.

Shot settings are stored in `~/.config/linuxvr-viewshot/layer.json` and apply **instantly**, even while the game is running.

### Tips
- Disable temporarily: start the game with `DISABLE_LINUXVR_VIEWSHOT=1 %command%`
- Frame margin override for testing (default: Options → Shot): `VIEWSHOT_INSET_CM=5 %command%`
- Log file: `~/.local/state/linuxvr-viewshot/layer.log`

### Limits
- Vulkan games only; 8-bit color formats (RGBA8/BGRA8)
- The trigger press also reaches the game

---

## 🇩🇪 Deutsch

### Schnell-Installation
```bash
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash
```
Kein sudo nötig – alles landet in deinem Home-Ordner. Das Skript prüft die Abhängigkeiten (und zeigt den Installationsbefehl für deine Distro, falls etwas fehlt), lädt das Projekt nach `~/.local/share/linuxvr-viewshot/app`, baut den OpenXR-Layer und legt **LinuxVR-ViewShot** ins Startmenü plus den Befehl `linuxvr-viewshot`.

**Braucht:** `git`, `python3` + **PyQt6**, **rust/cargo** – z. B. Arch: `sudo pacman -S --needed git python-pyqt6 rust`
**Optional** (Texterkennung für die Übersetzung): `pip install --user rapidocr onnxruntime`

**Update:** dieselbe Zeile nochmal ausführen · **Entfernen** (Fotos + Einstellungen bleiben):
```bash
curl -fsSL https://raw.githubusercontent.com/yakuda-stack/LinuxVR-ViewShot/main/install.sh | bash -s -- uninstall
```
<details><summary>Stattdessen aus einem Klon installieren</summary>

```bash
git clone https://github.com/yakuda-stack/LinuxVR-ViewShot.git
cd LinuxVR-ViewShot
./install.sh            # oder: ./install.sh uninstall
```
</details>

Nach der Installation das **VR-Spiel neu starten**, damit der Layer geladen wird.

### So funktioniert's
1. **Grip an beiden Controllern** halten – Trigger, A/B/X/Y und Stick nicht anfassen.
2. Hände mind. ~15 cm auseinander, 0,4 s halten → kurzes Vibrieren + **roter Rahmen** erscheint.
3. **Auslöser-Trigger** drücken (Standard: rechts) → Foto! (stärkeres Vibrieren, Rahmen blitzt weiß)
4. Der Bereich zwischen den Händen landet als PNG in `~/Bilder/LinuxVR-ViewShot/`.

### Funktionen
- 📸 Foto vom Bereich **zwischen** den Händen – Finger bleiben draußen (wie ein Kamera-Rahmen)
- 👀 Ausschnitt passt zu dem, was du mit beiden Augen siehst (Mittelauge)
- 🟥 Sichtbarer roter Rahmen in VR – ist nie mit im Foto
- Läuft mit OpenXR-Spielen und OpenVR-Spielen über xrizer / OpenComposite
- Controller: Quest/Touch, Pico 4 / Neo 3, Index, Vive, WMR

### Desktop-App
**Main** (Status + letztes Foto, 🔧 Knopf **Installieren / Neu bauen & installieren** für den Layer mit Live-Ausgabe) · **Galerie** (gleich große Kacheln, 🔍 Größen-Slider – größere Kacheln sind in VR leichter zu treffen, Klick = große Ansicht mit ‹ › / Pfeiltasten) · **Optionen** (Sprache, Ordner)

Breite Seitenleiste mit großen Knöpfen – gut mit dem VR-Laser zu treffen.

Knöpfe in der großen Ansicht (groß genug für den VR-Laser):
- 📋 **Kopieren** – Bild in die Zwischenablage
- ↗ **Teilen** – Discord (mit Strg+V einfügen), Telegram, E-Mail
- ☁ **Hochladen & Link kopieren** – zu [directupload.eu](https://www.directupload.eu/), zeigt Bild-Link + Lösch-Link
- ⓘ **Info** – Aufnahmezeit, Auflösung, Dateigröße
- 🗑 **Löschen** – verschiebt das Foto in den Papierkorb (fragt vorher), springt sofort zum nächsten Foto
- ↻ **Upload prüfen** – prüft, ob das hochgeladene Bild noch online ist; wurde es gelöscht, verschwinden die Links und der Upload-Knopf ist wieder da

Klick auf **Galerie** links bringt immer zur Kachel-Ansicht zurück – praktisch in VR.

**Optionen**-Tabs: **General** (Discord, Ko-fi, VRChat-Gruppe, GitHub, Sprache, Ordner) · **Shot** (Slider für Rahmengröße, Slider linkes/rechtes Auge, Ausnahme-Liste – Standard `wayvr`) · **Übersetzung** (Lingva, Google, LibreTranslate lokal/online, DeepL, eigene API – Zielsprache, automatisch übersetzen, Test-Knopf).

🌐 **Übersetzung:** Der Text im neuesten Foto wird erkannt (RapidOCR, PP-OCRv6) und übersetzt – auf **Main** rechts neben dem Foto, mit **Von → Nach** in einer Zeile (Standard: automatisch erkennen) und **Dienst** darunter; Keys und Server kommen aus den Optionen. Ein LibreTranslate-Server auf Port 5000 (z. B. Docker) wird automatisch erkannt. Fällt der gewählte Dienst aus, springen Lingva/Google automatisch ein. Die Übersetzer sind dieselben wie in OSC-DreamChatbox.

📁 🖼 **Anderes Foto:** Neben *Letztes Foto* auf Main öffnet 📁 die Dateiauswahl und 🖼 eine kleine Galerie – das gewählte Bild wird angezeigt und übersetzt. Ohne Auswahl (oder nach *✕ Letztes Foto*) wird das neueste Foto genommen.

🔳 **QR-Codes:** Ist im Foto auf Main ein QR-Code, erscheint darunter eine Zeile mit dem Inhalt – **Öffnen** bei Links, **Kopieren** bei anderem Text. Das Foto auf Main wächst mit dem Fenster mit.

🏷️ **Bild-Erkennung:** Jedes Foto wird im Hintergrund getaggt: 📝 Text zum Übersetzen, 🔳 QR-Code oder 🖼 normales Bild – die Symbole stehen unter den Galerie-Kacheln. VRChat-Namensschilder (Namen, Pronomen, Ränge, Gruppen) zählen nicht als Text. Unter **Info** in der Galerie sieht man die Tags, kann sie per Klick ändern oder *Neu erkennen*.

🔎 **Galerie-Filter & Mehrfach-Löschen:** Kacheln nach 📝 / 🔳 / 🖼 filtern. **☑ Auswählen** → Kacheln antippen (roter Rahmen + ✓) → **🗑 Löschen (n)** schiebt alle in den Papierkorb, oder **🏷 Typ** setzt alle auf 📝 / 🔳 / 🖼. **ⓘ** neben dem Foto auf Main öffnet dasselbe Info-Fenster mit den Tags.

🧹 **Beim Beenden aufräumen** (Optionen → General, Standard aus): QR-Code- und/oder Text-Fotos beim Schließen in den Papierkorb – Fotos, die zusätzlich 🖼 Bild getaggt sind, bleiben.

🎮 **Tasten & manueller Typ:** Optionen → Shot → *Erkennung & Tasten*: welcher Trigger das Foto auslöst (links / rechts / beide, Standard **rechts**). Erkennung **🤖 automatisch** (die App erkennt Text / QR / Bild) oder **✋ manuell** (auch neben *Letztes Foto* auf Main umschaltbar): Im Rahmen erscheint unten rechts ein Symbol, der Typ-Trigger (Standard **links**) schaltet 🖼 → 📝 → 🔳 um, und das Foto wird damit getaggt (steht im PNG, keine OCR nötig). Einmal den Layer neu bauen.

🎨 **WayVR-Design von Cubee:** Optionen → General → *WayVR-Design + App-Knopf auf der Uhr installieren* lädt [Cubees WayVR-Design](https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr) (Uhr, Farben, Sounds) nach `~/.config/wayvr` (alte Dateien kommen ins Backup). Der Knopf *Chatbox öffnen* auf der Uhr wird zu einem **LinuxVR-ViewShot**-Knopf, der diese App als Fenster in WayVR öffnet (`wayvrctl process-launch`). Eigene WayVR-Einstellungen und die Controller-Belegung bleiben.

🖱️ **Mausrad:** Scrollen über Dropdowns oder Slidern scrollt die Seite – der Wert ändert sich nicht mehr aus Versehen.

Shot-Einstellungen liegen in `~/.config/linuxvr-viewshot/layer.json` und wirken **sofort**, auch während das Spiel läuft.

### Tipps
- Kurz abschalten: Spiel mit `DISABLE_LINUXVR_VIEWSHOT=1 %command%` starten
- Rand zum Testen überschreiben (sonst Optionen → Shot): `VIEWSHOT_INSET_CM=5 %command%`
- Log-Datei: `~/.local/state/linuxvr-viewshot/layer.log`

### Grenzen
- Nur Vulkan-Spiele; 8-Bit-Farbformate (RGBA8/BGRA8)
- Der Trigger-Druck kommt auch im Spiel an

---

## Project layout / Aufbau
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
manifest/         OpenXR layer manifest template
packaging/        .desktop template
scripts/          install-layer.sh (build + register the layer)
UI/               desktop app (PyQt6)
  start.sh          start (sets the process name, see starter.py)
  assets/           app icon
  core/             paths, config, EN/DE texts, OCR, translation, tags, WayVR theme
  ui/               window, style, pages (main / gallery / options)
```

## Credits
- Inspired by **VRHandsFrame**
- WayVR theme: [**Cubee**](https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr) (GPL-3.0) – downloaded on demand, not bundled
- Translators shared with [**OSC-DreamChatbox**](https://github.com/yakuda-stack)
- Text recognition: [RapidOCR](https://github.com/RapidAI/RapidOCR) · Image hosting: [directupload.eu](https://www.directupload.eu/)

## License
[GPL-3.0](LICENSE) © Yakuda

> 🤖 **Transparency Note:** This project is developed with the support of AI coding assistants (**Claude by Anthropic**).
