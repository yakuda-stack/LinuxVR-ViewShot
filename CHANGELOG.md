# Changelog

## [v1.0.4] – 2026-10-09
Update: **AUR** `yay -Syu linuxvr-viewshot` or the **AppImage** – open the app once (or press ⬆ *Update layer*). From a clone: 🔧 *Rebuild & install*. Then restart the VR game. **Needs a layer + service rebuild.**

- **Fix: 🔁 Lens / 📌 Pin showed no translation (only the frame)** – when the runtime rejected one overlay layer once (`ERROR_POSE_INVALID`, e.g. a controller briefly lost tracking), the layer turned the overlay **and** the 🪟 panel off until the game was restarted. Now it only pauses for 3 s and tries again; only after 5 rejections in a row it stays off
- **Broken poses are no longer sent to the runtime** – quads with an invalid rotation (0 / NaN), position or size are left out for that frame, rotations are normalised before every frame. So one bad quad can't make the runtime reject the whole frame anymore
- **Better logs for Lens / Pin** – `layer.log`: “Translation over the original shown” once per Lens/Pin, and a note when a translation belongs to an unknown picture. `daemon.log`: live picture received, translated → overlay written, no text, translation failed (only changes are logged, no spam every 3 s)
- **`daemon.log` from the last start is kept** as `daemon.log.1` – before, a game restart overwrote it

## [v1.0.3] – 2026-10-07
Update: **AUR** `yay -Syu linuxvr-viewshot` or the **AppImage** – open the app once (or press ⬆ *Update layer*). From a clone: 🔧 *Rebuild & install*. Then restart the VR game. **Needs a layer + service rebuild.**

- **🥽 Lens overlay is fixed in the world** – the translation no longer sticks to the blue frame in front of your face. The layer remembers where you looked for every Lens picture (`ViewShot-Seq` in `live.png` → copied into `overlay.png`), and the translation is placed exactly there, over the original text. Turn your head and it stays on the text. Placed 2 m away (real text distance is unknown – further away = less shifting when you move)
- **🔁 Lens only translates** – no 🤖 Auto / explain / answer anymore, also when another task is chosen for photos
- **🥽 No text anymore → overlay disappears** – Lens removes the old translation when the picture has no text, so you have a clear view again
- **Fix: Lens translation jumping into the frame** – the translation was sometimes shown in the frame first and then at the right place. It is now only shown at the right place in the world (the layer keeps the last 16 pictures in order; unknown picture = nothing shown)
- **📌 New type: Pin** – between photo and Lens in the type cycle (🪄 Auto → 📌 Pin → 🔁 Lens · 🖼 → 📝 → 🔳 → 📌 Pin → 🔁 Lens). Mark an area and press the shutter: the blue frame stays **fixed in the world** – you can walk around it. Whenever you look into it, the part of the picture inside the frame is translated and shown right over the original text, like Lens. Translation only. Not looking into it (less than half in view) → nothing is captured. New frame = off
- **🥽 Tilted head: translation stays straight** (Lens + Pin) – the layer writes the head tilt into `live.png` (`ViewShot-Roll`), app / service turn the picture until the text is level (OCR reads it better too) and the layer turns the box back. So the translation lies exactly over the original text instead of tilting with your head (from 2° tilt)
- **🔘 Panel doesn't open for a photo without translation** – with *Open when translating*, the closed panel now opens when a new photo has actually been translated (app / service writes `panel_open_request`), not right at the shutter

## [v1.0.2] – 2026-10-07
Update: **AUR** `yay -Syu linuxvr-viewshot` or the **AppImage** – open the app once (or press ⬆ *Update layer*). From a clone: 🔧 *Rebuild & install*. Then restart the VR game. **Needs a service rebuild.**

- **🥽 Lens overlay: translation sits exactly over the original** – the grey box now has the size and position of the recognised line instead of being up to 25 % wider and growing downwards, so it no longer covers half the view. Text is centred vertically in the box
- **Long translations get a smaller font** instead of a bigger box (German texts are often longer) – the font shrinks until the text fits in width *and* height. Smallest font is now ~1/90 of the image height (was 1/40); only if it still doesn't fit, the box grows downwards
- Same for the photo overlay (desktop app), so both look the same

## [v1.0.1] – 2026-10-05
Update: **AUR** `yay -Syu linuxvr-viewshot` or the **AppImage** – open the app once (or press ⬆ *Update layer*). From a clone: 🔧 *Rebuild & install*. Then restart the VR game. **Needs a layer + service rebuild.**

- **📐 Fixed aspect ratio** (Options → Shot): free / 1:1 / 16:9 – like a real camera, the frame always keeps the format so shared photos look cleaner. It uses as much of the space between your hands as it can and stays centred. Works for photos, 🔁 Lens and GIFs, changes live in VR (`aspect` in layer.json)
- **🎞 GIF recording:** hold the shutter in the frame (~0.45 s) → GIF. The frame blinks red/white while recording; let go, release the grips or reach the limit to stop. Max. length 1–15 s (Options → Shot, default 15 s), 10 frames/s, longest side 512 px. A short press is still a normal photo – **with GIF on, the photo is taken when you let go** (turn *Hold shutter = record GIF* off for the old instant shutter). With 🔁 Lens selected, holding starts Lens as before. GIFs go to the gallery (animated in the desktop viewer, first frame in the VR gallery) but aren't translated. Encoding runs in its own thread; the file appears only when it's finished (`gif_hold`, `gif_max_s`, `gif_fps` in layer.json)
- **📤 Output: OSC / file** (Options → General, each on/off): every new translation is passed on – also by the background service when the app is closed
  - 📡 **OSC** to `127.0.0.1:9025` (host + port adjustable): message `/viewshot/translation` with 3 strings – translation, original text, source (`photo` / `lens`). Meant for an OSC-DreamChatbox plugin that puts the translation into the chatbox. Don't use port 9000 (VRChat)
  - 📄 **File** `translation.json` with the same info as OSC, latest translation only: `{"id", "time", "translation", "original", "source"}` – `id` (ms since 1970) changes with every new translation, even with the same text, so a plugin only has to watch the id. Replaced in one step (never half written). Default `~/.local/state/linuxvr-viewshot/translation.json`, path adjustable, 📂 opens the folder
  - 🧪 *Send test* button; 🔁 Lens only sends when the text changed
- **Options sorted into 4 tabs:**
  - ⚙ **General:** community, language, main page, folders, clean up, 📤 output (OSC / file), ⚙ without the app (background service), about
  - 📸 **Shot:** frame size, eye, 📐 aspect ratio, 🎞 GIF, detection & buttons, icon corner, exceptions
  - 🥽 **VR (new):** 🪟 panel + 🔘 button, 🔁 Lens, 🥽 overlay – moved out of Shot
  - 🌐 **Translation:** unchanged
- **Removed: WayVR theme** – the *Install Cubee's WayVR theme + ViewShot watch button* card (Options → General) is gone. An already installed theme in `~/.config/wayvr` stays untouched
- **Removed: clipboard mirror** – the *Clipboard* card (copy to the desktop via `wl-copy` when the app runs inside WayVR, incl. the wl-clipboard install button). Copying in the app now only uses the normal Qt clipboard; the background service still uses `wl-copy` / `xclip` for the VR panel (`wl-clipboard` stays an optional dependency for that)
- Texts for all new options in DE / EN / FR

## [v1.0.0] – 2026-10-02
**First stable release.** Update: **AUR** `yay -Syu linuxvr-viewshot` or the new **AppImage** – open the app once, it copies the new layer + background service to `~/.local` by itself (or press ⬆ *Update layer*). From a clone: 🔧 *Rebuild & install*. Then restart the VR game.

- **👋 Welcome on first start:** three short windows – the app is only for setup/installing, afterwards everything happens in VR · install now (🔧 Install now / Later, skipped if already installed) · set up your translators → OK opens Options → Translation. Shown once (`welcome_done` in ui.json)
- **🇫🇷 French** as app language (Options → General → Language), all texts in `UI/core/i18n_fr.py`; missing texts fall back to English. The VR panel of the background service speaks French too
- **🔘 Button to open/close the panel** (like WayVR) – drawn by the layer on the same anchor as the panel (default: on top of the anchor hand, 3 cm, right hand mirrored; head: bottom left; world: in front). Laser + trigger toggles the panel (white ring = open), state is kept in `panel_state.json`. **Edit mode:** button and panel move/rotate (grip) and resize (bottom right corner + trigger) separately – own `button_pose.json`; a new panel appears above the button. ⟲ resets both. Options → Shot and ⚙ in VR: button on/off, **Open when translating** (closed panel opens after a photo, on by default), button size (2–20 cm), button colour (7 colours in VR, colour picker in the app).
- **Faster size switch** between translation and gallery: the layer checks `panel_pose.json` every 80 ms instead of 500 ms
- **🖼 VR panel: pages + gallery** – at the bottom **◀** left / **▶** right switch between 🌐 translation and 🖼 gallery (● ○ shows where you are), ⚙ stays at the top. **Size per page:** translation and gallery each keep their own width/height in VR (`panel_sizes.json`), the gallery is bigger by default (48 cm) and opens big right away. The gallery fills the whole panel: 4 thumbnails per row with **month dividers**, ▲ / ▼ pages next to ⚙. Tap = photo large with **📋 Copy · ☁ Upload + link · ↗ Share · 🌐 Translate · ⓘ Info · 🗑 Delete** (tap twice → trash) and ‹ ›. Same in the app and in the background service (it copies via wl-copy/xclip, uploads to directupload.eu, shares, moves files to the trash itself). The app's panel works right away
- **📁 Gallery folders** – ⚙ in the desktop gallery: photo folder (fixed) + more folders (e.g. `~/Pictures/VRChat`), change / remove, *include subfolders* for each. Desktop + VR gallery show all of them, newest first; only ViewShot photos are translated. Thumbnails load in the background (no freeze with thousands of screenshots)
- **📅 Month dividers** in the desktop and VR gallery (“──── 2026 October ────”)
- **Options → Translation:** *Settings for* dropdown – set up any service without switching Main; 🧪 Test checks the service shown
- **Service dropdowns grouped:** “── Translation ──” (Lingva, Google, LibreTranslate, DeepL, own API) and “── AI translation ──” (Claude, Gemini, ChatGPT, own command, image LLM) – main page, options and VR panel
- **🕘 History on the main page** moved to Options → General (card *Main page*)
- **Fix – share to Discord:** Vesktop / Discord / WebCord are also found as Flatpak (e.g. `dev.vencord.Vesktop`)
- **🪟 Panel: ⚙ settings** instead of the edit/reset buttons – they slide down from the top like on a phone (a few frames; the layer now checks the panel image every 80 ms): **size** slider (panel width 15–80 cm, also in Options → Shot), opacity slider (click anywhere on the bar with the laser), attach to 🤚 left / ✋ right hand, 👤 head, 🌍 world, ✥ move (grip), ⟲ reset position, detection & buttons (auto/manual, shutter, type button). Same in the app's panel and in the background service
- **🪟 Panel: long translations** are split into pages that fit – ▼ below the text shows the next page, ▲ goes back (1 / 3)
- **🪟 Panel: mode 🤖 automatic / ✋ manual** right in the service list
- **Round laser dot** instead of the small square
- **🔧 Rebuild shows %** – cargo's progress (`Building … 120/231`) becomes the percentage on the button; the progress lines stay out of the log
- **⚙ Works without the desktop app:** new background service `viewshot-daemon` (Rust, `daemon/`). It does what the app did in the background – new photo → text recognition → translation → 🪟 VR panel, and 🔁 Lens with the overlay – so the app is mainly for settings and for looking at what you did (gallery, history). Same PaddleOCR models as RapidOCR via onnxruntime (identical text, boxes ±1 px), same services, same auto/manual routing, same `translations.json` cache and history – the app shows the service's results without asking again. Start: the layer sends `hello` to 127.0.0.1:47932 during a VR game and systemd (socket activation) starts the service; it quits ~2 min after the game (the OCR model leaves memory after 1 min idle). Options → Shot → *Without the app*: off / every VR game / only selected games (recently played games to tick + own names). While the app is open it holds `~/.local/state/linuxvr-viewshot/app.lock` and the service steps aside. The app copies the service, onnxruntime and the OCR models to `~/.local/lib/linuxvr-viewshot/` and sets up the systemd user units (also AppImage / AUR). Custom snippet translator ("Eigene API") only with the app. Log: `~/.local/state/linuxvr-viewshot/daemon.log`. `daemon/contract.json` (texts, defaults, cache keys, prompts) is generated from the app and checked by tests on both sides.
- **↻ Send again** really asks again (the saved answer used to come back)
- **🪟 Translation panel in VR** (Options → Shot, on by default): a window with the photo and numbers ①②③ on the recognised lines and the translations 1, 2, 3 below (AI answers as text). Service, task, from → to and ↻ right in VR: point with the controller (laser) and press the trigger – lists instead of dropdowns. Attached to the left/right hand, head or world. ✥ Edit mode (yellow border): grip = move, corner lights up + hold trigger: bottom right = width, top left = height; opacity − / + (30–100 %, also in Options); ⟲ reset position in the panel or in Options. The app draws the panel (invisible Qt window → `panel/panel.png`), clicks come back via UDP (port 47931). Grip/trigger still reach the game.
- **🥽 🔁 Lens: translation over the original** (Options → Shot, off by default): a grey box with the translation over every recognised line inside the blue frame, updated with every new picture. Photos are shown in the 🪟 panel instead (photo overlay removed from the layer too, `overlay_seconds` is gone). The app draws the image (`overlay/overlay.png`), the layer shows it. If the number of lines doesn't match (e.g. AI answers) there is one big box over the text.
- **🖼 Local image LLM (Ollama)** – new AI service: gets the photo plus the OCR lines, answers line by line (fits the VR overlay), fixes OCR mistakes and reads text OCR missed. Streaming, all AI tasks, model dropdown with the installed image models, 📥 *Download model*, and *Keep in graphics memory* (30 s … always) so VR gets the memory back. **📦 Install Ollama** button: on Arch/CachyOS the pacman package that fits the graphics card (NVIDIA → `ollama-cuda`, AMD → `ollama-rocm`, else `ollama`) + `systemctl enable --now ollama`, on other distros the official script from ollama.com – runs in a terminal, hidden once Ollama is installed.
- Text recognition now also keeps the position of every line (cached)
- **Answer question:** the lines go to the AI numbered (1), 2), …) – the answer names the number (➜ ③ …), the same number as on the photo in the panel. Image LLM: first a short *quiz? yes/no*, then either a quiz prompt or a line-by-line translation (small models do two small steps much better than one big one)
- **🧭 Service per task** (Options → Translation, one card): **Mode** 🤖 automatic / ✋ manual, **Main**, *Explain context* AI, *Answer question* AI (model = the one set for that AI, also changeable there). 🤖 Automatic (only with an AI as main – LibreTranslate & Co. switch the mode to manual): for every photo the main AI decides with a one-word question (QUIZ / EXPLAIN / TEXT), translates normal text itself and hands the rest to the task's AI. Picking a task on the main page / in the VR panel overrides it for the current + next photo, then it's automatic again. ✋ Manual: the task you pick stays, with its fixed AI
- **🏷 Last AI** under *Task* (main page + VR panel): which AI, model and task wrote the answer shown; remembered per photo in the cache, stays until the next answer
- **The service no longer switches automatically:** if a service fails, Lingva/Google step in once and your setting stays
- **Image LLM thinks first:** for quizzes it first writes the full proverb/idiom/fact (💡 line), then picks the number – small models no longer just pick the first option as often

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
