"""
core/i18n.py – Übersetzungen EN/DE.

Benutzung:   tr("nav_main")   → "Main"
Neuer Text?  Unten in TEXTS eine Zeile mit "de" und "en" eintragen.
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
    "howto_4":         {"de": "4.  Manuell: Typ-Trigger (Standard: links) schaltet das Symbol unten rechts "
                              "im Rahmen um – 🖼 Bild → 📝 Text → 🔳 QR. Das Foto bekommt diesen Typ.",
                        "en": "4.  Manual: the type trigger (default: left) switches the icon in the frame's "
                              "bottom-right corner – 🖼 Image → 📝 Text → 🔳 QR. The photo gets that type."},
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
    "buttons_auto_note": {"de": "Typ wechseln gibt es nur im manuellen Modus.",
                          "en": "Switching type is only available in manual mode."},
    "buttons_manual_note": {"de": "Im Rahmen erscheint unten rechts ein Symbol (🖼 / 📝 / 🔳). "
                                  "Auslöser und Typ-Taste können nicht gleich sein.",
                            "en": "An icon (🖼 / 📝 / 🔳) appears in the frame's bottom-right corner. "
                                  "Shutter and type button can't be the same."},
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
    "wayvr_title":     {"de": "WayVR: Design von Cubee + ViewShot-Knopf", "en": "WayVR: Cubee's theme + ViewShot button"},
    "wayvr_hint":      {"de": "Installiert Cubees Design für WayVR (Uhr, Farben, Sounds) nach ~/.config/wayvr. "
                              "Der Knopf „Chatbox öffnen“ auf der Uhr wird zu „LinuxVR-ViewShot“ und öffnet "
                              "diese App als Fenster in VR. Deine eigenen WayVR-Einstellungen und die "
                              "Controller-Belegung bleiben; überschriebene Dateien kommen vorher in ein Backup.",
                        "en": "Installs Cubee's WayVR theme (watch, colours, sounds) to ~/.config/wayvr. "
                              "The watch's “Open Chatbox” button becomes “LinuxVR-ViewShot” and opens this "
                              "app as a window in VR. Your own WayVR settings and controller bindings stay; "
                              "overwritten files are backed up first."},
    "wayvr_install":   {"de": "WayVR-Design + App-Knopf auf der Uhr installieren",
                        "en": "Install WayVR theme + app button on the watch"},
    "wayvr_reinstall": {"de": "WayVR-Design + App-Knopf neu installieren",
                        "en": "Reinstall WayVR theme + app button"},
    "wayvr_installing": {"de": "Lädt von GitHub …", "en": "Downloading from GitHub …"},
    "wayvr_source":    {"de": "Quelle",          "en": "Source"},
    "wayvr_ok":        {"de": "✔ {n} Dateien installiert nach {path}", "en": "✔ {n} files installed to {path}"},
    "wayvr_backup":    {"de": "Backup der alten Dateien: {path}", "en": "Backup of the old files: {path}"},
    "wayvr_no_button": {"de": "⚠ Chatbox-Knopf nicht gefunden – Cubees Uhr hat sich geändert, "
                              "ViewShot-Knopf fehlt.",
                        "en": "⚠ Chatbox button not found – Cubee's watch has changed, "
                              "ViewShot button missing."},
    "wayvr_no_ctl":    {"de": "⚠ wayvrctl nicht gefunden – der Knopf öffnet die App dann auf dem Desktop "
                              "statt in WayVR.",
                        "en": "⚠ wayvrctl not found – the button will open the app on the desktop "
                              "instead of inside WayVR."},
    "wayvr_restart":   {"de": "WayVR neu starten, damit das Design geladen wird.",
                        "en": "Restart WayVR to load the theme."},
    "wayvr_failed":    {"de": "✘ Installation fehlgeschlagen", "en": "✘ Installation failed"},
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

    # Optionen
    "language":        {"de": "Sprache",         "en": "Language"},
    "folders":         {"de": "Ordner & Dateien", "en": "Folders & files"},
    "photo_folder":    {"de": "Foto-Ordner",     "en": "Photo folder"},
    "log_file":        {"de": "Layer-Log",       "en": "Layer log"},
    "open":            {"de": "Öffnen",          "en": "Open"},
    "about":           {"de": "Über",            "en": "About"},
}

_lang = "de"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in ("de", "en") else "de"


def tr(key: str, **kwargs) -> str:
    """Text in der aktuellen Sprache. Fehlt ein Schlüssel, wird er selbst angezeigt."""
    text = TEXTS.get(key, {}).get(_lang, key)
    return text.format(**kwargs) if kwargs else text
