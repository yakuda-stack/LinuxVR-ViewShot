# Changelog

## [v0.4.6] – 2026-09-28
- **RUST ERROR** new rust patch

## [v0.4.5] – 2026-09-28
- **🔁 Lens** (live translation): the type trigger now works in automatic mode too – 🪄 Auto ↔ 🔁 Lens (manual: 🖼 → 📝 → 🔳 → 🔁 Lens). With 🔁 the shutter takes no photo but photographs the same area again every 1–10 s (Options → Shot; blue frame in VR, stays in front of your head) and the app translates it – fastest with LibreTranslate. Pictures go to `live/live.png`, not the gallery; unchanged text isn't translated again. Open a new frame to stop. New icons 🪄 Auto and 🔁 Lens. **Needs a layer rebuild.**
- **AI answers appear live** while Claude / Gemini / a custom command (e.g. Ollama) is still writing (ChatGPT/Codex usually delivers the answer in one piece)
- **☁/🔒 privacy note** for every service (Options → Translation + tooltip in the Main dropdown): whether the recognised text is sent to the internet – only text, never the photo
- Tests: layer.json defaults in Python and Rust are compared automatically; new GitHub Actions workflow runs `cargo test`, `clippy`, `pytest` and the smoke test on every push
- Code: `main_page.py` split into `main_translation.py`, `main_history.py`, `main_install.py`, `main_live.py` (Lens) (+ `ui/panel_window.py`)

## [v0.4.4] – 2026-09-28
- **⭐ Favourite services** (Options → Translation): tick services – then only those appear in the Main dropdown; nothing ticked = as before
- Main: **🕘 History pop-out** – ⧉ opens the history in its own window (in VR its own panel); closing it docks it back
- **Fix – AI task *Answer question* (ChatGPT only):** with a blank (○○) plus answer buttons ChatGPT now names the WHOLE button to click (e.g. 下暗し), not just the missing character; its old saved answers are asked again
- **Fix – Options → Shot:** moving *Frame size* changed the *Eye* label instead of its own, and its *Default* button reset the eye slider
- **Manual mode: icon corner selectable** (Options → Shot): bottom left (new default) / bottom right / top left / top right – applies instantly in VR
- **Fix – history missed photos:** results that were already saved (e.g. text read earlier) now go into the history too; duplicates (same photo + same translation) are skipped
- Main: **🕘 History** card above *How it works* (off by default – Options → Translation): scrollable list of past translations; tap one to show recognised text + translation (no image, the photo may be gone)
- Main: **recognised text is editable** – fix OCR mistakes or type text yourself, then *Translate corrected text* (the correction is remembered for that photo)
- Main: *Recognised text* can be folded (▸ / ▾), folded by default – more room for the translation in VR; the choice is remembered
- Main: **📋 Copy** button right above the translation
- AI: **Send again if it takes longer than … s** (Options → Translation, per AI; off by default, 60 s): a stuck request is cancelled (whole process group) and sent again up to 2×, then Lingva/Google; off = wait up to 300 s
- Main: **↻** button next to the pop-out button – sends again and gets a fresh answer
- AI prompts: short answers, no tools / web search / file reading (Gemini sometimes took minutes); AI timeout 120 s → 60 s, a timeout says when the rate limit (429) was hit
- Main shows what the translation is doing right now (reading text / waiting for image detection / translating with X); new **app log** `~/.local/state/linuxvr-viewshot/ui.log` with timings (Options → General → Folders)
- AI task *Answer question*: made for quiz / puzzle / escape rooms – names the button to click EXACTLY as written in the photo, or what to type into a gap (○○), first line starts with ➜; old saved answers are asked again
- **Fix – Gemini "not running in a trusted directory" (error 55):** the app now runs Gemini in trusted mode; a Gemini API-key login (settings.json / ~/.gemini/.env) counts as signed in; colour codes removed from error messages; the Sign-in terminal starts in the home folder
- **Fix – "No text found" for minutes after start:** at start the background detection reads ALL photos; the translation had to wait until it was done and showed "No text found" meanwhile. The translation now goes first, and "No text found" only appears after text recognition really ran
- **Translation pop-out:** ⧉ opens the translation in its own window (in VR its own panel); closing it docks it back
- **QR codes inside the translation:** links are clickable right in the translation field, 📋 copies – no extra box anymore
- **AI task** (Main, only with an AI service): 🌐 translate · 💡 explain context · ❓ answer a question in the photo (quiz, riddle …, otherwise translate)
- **AI translation:** Claude Code (Opus / Sonnet / Haiku), Gemini CLI, ChatGPT (Codex CLI) with model choice, plus a custom command (e.g. Ollama). Falls back to Lingva/Google if it fails
- Main: the service dropdown only lists services that are set up (key entered / program installed); model dropdown right next to it
- Models: Gemini `flash` / `pro` / `flash-lite` (CLI aliases, always the current model), ChatGPT `gpt-5.6-luna` (fast, default) / `terra` / `sol` / `gpt-5.5`; Codex gets the prompt via stdin and low reasoning effort, Gemini answers as JSON (no status lines in the translation)
- Model dropdown is a normal dropdown again (click opens the list); new model names via *✏ Other model …*
- AI tools get a **Sign in** button (opens a terminal with `claude` / `gemini` / `codex login`) and show whether you are signed in; not signed in → skipped right away, Lingva takes over
- Claude Code is installed with the official installer (`curl -fsSL https://claude.ai/install.sh | bash`) instead of npm – the npm version could end up without its program ("claude native binary not installed"); a broken install is detected and offered as **Reinstall**. npm installs for Gemini/Codex now force optional deps + install scripts
- AI tools get an **Install** button (`npm install -g --prefix ~/.local …`, installs npm via pkexec if missing)
- Options → Translation: *Test* checks ONLY the chosen service (no Lingva/Google stand-in), and the service is never switched automatically while Options is open
- If the chosen service fails, Main switches the service to the one that actually translated (e.g. Claude Code → Lingva) and says why
- **Fix – copy in WayVR didn't reach the desktop:** copied text/images are also handed to the desktop clipboard via `wl-copy` (Options → General → Clipboard) – with a button that installs `wl-clipboard` (pacman / dnf / apt / zypper, password via pkexec)

## [v0.4.3] – 2026-09-27
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
