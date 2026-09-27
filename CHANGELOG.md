# Changelog

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
