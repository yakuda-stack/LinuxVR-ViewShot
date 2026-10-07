"""
core/i18n.py – Übersetzungen DE/EN/FR.

Benutzung:   tr("nav_main")   → "Main"
Neuer Text?  Unten in TEXTS eine Zeile mit "de" und "en" eintragen,
             Französisch in core/i18n_fr.py (fehlt es dort, kommt Englisch).
"""

TEXTS = {
    # Seitenleiste
    "nav_main":        {"de": "Main",            "en": "Main"},
    "nav_gallery":     {"de": "Galerie",         "en": "Gallery"},
    "nav_options":     {"de": "Optionen",        "en": "Options"},

    # Main
    "status":          {"de": "Status",          "en": "Status"},
    "layer_ok":        {"de": "✔  Layer ist installiert",
                        "en": "✔  Layer is installed"},
    "layer_missing":   {"de": "✘  Layer ist nicht installiert",
                        "en": "✘  Layer is not installed"},
    "install":         {"de": "Installieren",    "en": "Install"},
    "reinstall":       {"de": "Neu bauen & installieren", "en": "Rebuild & install"},
    "installing":      {"de": "Baut … (kann 1–2 Minuten dauern)",
                        "en": "Building … (may take 1–2 minutes)"},
    "install_ok":      {"de": "✔ Fertig – Spiel neu starten, damit der neue Layer geladen wird",
                        "en": "✔ Done – restart the game to load the new layer"},
    "install_failed":  {"de": "✘ Fehlgeschlagen – siehe Ausgabe oben",
                        "en": "✘ Failed – see output above"},
    "layer_legacy":    {"de": "⚠ alte systemweite Kopie – Paket aktualisieren",
                        "en": "⚠ old system-wide copy – update the package"},
    "layer_legacy_tip": {"de": "Eine alte Version des AUR-Pakets hat den Layer in /usr/share/openxr "
                               "registriert. Steam-/Proton-Spiele wie VRChat sehen das nicht, andere "
                               "Programme laden ihn dann doppelt.\nAbhilfe: Paket aktualisieren "
                               "(yay -Syu) oder entfernen (sudo pacman -R linuxvr-viewshot) und hier "
                               "„Installieren“ drücken.",
                         "en": "An old version of the AUR package registered the layer in "
                               "/usr/share/openxr. Steam/Proton games like VRChat can't see it, other "
                               "programs then load it twice.\nFix: update the package (yay -Syu) or "
                               "remove it (sudo pacman -R linuxvr-viewshot) and press “Install” here."},
    "layer_packaged":  {"de": "Installiert über ein Paket (AUR) – „Installieren“ kopiert den Layer "
                              "nach ~/.local, nach Paket-Updates passiert das automatisch.",
                        "en": "Installed from a package (AUR) – “Install” copies the layer to "
                              "~/.local; after package updates this happens automatically."},
    "uninstall":       {"de": "Entfernen",       "en": "Remove"},
    "uninstall_question": {"de": "Den VR-Layer entfernen?\n\nViewShot ist danach in VR aus. Diese App, "
                                 "deine Fotos und Einstellungen bleiben – mit „Installieren“ ist er wieder da.",
                           "en": "Remove the VR layer?\n\nViewShot is then off in VR. This app, your "
                                 "photos and settings stay – “Install” brings it back."},
    "uninstall_ok":    {"de": "✔ Layer entfernt – Spiel neu starten, dann ist ViewShot in VR aus",
                        "en": "✔ Layer removed – restart the game and ViewShot is off in VR"},
    "uninstall_failed": {"de": "✘ Entfernen fehlgeschlagen", "en": "✘ Removing failed"},
    # AppImage: Layer liegt fertig bei und wird nur kopiert
    "layer_update":    {"de": "Layer aktualisieren", "en": "Update layer"},
    "layer_reinstall": {"de": "Layer neu installieren", "en": "Reinstall layer"},
    "layer_updated":   {"de": "✔ Layer auf v{v} aktualisiert – Spiel neu starten",
                        "en": "✔ Layer updated to v{v} – restart the game"},
    "install_failed_copy": {"de": "✘ Layer konnte nicht nach ~/.local kopiert werden",
                            "en": "✘ Could not copy the layer to ~/.local"},
    "no_script":       {"de": "Install-Skript nicht gefunden", "en": "Install script not found"},
    "photo_count":     {"de": "Fotos: {n}",      "en": "Photos: {n}"},
    "last_photo":      {"de": "Letztes Foto",    "en": "Last photo"},
    "no_photo":        {"de": "Noch kein Foto – mach eins in VR!",
                        "en": "No photo yet – take one in VR!"},
    "chosen_photo":    {"de": "Ausgewähltes Foto", "en": "Selected photo"},
    "pick_file":       {"de": "Bild aus Datei wählen …", "en": "Choose image file …"},
    "pick_gallery":    {"de": "Foto aus der Galerie wählen …", "en": "Choose photo from gallery …"},
    "use_last_photo":  {"de": "Letztes Foto", "en": "Last photo"},
    "image_files":     {"de": "Bilder",          "en": "Images"},
    "pick_photo_title": {"de": "Foto wählen",    "en": "Choose photo"},
    "pick_photo_hint": {"de": "Klick auf ein Foto wählt es aus.",
                        "en": "Click a photo to select it."},
    "cancel":          {"de": "Abbrechen",       "en": "Cancel"},
    "qr_title":        {"de": "QR-Code im Foto", "en": "QR code in photo"},
    "qr_open":         {"de": "Öffnen",          "en": "Open"},
    "howto":           {"de": "So geht's",       "en": "How it works"},
    "howto_1":         {"de": "1.  Grip an beiden Controllern halten (sonst nichts drücken)",
                        "en": "1.  Hold grip on both controllers (don't press anything else)"},
    "howto_2":         {"de": "2.  Hände auseinander → kurzes Vibrieren, roter Rahmen erscheint",
                        "en": "2.  Hands apart → short vibration, red frame appears"},
    "howto_3":         {"de": "3.  Auslöser-Trigger drücken (Standard: rechts) → Foto! Der Rahmen blitzt weiß",
                        "en": "3.  Press the shutter trigger (default: right) → photo! The frame flashes white"},
    "howto_4":         {"de": "4.  Manuell: Typ-Trigger (Standard: links) schaltet das Symbol im Rahmen um – "
                              "🖼 Bild → 📝 Text → 🔳 QR → 📌 Pin → 🔁 Lens. Das Foto bekommt diesen Typ.",
                        "en": "4.  Manual: the type trigger (default: left) switches the icon in the frame – "
                              "🖼 Image → 📝 Text → 🔳 QR → 📌 Pin → 🔁 Lens. The photo gets that type."},
    "howto_4_auto":    {"de": "4.  Typ-Trigger (Standard: links) schaltet das Symbol im Rahmen um: "
                              "🪄 Auto (Foto) → 📌 Pin → 🔁 Lens (Live-Übersetzung).",
                        "en": "4.  The type trigger (default: left) switches the icon in the frame: "
                              "🪄 Auto (photo) → 📌 Pin → 🔁 Lens (live translation)."},
    "howto_5":         {"de": "5.  🔁 Lens + Auslöser → kein Foto, sondern ein blauer Rahmen: der Bereich wird "
                              "alle paar Sekunden neu übersetzt. 📌 Pin: der Rahmen bleibt fest in der Welt stehen – "
                              "schau hinein und der Text darin wird übersetzt. Neuer Rahmen = aus.",
                        "en": "5.  🔁 Lens + shutter → no photo but a blue frame: the area is translated again "
                              "every few seconds. 📌 Pin: the frame stays fixed in the world – look into it and "
                              "the text inside is translated. New frame = off."},
    "open_folder":     {"de": "Foto-Ordner",     "en": "Photo folder"},

    # Galerie
    "refresh":         {"de": "Aktualisieren",   "en": "Refresh"},
    "tile_size":       {"de": "Größe",           "en": "Size"},
    "gallery_hint":    {"de": "Klick zeigt das Foto groß  ·  ← → blättern  ·  Esc zurück",
                        "en": "Click shows the photo large  ·  ← → browse  ·  Esc back"},
    "back":            {"de": "Zurück",          "en": "Back"},
    "open_external":   {"de": "Im Bildbetrachter öffnen", "en": "Open in image viewer"},
    "copy":            {"de": "Kopieren",        "en": "Copy"},
    "share":           {"de": "Teilen",          "en": "Share"},
    "upload":          {"de": "Hochladen & Link kopieren", "en": "Upload & copy link"},
    "uploading":       {"de": "Lädt hoch …",     "en": "Uploading …"},
    "copy_link":       {"de": "Link kopieren",   "en": "Copy link"},
    "info":            {"de": "Info",            "en": "Info"},
    "copied_image":    {"de": "✔ Bild in die Zwischenablage kopiert",
                        "en": "✔ Image copied to clipboard"},
    "copied_link":     {"de": "✔ Link kopiert",  "en": "✔ Link copied"},
    "share_none":      {"de": "Kein Programm gefunden (Discord, Telegram …)",
                        "en": "No app found (Discord, Telegram …)"},
    "share_paste":     {"de": "✔ Bild kopiert – in Discord mit Strg+V einfügen",
                        "en": "✔ Image copied – paste in Discord with Ctrl+V"},
    "share_opened":    {"de": "✔ Geöffnet",      "en": "✔ Opened"},
    "share_failed":    {"de": "✘ Teilen fehlgeschlagen", "en": "✘ Sharing failed"},
    "upload_done":     {"de": "✔ Hochgeladen – Link ist in der Zwischenablage",
                        "en": "✔ Uploaded – link is in the clipboard"},
    "upload_failed":   {"de": "✘ Upload fehlgeschlagen", "en": "✘ Upload failed"},
    "link_view":       {"de": "Link zum Bild",   "en": "Image link"},
    "link_delete":     {"de": "Link zum Löschen", "en": "Delete link"},
    "info_taken":      {"de": "Aufgenommen",     "en": "Taken"},
    "info_resolution": {"de": "Auflösung",       "en": "Resolution"},
    "info_size":       {"de": "Dateigröße",      "en": "File size"},
    "tags_title":      {"de": "Bild-Erkennung",  "en": "Image detection"},
    "tags_hint":       {"de": "Automatisch erkannt – anklicken zum Ändern. "
                              "VRChat-Namensschilder zählen nicht als Text.",
                        "en": "Detected automatically – click to change. "
                              "VRChat nameplates don't count as text."},
    "tag_text":        {"de": "Text",            "en": "Text"},
    "tag_qr":          {"de": "QR-Code",         "en": "QR code"},
    "tag_image":       {"de": "Bild",            "en": "Image"},
    "tags_pending":    {"de": "Wird noch erkannt …", "en": "Still detecting …"},
    "tags_auto":       {"de": "Automatisch erkannt", "en": "Detected automatically"},
    "tags_manual":     {"de": "Von Hand geändert", "en": "Changed by hand"},
    "tags_redo":       {"de": "Neu erkennen",    "en": "Detect again"},
    "close":           {"de": "Schließen",       "en": "Close"},
    "detect_auto":     {"de": "🤖  Automatisch erkennen", "en": "🤖  Detect automatically"},
    "detect_manual":   {"de": "✋  Manuell in VR wählen", "en": "✋  Choose manually in VR"},
    "detect_tip":      {"de": "Automatisch: die App erkennt Text / QR / Bild.\n"
                              "Manuell: du wählst den Typ in VR mit dem Typ-Trigger.",
                        "en": "Automatic: the app detects text / QR / image.\n"
                              "Manual: you choose the type in VR with the type trigger."},
    "buttons_title":   {"de": "Erkennung & Tasten", "en": "Detection & buttons"},
    "buttons_hint":    {"de": "Welche Trigger bei offenem Rahmen was tun. Wirkt sofort – "
                              "nur beim ersten Mal Layer neu bauen (Main → Neu bauen).",
                        "en": "What the triggers do while the frame is open. Applies instantly – "
                              "rebuild the layer once (Main → Rebuild)."},
    "detect_mode":     {"de": "Erkennung",       "en": "Detection"},
    "shutter":         {"de": "Foto auslösen",   "en": "Take photo"},
    "mode_button":     {"de": "Typ wechseln",    "en": "Switch type"},
    "combo_left":      {"de": "Linker Trigger",  "en": "Left trigger"},
    "combo_right":     {"de": "Rechter Trigger", "en": "Right trigger"},
    "combo_both":      {"de": "Beide Trigger gleichzeitig", "en": "Both triggers together"},
    "buttons_auto_note": {"de": "Im Rahmen erscheint ein Symbol: 🪄 Auto (Foto, die App erkennt den Typ) ↔ "
                                "📌 Pin ↔ 🔁 Lens. Auslöser und Typ-Taste können nicht gleich sein.",
                          "en": "An icon appears in the frame: 🪄 Auto (photo, the app detects the type) ↔ "
                                "📌 Pin ↔ 🔁 Lens. Shutter and type button can't be the same."},
    "buttons_manual_note": {"de": "Im Rahmen erscheint ein Symbol: 🖼 / 📝 / 🔳 / 📌 Pin / 🔁 Lens. "
                                  "Auslöser und Typ-Taste können nicht gleich sein.",
                            "en": "An icon appears in the frame: 🖼 / 📝 / 🔳 / 📌 Pin / 🔁 Lens. "
                                  "Shutter and type button can't be the same."},
    "icon_position":   {"de": "Symbol-Position",   "en": "Icon position"},
    "icon_position_hint": {"de": "In welcher Ecke des Rahmens das Typ-Symbol sitzt. Wirkt sofort.",
                           "en": "Which corner of the frame shows the type icon. Applies instantly."},
    "bottom_left":     {"de": "↙ Unten links",     "en": "↙ Bottom left"},
    "bottom_right":    {"de": "↘ Unten rechts",    "en": "↘ Bottom right"},
    "top_left":        {"de": "↖ Oben links",      "en": "↖ Top left"},
    "top_right":       {"de": "↗ Oben rechts",     "en": "↗ Top right"},
    "filter_all":      {"de": "Alle",            "en": "All"},
    "select":          {"de": "Auswählen",       "en": "Select"},
    "select_all":      {"de": "Alle",            "en": "All"},
    "set_type":        {"de": "Typ",             "en": "Type"},
    "type_set":        {"de": "✔ {n} Fotos sind jetzt {tag}", "en": "✔ {n} photos are now {tag}"},
    "selected_count":  {"de": "{n} ausgewählt",  "en": "{n} selected"},
    "delete_many_question": {"de": "{n} Fotos in den Papierkorb verschieben?",
                        "en": "Move {n} photos to the trash?"},
    "deleted_many":    {"de": "✔ {n} Fotos wurden gelöscht (Papierkorb)",
                        "en": "✔ {n} photos were deleted (trash)"},
    "cleanup_title":   {"de": "Beim Beenden aufräumen", "en": "Clean up on exit"},
    "cleanup_hint":    {"de": "Wenn du die App schließt, kommen diese Fotos in den Papierkorb. "
                              "Fotos, die zusätzlich 🖼 Bild getaggt sind, bleiben.",
                        "en": "When you close the app, these photos go to the trash. "
                              "Photos also tagged 🖼 Image are kept."},
    "cleanup_qr":      {"de": "🔳  QR-Code-Fotos löschen", "en": "🔳  Delete QR code photos"},
    "cleanup_text":    {"de": "📝  Text-Fotos löschen", "en": "📝  Delete text photos"},

    # Upload prüfen
    "check_upload":    {"de": "Upload prüfen",   "en": "Check upload"},
    "checking":        {"de": "Prüfe …",         "en": "Checking …"},
    "still_online":    {"de": "✔ Bild ist noch online", "en": "✔ Image is still online"},
    "was_deleted":     {"de": "✔ Bild wurde online gelöscht – Links entfernt",
                        "en": "✔ Image was deleted online – links removed"},
    "check_failed":    {"de": "✘ Prüfen fehlgeschlagen", "en": "✘ Check failed"},

    # Löschen
    "delete":          {"de": "Löschen",         "en": "Delete"},
    "delete_title":    {"de": "Foto löschen?",   "en": "Delete photo?"},
    "delete_question": {"de": "„{name}“ in den Papierkorb verschieben?",
                        "en": "Move “{name}” to the trash?"},
    "deleted":         {"de": "✔ Foto {name} wurde gelöscht (Papierkorb)",
                        "en": "✔ Photo {name} was deleted (trash)"},
    "delete_failed":   {"de": "✘ Löschen fehlgeschlagen", "en": "✘ Delete failed"},
    "yes":             {"de": "Ja",              "en": "Yes"},
    "no":              {"de": "Nein",            "en": "No"},

    # Optionen – Tabs
    "tab_general":     {"de": "General",         "en": "General"},
    "tab_shot":        {"de": "Shot",            "en": "Shot"},
    "tab_vr":          {"de": "VR",              "en": "VR"},
    "community":       {"de": "Community",       "en": "Community"},
    "community_hint":  {"de": "Fragen, Ideen und Fehlermeldungen gerne auf Discord.",
                        "en": "Questions, ideas and bug reports are welcome on Discord."},
    "kofi":            {"de": "Unterstützen auf Ko-fi", "en": "Support on Ko-fi"},
    "about_text":      {"de": "VR-Fotos per Hand-Rahmen-Geste unter Linux (WiVRn / Monado). "
                              "Entwickelt mit Unterstützung von Claude (Anthropic).",
                        "en": "VR photos with a hand-frame gesture on Linux (WiVRn / Monado). "
                              "Developed with the support of Claude (Anthropic)."},
    "reset":           {"de": "Standard",        "en": "Default"},
    "frame_size":      {"de": "Rahmengröße",     "en": "Frame size"},
    "frame_size_hint": {"de": "Wie weit der rote Rahmen von deinen Händen nach innen rückt. "
                              "Wirkt sofort – auch während das Spiel läuft.",
                        "en": "How far the red frame sits inside your hands. "
                              "Applies instantly – even while the game is running."},
    "frame_bigger":    {"de": "größer",          "en": "bigger"},
    "frame_smaller":   {"de": "kleiner",         "en": "smaller"},
    "frame_value":     {"de": "{cm} cm Abstand zu den Händen", "en": "{cm} cm away from your hands"},
    "eye":             {"de": "Auge",            "en": "Eye"},
    "eye_hint":        {"de": "Von welchem Auge aus fotografiert wird. Stell es auf dein "
                              "Führungsauge, wenn der Ausschnitt verschoben wirkt. Das Bild "
                              "selbst kommt immer aus einem Auge (bis 50 % links, darüber "
                              "rechts) – beide mischen gäbe Doppelbilder.",
                        "en": "Which eye the photo is taken from. Set it to your dominant "
                              "eye if the crop looks shifted. The picture itself always comes "
                              "from one eye (up to 50 % left, above that right) – mixing both "
                              "would give double images."},
    "left":            {"de": "Links",           "en": "Left"},
    "right":           {"de": "Rechts",          "en": "Right"},
    "eye_value":       {"de": "Links {left} %  ·  Rechts {right} %   (Bild: {source})",
                        "en": "Left {left} %  ·  Right {right} %   (image: {source})"},
    "excluded":        {"de": "Ausnahmen",       "en": "Exceptions"},
    "excluded_hint":   {"de": "In diesen Programmen ist ViewShot aus (z. B. Overlays). "
                              "Ein Teil des Namens reicht, Groß-/Kleinschreibung egal.",
                        "en": "ViewShot is off in these programs (e.g. overlays). "
                              "Part of the name is enough, case doesn't matter."},
    "excluded_placeholder": {"de": "Programmname, z. B. wlx-overlay-s",
                             "en": "Program name, e.g. wlx-overlay-s"},
    "excluded_restart": {"de": "Gilt ab dem nächsten Start des Programms.",
                         "en": "Applies the next time the program starts."},
    "add":             {"de": "Hinzufügen",      "en": "Add"},
    "remove":          {"de": "Entfernen",       "en": "Remove"},
    "settings_folder": {"de": "Einstellungen",   "en": "Settings"},

    # Übersetzung
    "tab_translation": {"de": "Übersetzung",     "en": "Translation"},
    "tr_service":      {"de": "Übersetzungsdienst", "en": "Translation service"},
    "tr_service_hint": {"de": "Der Text im Foto wird erkannt (OCR) und übersetzt. Fällt der "
                              "gewählte Dienst aus, wird automatisch Lingva bzw. Google benutzt.",
                        "en": "The text in the photo is recognised (OCR) and translated. If the "
                              "chosen service fails, Lingva or Google is used automatically."},
    "tr_m_lingva":     {"de": "Lingva (anonym, kein Key)", "en": "Lingva (anonymous, no key)"},
    "tr_m_google":     {"de": "Google Translate (API-Key optional)",
                        "en": "Google Translate (API key optional)"},
    "tr_m_libre":      {"de": "LibreTranslate lokal (selbst installieren)",
                        "en": "LibreTranslate local (install yourself)"},
    "tr_m_libre_online": {"de": "LibreTranslate online (Key optional)",
                          "en": "LibreTranslate online (key optional)"},
    "tr_m_deepl":      {"de": "DeepL (API-Key nötig)", "en": "DeepL (API key required)"},
    "tr_m_custom":     {"de": "Eigene API (LibreTranslate als Vorlage)",
                        "en": "Custom API (LibreTranslate as template)"},
    "tr_m_llm_claude": {"de": "KI: Claude Code (Opus / Sonnet / Haiku)",
                        "en": "AI: Claude Code (Opus / Sonnet / Haiku)"},
    "tr_m_llm_gemini": {"de": "KI: Gemini CLI", "en": "AI: Gemini CLI"},
    "tr_m_llm_chatgpt": {"de": "KI: ChatGPT (Codex CLI)", "en": "AI: ChatGPT (Codex CLI)"},
    "tr_m_llm_custom": {"de": "KI: eigener Befehl (z. B. Ollama)",
                        "en": "AI: custom command (e.g. Ollama)"},
    "tr_task":         {"de": "Aufgabe",         "en": "Task"},
    "tr_last_ai":      {"de": "Letzte KI", "en": "Last AI"},
    "tr_mode_auto":    {"de": "🤖 Auto (Main-KI entscheidet)", "en": "🤖 Auto (main AI decides)"},
    "tr_step_classify": {"de": "{name} schaut, was es ist …", "en": "{name} checks what it is …"},
    "tr_mode_translate": {"de": "🌐 Übersetzen", "en": "🌐 Translate"},
    "tr_mode_explain": {"de": "💡 Kontext erklären", "en": "💡 Explain context"},
    "tr_mode_answer":  {"de": "❓ Frage beantworten (sonst übersetzen)",
                        "en": "❓ Answer question (else translate)"},
    "tr_model":        {"de": "Modell",          "en": "Model"},
    "tr_model_other":  {"de": "Anderes Modell …", "en": "Other model …"},
    "tr_llm_info":     {"de": "Nutzt das installierte Programm mit deinem Login – kein API-Key in "
                              "dieser App. Einmal auf „Anmelden“ klicken. Dauert ein paar "
                              "Sekunden. Klappt es nicht, übernimmt automatisch Lingva.",
                        "en": "Uses the installed program with your login – no API key in this app. "
                              "Click “Sign in” once. Takes a few seconds. "
                              "If it fails, Lingva takes over automatically."},
    "tr_llm_found":    {"de": "✔ {cmd} ist installiert", "en": "✔ {cmd} is installed"},
    "tr_llm_missing":  {"de": "✘ {cmd} nicht gefunden – installieren:  {hint}",
                        "en": "✘ {cmd} not found – install:  {hint}"},
    "tr_llm_install":  {"de": "Installieren",    "en": "Install"},
    "tr_llm_installing": {"de": "Installiere:  {cmd}  (kann 1–2 Minuten dauern) …",
                          "en": "Installing:  {cmd}  (may take 1–2 minutes) …"},
    "tr_llm_reinstall": {"de": "Neu installieren", "en": "Reinstall"},
    "tr_llm_broken":   {"de": "✘ {cmd} ist installiert, startet aber nicht (npm-Version unvollständig) "
                              "– auf „Neu installieren“ klicken",
                        "en": "✘ {cmd} is installed but doesn't start (incomplete npm version) "
                              "– click “Reinstall”"},
    "tr_llm_install_failed": {"de": "✘ Installieren fehlgeschlagen", "en": "✘ Install failed"},
    "tr_llm_login_btn": {"de": "Anmelden",       "en": "Sign in"},
    "tr_llm_logged_in": {"de": "✔ angemeldet – fertig eingerichtet", "en": "✔ signed in – ready"},
    "tr_llm_not_logged_in": {"de": "✘ noch nicht angemeldet – auf „Anmelden“ klicken",
                             "en": "✘ not signed in yet – click “Sign in”"},
    "tr_llm_login_unknown": {"de": "Anmeldung nicht erkennbar – falls es nicht geht: „Anmelden“ ({cmd})",
                             "en": "Can't tell if signed in – if it fails: “Sign in” ({cmd})"},
    "tr_llm_login_running": {"de": "Terminal ist offen: dort anmelden (öffnet den Browser). "
                                    "Danach das Terminal schließen – hier wird es automatisch erkannt.",
                             "en": "Terminal is open: sign in there (opens the browser). "
                                   "Then close the terminal – it is detected here automatically."},
    "tr_no_terminal":  {"de": "✘ Kein Terminal gefunden – selbst öffnen und  {cmd}  eingeben",
                        "en": "✘ No terminal found – open one and type  {cmd}"},
    "tr_press_enter":  {"de": "Fertig – Enter zum Schließen", "en": "Done – press Enter to close"},
    "tr_npm_missing":  {"de": "npm fehlt – der Knopf installiert es mit ({cmd})",
                        "en": "npm is missing – the button installs it too ({cmd})"},
    "tr_step_ocr":     {"de": "Liest Text im Foto …", "en": "Reading text in the photo …"},
    "tr_step_ocr_wait": {"de": "Liest Text im Foto … (Bild-Erkennung ist gerade noch bei einem "
                               "anderen Foto)",
                         "en": "Reading text in the photo … (image detection is still busy with "
                               "another photo)"},
    "tr_step_retry":   {"de": "{name} hängt – sende neu (Versuch {n}) …",
                        "en": "{name} is stuck – sending again (attempt {n}) …"},
    "tr_retry":        {"de": "Neu senden, wenn länger als", "en": "Send again if it takes longer than"},
    "tr_retry_hint":   {"de": "Hängt die KI, wird bis zu {n}× neu gefragt, danach übernimmt Lingva/Google. "
                              "Aus = warten (max. {max} s).",
                        "en": "If the AI is stuck it is asked again up to {n}×, then Lingva/Google "
                              "takes over. Off = wait (max. {max} s)."},
    "tr_copy_tip":     {"de": "Übersetzung kopieren", "en": "Copy translation"},
    "tr_copied":       {"de": "✔ Übersetzung kopiert", "en": "✔ Translation copied"},
    "history":         {"de": "Verlauf",          "en": "History"},
    "history_hint":    {"de": "Antippen zeigt erkannten Text + Übersetzung (ohne Bild).",
                        "en": "Tap to show recognised text + translation (without image)."},
    "history_clear":   {"de": "Verlauf leeren",   "en": "Clear history"},
    "history_popout":  {"de": "Verlauf in eigenem Fenster öffnen",
                        "en": "Open history in its own window"},
    "history_popped_out": {"de": "Der Verlauf ist in einem eigenen Fenster.",
                           "en": "The history is in its own window."},
    "history_showing": {"de": "🕘 Aus dem Verlauf: {time}  {service}",
                        "en": "🕘 From history: {time}  {service}"},
    "history_option":  {"de": "🕘 Verlauf auf der Main-Seite (Übersetzungen merken)",
                        "en": "🕘 History on the Main page (remember translations)"},
    "ocr_edit_hint":   {"de": "Text hier eintippen oder korrigieren …",
                        "en": "Type or correct the text here …"},
    "ocr_retranslate": {"de": "Korrigierten Text übersetzen", "en": "Translate corrected text"},
    "tr_refresh":      {"de": "Nochmal senden (neue Antwort holen)",
                        "en": "Send again (get a new answer)"},
    "tr_step_service": {"de": "Übersetzt mit {name} …", "en": "Translating with {name} …"},
    "tr_step_partial": {"de": "KI schreibt noch …", "en": "AI is still writing …"},
    "ui_log":          {"de": "App-Log",         "en": "App log"},
    "tr_fallback_once": {"de": "⚠ {failed} ging nicht – diesmal mit {used} übersetzt. {error}",
                         "en": "⚠ {failed} failed – translated with {used} this time. {error}"},
    "tr_no_answer":    {"de": "keine Antwort", "en": "no answer"},
    "tr_llm_custom_info": {"de": "Beliebiges Programm. {prompt} = fertige Übersetzungs-Anweisung "
                                 "mit Text. Außerdem: {text} {source} {target}. Ohne {prompt}/{text} "
                                 "kommt der Prompt über stdin. Die Ausgabe ist die Übersetzung.",
                           "en": "Any program. {prompt} = finished translation instruction incl. "
                                 "text. Also: {text} {source} {target}. Without {prompt}/{text} the "
                                 "prompt goes to stdin. The output is the translation."},
    "privacy_local":   {"de": "🔒 Läuft auf deinem PC – der erkannte Text verlässt ihn nicht.",
                        "en": "🔒 Runs on your PC – the recognised text never leaves it."},
    "privacy_cloud":   {"de": "☁ Der erkannte Text (nicht das Foto) wird zum Übersetzen an {service} "
                              "im Internet geschickt.",
                        "en": "☁ The recognised text (not the photo) is sent to {service} "
                              "on the internet for translation."},
    "privacy_custom":  {"de": "ℹ Hängt von deiner Einrichtung ab: lokal (z. B. Ollama, eigener Server) "
                              "oder im Internet. Verschickt wird nur der erkannte Text, nie das Foto.",
                        "en": "ℹ Depends on your setup: local (e.g. Ollama, your own server) or on the "
                              "internet. Only the recognised text is sent, never the photo."},
    "aspect_card":     {"de": "Seitenverhältnis", "en": "Aspect ratio"},
    "aspect_hint":     {"de": "Wie bei einer echten Kamera: Der Rahmen hält immer dieses Format – so "
                              "sehen geteilte Fotos sauberer aus. Er nutzt den Platz zwischen deinen Händen "
                              "so gut es geht und bleibt mittig.",
                        "en": "Like a real camera: the frame always keeps this format – shared photos look "
                              "cleaner. It uses as much of the space between your hands as it can and stays "
                              "centred."},
    "aspect_free":     {"de": "Frei",             "en": "Free"},
    "gif_card":        {"de": "GIF-Aufnahme",     "en": "GIF recording"},
    "gif_hint":        {"de": "Auslöser im Rahmen gedrückt halten → GIF. Der Rahmen blinkt rot/weiß, "
                              "solange aufgenommen wird; loslassen beendet die Aufnahme. Kurz drücken bleibt "
                              "ein normales Foto.",
                        "en": "Hold the shutter in the frame → GIF. The frame blinks red/white while "
                              "recording; let go to stop. A short press is still a normal photo."},
    "gif_on":          {"de": "Auslöser halten = GIF aufnehmen", "en": "Hold shutter = record GIF"},
    "gif_max":         {"de": "Höchstens",        "en": "At most"},
    "gif_note":        {"de": "Ist das an, wird ein Foto erst beim Loslassen gemacht (sonst sofort beim "
                              "Drücken). GIFs landen in der Galerie, werden aber nicht übersetzt.",
                        "en": "When on, a photo is taken when you let go (otherwise right when you press). "
                              "GIFs go to the gallery but aren't translated."},
    "out_card":        {"de": "Ausgabe (OSC / Datei)", "en": "Output (OSC / file)"},
    "out_hint":        {"de": "Jede neue Übersetzung zusätzlich weitergeben – z. B. an ein Plugin in "
                              "OSC-DreamChatbox, das sie in die Chatbox schreibt. Beides geht einzeln oder "
                              "zusammen. Klappt auch, wenn nur der Hintergrund-Dienst läuft.",
                        "en": "Also pass on every new translation – e.g. to a plugin in OSC-DreamChatbox that "
                              "puts it into the chatbox. Use either one or both. Also works when only the "
                              "background service is running."},
    "out_osc":         {"de": "📡 Per OSC senden", "en": "📡 Send via OSC"},
    "out_osc_host":    {"de": "Adresse",          "en": "Host"},
    "out_osc_port":    {"de": "Port",             "en": "Port"},
    "out_osc_note":    {"de": "Nachricht {address} mit 3 Texten: Übersetzung, Originaltext, Quelle "
                              "(photo / lens). Nicht Port 9000 nehmen – der gehört VRChat.",
                        "en": "Message {address} with 3 strings: translation, original text, source "
                              "(photo / lens). Don't use port 9000 – that's VRChat's."},
    "out_file":        {"de": "📄 In Datei schreiben (JSON, immer nur die letzte Übersetzung)",
                        "en": "📄 Write to a file (JSON, always just the latest translation)"},
    "out_file_note":   {"de": "Gleiche Infos wie bei OSC: translation, original, source – dazu id (neu bei jeder "
                              "Übersetzung, auch bei gleichem Text) und time. Ein Plugin muss nur schauen, ob sich "
                              "die id geändert hat.",
                        "en": "Same info as OSC: translation, original, source – plus id (new for every translation, "
                              "even with the same text) and time. A plugin just checks whether the id changed."},
    "out_test":        {"de": "Test senden",      "en": "Send test"},
    "out_test_text":   {"de": "ViewShot-Test ✔",  "en": "ViewShot test ✔"},
    "out_test_ok":     {"de": "Gesendet",         "en": "Sent"},
    "out_test_off":    {"de": "Erst OSC oder Textdatei einschalten.",
                        "en": "Turn on OSC or the text file first."},
    "live_card":       {"de": "Lens (Live-Übersetzung)", "en": "Lens (live translation)"},
    "live_hint":       {"de": "Im Rahmen mit der Typ-Taste auf 🔁 Lens schalten, dann Auslöser: statt eines "
                              "Fotos wird der Bereich immer wieder fotografiert und übersetzt – z. B. für Welten "
                              "mit viel wechselndem Text. Ein blauer Rahmen zeigt ihn (bleibt vor deinem Kopf).",
                        "en": "In the frame, switch to 🔁 Lens with the type button, then press the shutter: "
                              "instead of a photo the area is photographed and translated again and again – "
                              "e.g. for worlds with lots of changing text. A blue frame shows it "
                              "(stays in front of your head)."},
    "live_every":      {"de": "Alle",             "en": "Every"},
    "live_seconds":    {"de": "{s} s",            "en": "{s} s"},
    "live_note":       {"de": "Beenden: neuen Rahmen aufziehen. Lens-Bilder landen nicht in der Galerie. "
                              "Gleicher Text wird nicht nochmal übersetzt. Am schnellsten mit LibreTranslate – "
                              "kurze Abstände + KI-Dienste = viele Anfragen.",
                        "en": "Stop: open a new frame. Lens pictures don't go to the gallery. Unchanged text "
                              "isn't translated again. Fastest with LibreTranslate – short intervals + AI "
                              "services = many requests."},
    "live_title":      {"de": "Lens",             "en": "Lens"},
    "live_status":     {"de": "Lens",             "en": "Lens"},
    "tr_m_llm_vision": {"de": "🖼 Lokales Bild-LLM (Ollama)", "en": "🖼 Local image LLM (Ollama)"},
    "tr_vision_info":  {"de": "Läuft auf deinem PC und bekommt das FOTO mit: liest schräge oder kleine "
                              "Schrift, bessert Fehler der Texterkennung aus und findet Text, den sie "
                              "übersehen hat. Braucht Ollama – NVIDIA: sudo pacman -S ollama-cuda · "
                              "AMD: ollama-rocm · dann systemctl enable --now ollama. Tipp: das Modell "
                              "teilt sich die Grafikkarte mit VR – kleine Modelle (3–7B) nehmen.",
                        "en": "Runs on your PC and gets the PHOTO too: reads tilted or small text, fixes "
                              "text recognition mistakes and finds text it missed. Needs Ollama – NVIDIA: "
                              "sudo pacman -S ollama-cuda · AMD: ollama-rocm · then systemctl enable --now "
                              "ollama. Tip: the model shares the graphics card with VR – use small models (3–7B)."},
    "tr_vision_install": {"de": "Ollama installieren", "en": "Install Ollama"},
    "tr_vision_installing": {"de": "⏳ Installation läuft im Terminal (Passwort dort eingeben) – danach 🔄 Prüfen",
                             "en": "⏳ Installing in the terminal (enter your password there) – then 🔄 Check"},
    "tr_vision_install_manual": {"de": "Kein Terminal gefunden – selbst ausführen: {cmd}",
                                 "en": "No terminal found – run it yourself: {cmd}"},
    "tr_vision_check": {"de": "Prüfen",           "en": "Check"},
    "tr_vision_pull":  {"de": "Modell laden",     "en": "Download model"},
    "tr_vision_ok":    {"de": "✔ Ollama läuft · {n} Bild-Modell(e): {models}",
                        "en": "✔ Ollama is running · {n} image model(s): {models}"},
    "tr_vision_no_model": {"de": "⚠ Ollama läuft, aber noch kein Bild-Modell – Modell wählen und "
                                 "📥 Modell laden",
                           "en": "⚠ Ollama is running but has no image model yet – pick one and "
                                 "📥 Download model"},
    "tr_vision_off":   {"de": "✘ Ollama nicht erreichbar ({url}) – installiert und gestartet? "
                              "systemctl enable --now ollama",
                        "en": "✘ Ollama not reachable ({url}) – installed and started? "
                              "systemctl enable --now ollama"},
    "tr_vision_pull_manual": {"de": "Kein Terminal/Ollama gefunden – selbst ausführen: ollama pull {model}",
                              "en": "No terminal/Ollama found – run it yourself: ollama pull {model}"},
    "tr_vision_keep":  {"de": "Im Grafikspeicher lassen", "en": "Keep in graphics memory"},
    "tr_vision_keep_30s": {"de": "30 s (VR bekommt den Speicher schnell zurück)",
                           "en": "30 s (VR gets the memory back quickly)"},
    "tr_vision_keep_2m": {"de": "2 min", "en": "2 min"},
    "tr_vision_keep_10m": {"de": "10 min", "en": "10 min"},
    "tr_vision_keep_forever1": {"de": "Immer (schnellste Antwort)", "en": "Always (fastest answer)"},
    "tr_vision_url":   {"de": "Adresse",          "en": "Address"},
    "panel_card":      {"de": "Übersetzungs-Panel in VR", "en": "Translation panel in VR"},
    "panel_hint":      {"de": "Ein Fenster in VR: oben das Foto mit Nummern ①②③ auf den Textzeilen, darunter "
                              "die Übersetzungen 1, 2, 3 – dazu Dienst, Aufgabe und Sprachen per Laser. "
                              "Zeig mit dem Controller drauf und drück den Trigger (einmal Layer neu bauen).",
                        "en": "A window in VR: the photo with numbers ①②③ on the text lines on top, the "
                              "translations 1, 2, 3 below – plus service, task and languages via laser. "
                              "Point at it with the controller and press the trigger (rebuild the layer once)."},
    "panel_on":        {"de": "🪟 Panel in VR anzeigen", "en": "🪟 Show panel in VR"},
    "panel_anchor":    {"de": "Hängt an",         "en": "Attached to"},
    "panel_anchor_left": {"de": "🤚 Linke Hand",   "en": "🤚 Left hand"},
    "panel_anchor_right": {"de": "✋ Rechte Hand", "en": "✋ Right hand"},
    "panel_anchor_head": {"de": "👤 Kopf (wandert mit)", "en": "👤 Head (follows you)"},
    "panel_anchor_world": {"de": "🌍 Welt (bleibt im Raum)", "en": "🌍 World (stays in the room)"},
    "panel_edit_mode": {"de": "✥ Bearbeiten (Position + Größe ändern)", "en": "✥ Edit (move + resize)"},
    "panel_edit_hint": {"de": "Im Bearbeiten-Modus hat das Panel einen gelben Rand: Laser drauf + Grip halten = "
                              "verschieben · Ecke unten rechts (leuchtet) + Trigger halten = Breite, Ecke oben links = Höhe. "
                              "Geht auch im Panel selbst (✥). Grip/Trigger kommen trotzdem im Spiel an.",
                        "en": "In edit mode the panel has a yellow border: laser on it + hold grip = move · laser "
                              "on the bottom right corner (lights up) + hold trigger = width, top left corner = height. Also works "
                              "inside the panel (✥). Grip/trigger still reach the game."},
    "panel_opacity":   {"de": "Deckkraft",        "en": "Opacity"},
    "panel_edit_help": {"de": "Panel und 🔘 Knopf je einzeln: Laser drauf + Grip = verschieben/drehen · "
                              "Ecke unten rechts + Trigger = Größe · Panel: Ecke oben links + Trigger = Höhe · ⟲ = zurücksetzen",
                        "en": "Panel and 🔘 button each on their own: laser on it + grip = move/rotate · "
                              "bottom right corner + trigger = size · panel: top left corner + trigger = height · ⟲ = reset"},
    "panel_settings":  {"de": "Einstellungen", "en": "Settings"},
    "vr_delete_sure":  {"de": "Wirklich löschen?", "en": "Really delete?"},
    "month_1": {"de": "Januar", "en": "January"},
    "month_2": {"de": "Februar", "en": "February"},
    "month_3": {"de": "März", "en": "March"},
    "month_4": {"de": "April", "en": "April"},
    "month_5": {"de": "Mai", "en": "May"},
    "month_6": {"de": "Juni", "en": "June"},
    "month_7": {"de": "Juli", "en": "July"},
    "month_8": {"de": "August", "en": "August"},
    "month_9": {"de": "September", "en": "September"},
    "month_10": {"de": "Oktober", "en": "October"},
    "month_11": {"de": "November", "en": "November"},
    "month_12": {"de": "Dezember", "en": "December"},
    "gallery_folders": {"de": "Galerie-Ordner", "en": "Gallery folders"},
    "gallery_folders_hint": {"de": "Diese Ordner zeigt die Galerie (Desktop + VR). Übersetzt wird nur, was ViewShot fotografiert.",
                             "en": "The gallery (desktop + VR) shows these folders. Only photos taken by ViewShot are translated."},
    "gallery_subfolders": {"de": "Unterordner einbeziehen", "en": "Include subfolders"},
    "gallery_add_folder": {"de": "Ordner hinzufügen …", "en": "Add folder …"},
    "gallery_change_folder": {"de": "Ändern …", "en": "Change …"},
    "gallery_remove_folder": {"de": "Entfernen", "en": "Remove"},
    "gallery_main_folder": {"de": "Foto-Ordner (ViewShot)", "en": "Photo folder (ViewShot)"},
    "gallery_settings": {"de": "Galerie-Ordner einstellen", "en": "Gallery folder settings"},
    "upload_copy_link": {"de": "Hochladen + Link", "en": "Upload + link"},
    "vr_copied_image": {"de": "✔ Bild kopiert", "en": "✔ Image copied"},
    "vr_link_copied":  {"de": "✔ Link kopiert", "en": "✔ Link copied"},
    "vr_uploading":    {"de": "⏳ Wird hochgeladen …", "en": "⏳ Uploading …"},
    "vr_upload_failed": {"de": "✘ Hochladen fehlgeschlagen", "en": "✘ Upload failed"},
    "vr_shared_paste": {"de": "✔ Bild kopiert – im Programm Strg+V drücken", "en": "✔ Image copied – press Ctrl+V in the app"},
    "vr_shared":       {"de": "✔ Geöffnet", "en": "✔ Opened"},
    "vr_share_none":   {"de": "Kein Programm zum Teilen gefunden", "en": "No app to share with found"},
    "vr_info_folder":  {"de": "Ordner", "en": "Folder"},
    "vr_info_date":    {"de": "Datum", "en": "Date"},
    "vr_info_size":    {"de": "Größe", "en": "Size"},
    "vr_info_type":    {"de": "Typ", "en": "Type"},
    "vr_info_link":    {"de": "Link", "en": "Link"},
    "vr_page_translate": {"de": "Übersetzung", "en": "Translation"},
    "welcome_title":   {"de": "Willkommen bei LinuxVR-ViewShot", "en": "Welcome to LinuxVR-ViewShot"},
    "welcome_1":       {"de": "Diese App ist nur zum Einstellen und Installieren.\n\nNach der Installation kannst du "
                              "sie schließen und alles in VR machen – Fotos, Übersetzung, Galerie und Einstellungen "
                              "gibt es dort im 🪟 Panel.",
                        "en": "This app is only for setting things up and installing.\n\nAfter installing you can close "
                              "it and do everything in VR – photos, translation, gallery and settings are all in the "
                              "🪟 panel there."},
    "welcome_2":       {"de": "Damit in VR alles funktioniert, musst du gleich installieren (OpenXR-Layer + "
                              "Hintergrund-Dienst).",
                        "en": "To make everything work in VR you need to install now (OpenXR layer + background "
                              "service)."},
    "welcome_3":       {"de": "Bitte richte jetzt deine Übersetzer ein (Dienst, Sprachen, KI).\n\nMit OK geht's direkt "
                              "zu Optionen → Übersetzung.",
                        "en": "Please set up your translators now (service, languages, AI).\n\nOK takes you straight "
                              "to Options → Translation."},
    "welcome_next":    {"de": "Weiter", "en": "Next"},
    "welcome_install_now": {"de": "🔧  Jetzt installieren", "en": "🔧  Install now"},
    "welcome_later":   {"de": "Später", "en": "Later"},
    "ok":              {"de": "OK", "en": "OK"},
    "panel_button":    {"de": "🔘 Knopf zum Auf-/Zuklappen", "en": "🔘 Button to open/close"},
    "panel_button_short": {"de": "🔘 Knopf", "en": "🔘 Button"},
    "panel_button_hint": {"de": "Wie bei WayVR: ein Knopf am selben Anker wie das Panel (Standard: oben auf der Hand) – "
                                "Laser + Trigger klappt das Panel auf und zu. Im Bearbeiten-Modus Knopf und Panel einzeln "
                                "verschieben, drehen und vergrößern (z. B. neben das WayVR-Handgelenk-Menü).",
                          "en": "Like WayVR: a button on the same anchor as the panel (default: on top of the hand) – laser + "
                                "trigger opens and closes the panel. In edit mode move, rotate and resize button and panel "
                                "separately (e.g. next to the WayVR wrist menu)."},
    "panel_open_on_shot": {"de": "Beim Übersetzen öffnen (zugeklapptes Panel geht nach einem Foto auf)",
                           "en": "Open when translating (a closed panel opens after a photo)"},
    "panel_open_on_shot_short": {"de": "Nach Foto öffnen", "en": "Open after photo"},
    "panel_button_size": {"de": "Knopf-Größe", "en": "Button size"},
    "panel_button_color": {"de": "Knopf-Farbe", "en": "Button colour"},
    "panel_button_pick": {"de": "Farbe wählen …", "en": "Pick colour …"},
    "panel_size":      {"de": "Größe", "en": "Size"},
    "panel_size_later": {"de": "(erst möglich, wenn das Panel einmal in VR zu sehen war)",
                         "en": "(possible once the panel has been shown in VR)"},
    "panel_move":      {"de": "Verschieben (Grip)", "en": "Move (grip)"},
    "panel_anchor_short_left": {"de": "🤚 Links", "en": "🤚 Left"},
    "panel_anchor_short_right": {"de": "✋ Rechts", "en": "✋ Right"},
    "panel_anchor_short_head": {"de": "👤 Kopf", "en": "👤 Head"},
    "panel_anchor_short_world": {"de": "🌍 Welt", "en": "🌍 World"},
    "detect_short_auto": {"de": "🤖 Automatisch", "en": "🤖 Automatic"},
    "detect_short_manual": {"de": "✋ Manuell", "en": "✋ Manual"},
    "combo_short_left": {"de": "Links", "en": "Left"},
    "combo_short_right": {"de": "Rechts", "en": "Right"},
    "combo_short_both": {"de": "Beide", "en": "Both"},
    "panel_reset":     {"de": "Position zurücksetzen", "en": "Reset position"},
    "panel_edit":      {"de": "Bearbeiten",       "en": "Edit"},
    "panel_done":      {"de": "Fertig",           "en": "Done"},
    "daemon_card":     {"de": "Ohne App (Hintergrund-Dienst)", "en": "Without the app (background service)"},
    "daemon_hint":     {"de": "Übersetzen, 🪟 Panel und 🔁 Lens funktionieren auch, wenn diese App zu ist: ein "
                              "kleiner Dienst startet mit dem VR-Spiel und beendet sich danach. Ist die App offen, "
                              "macht sie alles selbst – Galerie und Verlauf zeigen, was der Dienst übersetzt hat.",
                        "en": "Translating, the 🪟 panel and 🔁 Lens also work while this app is closed: a small "
                              "service starts with the VR game and quits afterwards. While the app is open it does "
                              "everything itself – gallery and history show what the service translated."},
    "daemon_start":    {"de": "Starten", "en": "Start"},
    "daemon_off":      {"de": "Aus (nur mit offener App)", "en": "Off (only with the app open)"},
    "daemon_all":      {"de": "Bei jedem VR-Spiel", "en": "With every VR game"},
    "daemon_selected": {"de": "Nur bei ausgewählten Spielen", "en": "Only with selected games"},
    "daemon_games_hint": {"de": "Spiele, in denen der Layer zuletzt lief – oder Namen selbst eintragen "
                                "(Teilwort reicht, z. B. „vrchat“).",
                          "en": "Games the layer ran in recently – or type a name yourself "
                                "(part of the name is enough, e.g. “vrchat”)."},
    "daemon_game_placeholder": {"de": "Spielname, z. B. VRChat", "en": "Game name, e.g. VRChat"},
    "daemon_not_installed": {"de": "Dienst noch nicht eingerichtet – auf der Main-Seite einmal 🔧 Neu bauen.",
                             "en": "Service not set up yet – press 🔧 Rebuild on the main page once."},
    "daemon_off_status": {"de": "Aus – ohne offene App wird nichts übersetzt.",
                          "en": "Off – nothing is translated while the app is closed."},
    "daemon_ready":    {"de": "Eingerichtet – startet von selbst mit dem VR-Spiel (Log: ~/.local/state/"
                              "linuxvr-viewshot/daemon.log).",
                        "en": "Set up – starts by itself with the VR game (log: ~/.local/state/"
                              "linuxvr-viewshot/daemon.log)."},
    "overlay_card":    {"de": "🔁 Lens: Übersetzung über dem Original", "en": "🔁 Lens: translation over the original"},
    "overlay_hint":    {"de": "Nur bei 🔁 Lens: legt über jede erkannte Zeile ein graues Kästchen mit der "
                              "Übersetzung – fest in der Welt, genau über dem Originaltext. Fotos stehen im 🪟 Panel.",
                        "en": "🔁 Lens only: puts a grey box with the translation over every recognised line – "
                              "fixed in the world, right over the original text. Photos are shown in the 🪟 panel."},
    "overlay_on":      {"de": "🥽 Übersetzung über dem Text anzeigen", "en": "🥽 Show translation over the text"},
    "tr_favorites":    {"de": "Favoriten",        "en": "Favourites"},
    "tr_route":       {"de": "Modus", "en": "Mode"},
    "tr_route_auto":  {"de": "🤖 Automatisch", "en": "🤖 Automatic"},
    "tr_route_manual": {"de": "✋ Manuell", "en": "✋ Manual"},
    "tr_route_hint_auto": {"de": "Bei jedem Foto entscheidet die Main-KI: normalen Text übersetzt sie selbst, "
                                 "Erklärungen und Quiz gehen an die KI darunter. Aufgabe auf der Main-Seite / "
                                 "im VR-Panel umstellen gilt nur fürs aktuelle + nächste Foto.",
                           "en": "For every photo the main AI decides: it translates normal text itself, "
                                 "explanations and quizzes go to the AI below. Changing the task on the main "
                                 "page / in the VR panel only counts for the current + next photo."},
    "tr_route_hint_manual": {"de": "Du wählst die Aufgabe auf der Main-Seite / im VR-Panel – jede Aufgabe "
                                   "nimmt fest ihre KI. Nichts stellt sich von selbst um.",
                             "en": "You pick the task on the main page / in the VR panel – each task always "
                                   "uses its AI. Nothing switches by itself."},
    "tr_route_hint_noai": {"de": "✋ Manuell – ein Übersetzer wie LibreTranslate kann nicht entscheiden, was "
                                 "im Foto ist. Für Automatisch eine KI als Main wählen.",
                           "en": "✋ Manual – a translator like LibreTranslate can't decide what's in the "
                                 "photo. Pick an AI as main for automatic."},
    "tr_main":        {"de": "Main", "en": "Main"},
    "tr_group_plain": {"de": "Übersetzung", "en": "Translation"},
    "tr_group_ai":    {"de": "KI-Übersetzung", "en": "AI translation"},
    "tr_settings_for": {"de": "Einstellungen für", "en": "Settings for"},
    "main_page_card": {"de": "Main-Seite", "en": "Main page"},
    "tr_tasks_same":  {"de": "Wie Main", "en": "Same as main"},
    "tr_tasks_off":   {"de": "— aus (nur übersetzen)", "en": "— off (translate only)"},
    "tr_answer_not_ready": {"de": "Dieser Dienst ist noch nicht eingerichtet – bis dahin wird der normale "
                                  "Dienst genommen.",
                            "en": "This service is not set up yet – the normal service is used until then."},
    "tr_favorites_hint": {"de": "Nur angehakte Dienste stehen auf der Main-Seite im Dropdown. "
                                "Nichts angehakt = alle eingerichteten Dienste (wie bisher). "
                                "Nicht eingerichtete Favoriten erscheinen erst, wenn sie eingerichtet sind.",
                          "en": "Only ticked services appear in the Main page dropdown. "
                                "Nothing ticked = all services that are set up (as before). "
                                "Favourites that aren't set up only appear once they are."},
    "tr_only_configured": {"de": "Auf der Main-Seite stehen nur Dienste, die eingerichtet sind "
                                 "(Key eingetragen / Programm installiert).",
                           "en": "The Main page only lists services that are set up "
                                 "(key entered / program installed)."},
    "tr_source":       {"de": "Übersetzen von",  "en": "Translate from"},
    "tr_target":       {"de": "Übersetzen nach", "en": "Translate to"},
    "tr_from":         {"de": "Von",             "en": "From"},
    "tr_to":           {"de": "Nach",            "en": "To"},
    "tr_via":          {"de": "Dienst",          "en": "Service"},
    "tr_libre_not_installed": {"de": "LibreTranslate ist nicht als Programm installiert "
                                     "(egal, wenn es in Docker läuft)",
                               "en": "LibreTranslate is not installed as a program "
                                     "(fine if it runs in Docker)"},
    "libre_checking":  {"de": "Suche LibreTranslate-Server …", "en": "Looking for a LibreTranslate server …"},
    "libre_running":   {"de": "✔ Server läuft: {url}", "en": "✔ Server is running: {url}"},
    "libre_running_other": {"de": "✔ Server läuft unter {url} (nicht unter der eingestellten Adresse)",
                            "en": "✔ Server is running at {url} (not at the configured address)"},
    "libre_not_running": {"de": "✘ Kein Server gefunden (eingestellte Adresse und Port 5000 geprüft)",
                          "en": "✘ No server found (checked the configured address and port 5000)"},
    "use_this":        {"de": "Übernehmen",      "en": "Use this"},
    "check_again":     {"de": "Prüfen",          "en": "Check"},
    "tr_auto":         {"de": "Neues Foto automatisch übersetzen",
                        "en": "Translate new photos automatically"},
    "api_key":         {"de": "API-Key",         "en": "API key"},
    "api_key_optional": {"de": "API-Key (optional)", "en": "API key (optional)"},
    "server":          {"de": "Server",          "en": "Server"},
    "tr_lingva_info":  {"de": "Anonymer Proxy für Google Translate – nichts einzurichten.",
                        "en": "Anonymous proxy for Google Translate – nothing to set up."},
    "tr_google_info":  {"de": "Ohne Key wird der freie Web-Zugang benutzt (kann gebremst werden). "
                              "Mit eigenem Google-Cloud-Key: offizielle API.",
                        "en": "Without a key the free web endpoint is used (may be rate-limited). "
                              "With your own Google Cloud key: official API."},
    "tr_libre_info":   {"de": "LibreTranslate musst du selbst installieren und starten, z. B.:\n"
                              "  pipx install libretranslate   (oder AUR: libretranslate)\n"
                              "  libretranslate --port 5000\n"
                              "oder per Docker:\n"
                              "  docker run -d -p 5000:5000 libretranslate/libretranslate\n"
                              "Läuft komplett offline auf deinem PC.",
                        "en": "You have to install and start LibreTranslate yourself, e.g.:\n"
                              "  pipx install libretranslate   (or AUR: libretranslate)\n"
                              "  libretranslate --port 5000\n"
                              "or with Docker:\n"
                              "  docker run -d -p 5000:5000 libretranslate/libretranslate\n"
                              "Runs completely offline on your PC."},
    "tr_libre_found":  {"de": "✔ LibreTranslate ist installiert", "en": "✔ LibreTranslate is installed"},
    "tr_libre_missing": {"de": "✘ LibreTranslate nicht gefunden", "en": "✘ LibreTranslate not found"},
    "tr_online_info":  {"de": "Öffentlicher LibreTranslate-Server – nichts zu installieren. "
                              "de.libretranslate.com ist die Vorlage (verlangt inzwischen einen Key); "
                              "unter „Custom server …“ kannst du jede eigene Adresse eintragen.",
                        "en": "Public LibreTranslate server – nothing to install. "
                              "de.libretranslate.com is the preset (now requires a key); "
                              "use “Custom server …” for any address of your own."},
    "tr_deepl_info":   {"de": "Beste Qualität. Kostenloser Key: deepl.com/pro-api (500.000 Zeichen/Monat).",
                        "en": "Best quality. Free key: deepl.com/pro-api (500,000 characters/month)."},
    "tr_custom_info":  {"de": "curl-Befehl, Programm oder .py-Datei. {text} {source} {target} "
                              "werden von der App ausgefüllt.",
                        "en": "curl command, program or .py file. {text} {source} {target} "
                              "are filled in by the app."},
    "tr_reset_example": {"de": "Vorlage einsetzen", "en": "Insert template"},
    "tr_test":         {"de": "Testen",          "en": "Test"},
    "tr_test_text":    {"de": "Hello, this is a test.", "en": "Hallo, das ist ein Test."},
    "tr_testing":      {"de": "Teste …",         "en": "Testing …"},
    "ocr_missing":     {"de": "Texterkennung fehlt – installieren mit:  {cmd}",
                        "en": "Text recognition missing – install with:  {cmd}"},
    "ocr_ok":          {"de": "✔ Texterkennung (RapidOCR) ist installiert",
                        "en": "✔ Text recognition (RapidOCR) is installed"},

    # Main – Übersetzung
    "translation":     {"de": "Übersetzung",     "en": "Translation"},
    "translate_btn":   {"de": "Übersetzen",      "en": "Translate"},
    "translating":     {"de": "Liest Text und übersetzt …", "en": "Reading text and translating …"},
    "no_text":         {"de": "Kein Text im Foto gefunden.", "en": "No text found in the photo."},
    "recognized":      {"de": "Erkannter Text",  "en": "Recognised text"},
    "tr_failed":       {"de": "✘ Übersetzen fehlgeschlagen", "en": "✘ Translation failed"},
    "tr_popout":       {"de": "Übersetzung in eigenem Fenster öffnen",
                        "en": "Open translation in its own window"},
    "tr_dock":         {"de": "Zurück ins Hauptfenster", "en": "Back into the main window"},
    "tr_popped_out":   {"de": "Die Übersetzung ist in einem eigenen Fenster.",
                        "en": "The translation is in its own window."},
    "qr_in_text":      {"de": "QR-Code",         "en": "QR code"},
    "qr_copied":       {"de": "✔ QR-Inhalt kopiert", "en": "✔ QR content copied"},

    # Paket installieren (z. B. npm für die KI-CLIs)
    "pkg_installing":  {"de": "Installiere …",   "en": "Installing …"},
    "pkg_password":    {"de": "Passwort-Fenster erscheint auf dem Desktop …",
                        "en": "Password window appears on the desktop …"},

    # Optionen
    "language":        {"de": "Sprache",         "en": "Language"},
    "folders":         {"de": "Ordner & Dateien", "en": "Folders & files"},
    "photo_folder":    {"de": "Foto-Ordner",     "en": "Photo folder"},
    "log_file":        {"de": "Layer-Log",       "en": "Layer log"},
    "open":            {"de": "Öffnen",          "en": "Open"},
    "about":           {"de": "Über",            "en": "About"},
}

# Französisch steht in einer eigenen Datei (leichter zu prüfen) → hier einsortieren
from core.i18n_fr import FR  # noqa: E402

for _key, _text in FR.items():
    if _key in TEXTS:
        TEXTS[_key]["fr"] = _text

LANGUAGES = ("de", "en", "fr")
_lang = "de"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else "de"


def month_title(year: int, month: int) -> str:
    """Monats-Trenner in der Galerie: „2026 Oktober“."""
    return f"{year} {tr(f'month_{month}')}"


def tr(key: str, **kwargs) -> str:
    """Text in der aktuellen Sprache. Fehlt ein Schlüssel, wird er selbst angezeigt."""
    entry = TEXTS.get(key, {})
    text = entry.get(_lang) or entry.get("en") or key  # fehlt Französisch → Englisch
    return text.format(**kwargs) if kwargs else text
