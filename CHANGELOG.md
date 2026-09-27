# Changelog

## [v0.4.3] – unreleased
- **Fix – new VR photo not shown ("Take a photo in VR first"):** the app noticed the photo while it was still being written. It now waits until the file is complete; text/QR detection no longer runs on half-written files
- VR layer saves photos atomically (hidden `.part` file → rename) – needs *Rebuild & install* once

## [v0.4.2] – 2026-09-27
- **AppImage** (any distro, no Rust needed): the finished VR layer is inside; **Install** copies it to `~/.local`, after an AppImage update it is refreshed automatically
- **Fix – VR layer not loaded in VRChat with the AUR package:** Steam/Proton games run in Steam's container and can't see `/usr`. The package no longer registers the layer system-wide; the app copies it to `~/.local` (like the AppImage). Old system-wide registrations are detected and shown
- **Fix:** after *Rebuild & install* the button stayed disabled – *Remove → Install* works again
- **Fix:** text recognition crashed with newer omegaconf versions ("PosixPath is not a supported primitive type")

## [v0.4.1] – 2026-09-27
- Main: status, photo count and buttons in one compact row; new **Remove** button for the VR layer
- AUR package `linuxvr-viewshot` (system-wide); the app hides "Rebuild" when installed from a package and warns if the layer is installed twice
- Tests: pytest + smoke test; fixed a crash on exit in the smoke test (mouse-wheel filter is now removed before Qt shuts down)
- README with screenshots

## [v0.4.0] – 2026-09-27
First public release.

### VR (OpenXR layer)
- Hand-frame gesture: hold both grips → red frame → shutter trigger takes the photo
- Shutter on left / right / both triggers (default: right)
- Manual photo type: icon in the frame corner (🖼 / 📝 / 🔳), switched with a second trigger; stored in the PNG
- Frame size, eye (left/right) and excluded apps change live via `layer.json`

### Desktop app
- Main: last photo with OCR + translation (Lingva, Google, LibreTranslate, DeepL, custom API), QR codes with open/copy
- Gallery: equal tiles, large view, copy / share / upload (directupload.eu) / info / delete, filter by type, bulk select → delete or set type
- Image detection: text / QR / image tags, VRChat nameplates don't count as text
- Clean up QR / text photos on exit (optional)
- WayVR: Cubee's theme + a watch button that opens this app inside VR
- App icon, correct name in task managers, EN/DE

### Install
- `install.sh` for `curl | bash` (install / update / uninstall), AUR package `linuxvr-viewshot`
