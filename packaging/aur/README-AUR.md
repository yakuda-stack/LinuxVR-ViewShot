# AUR: linuxvr-viewshot

Paket: https://aur.archlinux.org/packages/linuxvr-viewshot (nach dem ersten Push)
Installation für Nutzer: `yay -S linuxvr-viewshot` (oder paru).

Das PKGBUILD baut den OpenXR-Layer aus dem GitHub-Tag (Rust, `cargo build --frozen`):

| Was | Wohin |
|---|---|
| Layer (fertig gebaut) | `/usr/lib/linuxvr-viewshot/liblinuxvr_viewshot_layer.so` |
| Manifest-**Vorlage** | `/usr/share/linuxvr-viewshot/manifest/linuxvr_viewshot.json.in` |
| App | `/usr/share/linuxvr-viewshot/UI/` + Befehl `/usr/bin/linuxvr-viewshot` |
| Startmenü + Icon | `/usr/share/applications/…`, `/usr/share/icons/hicolor/512x512/apps/…` |

⚠️ **Kein systemweites Manifest in `/usr/share/openxr`!** Steam-/Proton-Spiele (VRChat)
laufen im Steam-Container (pressure-vessel) – dort ist `/usr` nicht das `/usr` des Systems,
ein systemweiter Layer wäre für sie unsichtbar. Der Home-Ordner ist sichtbar. Deshalb:
**App einmal öffnen → „Installieren“** kopiert den Layer nach `~/.local` (wie bei der
AppImage). Nach Paket-Updates zieht die App ihn beim nächsten Start selbst nach.
Das sagt auch `linuxvr-viewshot.install` nach `pacman -S` / `-Syu` an.

Paket-Version 0.4.1 (erste Fassung) hatte noch ein systemweites Manifest – die App erkennt
das und zeigt „⚠ alte systemweite Kopie – Paket aktualisieren“.

---

## Einmalig: das Paket im AUR anlegen

1. **AUR-Account + SSH-Key** – hast du schon (gleicher Key wie bei osc-dreamchatbox).
2. **GitHub:** Projekt pushen und den Tag setzen – das PKGBUILD lädt
   `…/archive/refs/tags/v0.4.0.tar.gz`, ohne Tag gibt es 404.
   (Release-Launcher → LinuxVR-ViewShot → 3 · GitHub → Commit + Push, Tag setzen + Push)
3. **Leeres AUR-Repo klonen** – der Name wird dabei reserviert:
   ```bash
   git clone ssh://aur@aur.archlinux.org/linuxvr-viewshot.git ~/aur/linuxvr-viewshot
   ```
   („warning: You appear to have cloned an empty repository“ ist richtig so.)
4. **.gitignore anlegen** (nur PKGBUILD, linuxvr-viewshot.install + .SRCINFO kommen ins AUR):
   ```bash
   cp packaging/aur/gitignore-fuer-aur-repo ~/aur/linuxvr-viewshot/.gitignore
   ```
5. Ab hier wie bei jedem Update (unten) – im Release-Launcher Gruppe **5 · AUR** von oben nach unten.
   Beim allerersten Commit zusätzlich die .gitignore mitnehmen:
   ```bash
   cd ~/aur/linuxvr-viewshot && git add .gitignore
   ```

## Update-Ablauf (neue Version) – Release-Launcher, Projekt „LinuxVR-ViewShot“

1. **1 · Version:** Version eintragen → „Version setzen“
   (setzt `UI/core/version.py`, `layer/Cargo.toml`, `Cargo.lock`, `packaging/aur/PKGBUILD`, pkgrel=1)
2. `CHANGELOG.md` oben einen Block `## [vX.Y.Z] – Datum` schreiben
3. **2 · Testen:** „Alle Tests nacheinander“ (pytest, Smoke-Test, Rust-Tests, shellcheck, Desktop-Datei)
4. **3 · GitHub:** Verbotene Dateien? → Commit + Push → Tag setzen + Push
5. **4 · Release:** AppImage bauen → Quell-Archiv packen → GitHub-Release-Seite öffnen
   (hochladen: AppImage + .zsync + .tar.gz, KEIN Pre-release)
6. **5 · AUR:** PKGBUILD kopieren (nimmt die .install mit) → Aufräumen → Version prüfen → updpkgsums
   → Bauen + installieren → Installiertes Paket testen → .SRCINFO + Commit → AUR Push
7. App öffnen → **Installieren** (bzw. nach Updates passiert das beim Start automatisch)

Von Hand (ohne Launcher):
```bash
cp packaging/aur/PKGBUILD packaging/aur/linuxvr-viewshot.install ~/aur/linuxvr-viewshot/
cd ~/aur/linuxvr-viewshot
updpkgsums                              # holt die sha256 des Tags
makepkg -si                             # bauen + installieren, dann testen
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD linuxvr-viewshot.install .SRCINFO && git commit -m "Update to v0.4.1" && git push origin master
```

## Regeln / Stolperfallen
- **Tag zuerst**, sonst 404 bei `updpkgsums`.
- **.SRCINFO** bei JEDER Änderung neu erzeugen – sonst lehnt das AUR den Push ab.
- **pkgrel:** neue App-Version → 1; nur Packaging geändert → +1.
- **pkgver** ohne Bindestrich: `0.5.0_alpha` (der Tag `v0.5.0-alpha` wird über `_tag` gebaut).
- Ins AUR-Repo **nur** PKGBUILD + linuxvr-viewshot.install + .SRCINFO (+ .gitignore) – nie Quellcode, nie `src/`, `pkg/`, `*.pkg.tar.zst`.
- Branch: Projekt = `main`, AUR = `master`.
- `namcap PKGBUILD` und `namcap *.pkg.tar.zst` zeigen typische Paketfehler (`sudo pacman -S namcap`).
- Nach dem Push dauert `yay -Ss linuxvr-viewshot` manchmal Stunden (Suchindex);
  `yay -S linuxvr-viewshot` klappt sofort.
