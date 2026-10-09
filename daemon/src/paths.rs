//! Pfade – dieselben wie in der App (UI/core/paths.py) und im Layer (save.rs / log.rs).

use std::path::PathBuf;

fn home() -> PathBuf {
    dirs::home_dir().unwrap_or_else(|| PathBuf::from("/tmp"))
}

/// ~/.config/linuxvr-viewshot (ui.json, layer.json, translations.json …)
pub fn config_dir() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .unwrap_or_else(|| home().join(".config"))
        .join("linuxvr-viewshot")
}

/// ~/.local/state/linuxvr-viewshot (Logs, Sperr-Datei der App)
pub fn state_dir() -> PathBuf {
    std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .unwrap_or_else(|| home().join(".local/state"))
        .join("linuxvr-viewshot")
}

/// ~/.local/lib/linuxvr-viewshot – Layer, Dienst, onnxruntime, OCR-Modelle
pub fn lib_dir() -> PathBuf {
    home().join(".local/lib/linuxvr-viewshot")
}

static PHOTO_DIR: std::sync::Mutex<Option<PathBuf>> = std::sync::Mutex::new(None);

/// Foto-Ordner, den der Layer meldet („hello“) – gilt vor allem anderen
pub fn set_photo_dir(dir: PathBuf) {
    *PHOTO_DIR.lock().unwrap_or_else(|e| e.into_inner()) = Some(dir);
}

/// Foto-Ordner: vom Layer gemeldet, sonst $VIEWSHOT_OUTPUT_DIR oder ~/Bilder/LinuxVR-ViewShot
pub fn photo_dir() -> PathBuf {
    if let Some(dir) = PHOTO_DIR.lock().unwrap_or_else(|e| e.into_inner()).clone() {
        return dir;
    }
    if let Some(dir) = std::env::var_os("VIEWSHOT_OUTPUT_DIR").filter(|d| !d.is_empty()) {
        return PathBuf::from(dir);
    }
    dirs::picture_dir().unwrap_or_else(|| home().join("Pictures")).join("LinuxVR-ViewShot")
}

pub fn live_file() -> PathBuf {
    photo_dir().join("live").join("live.png")
}

pub fn panel_file() -> PathBuf {
    photo_dir().join("panel").join("panel.png")
}

pub fn overlay_file() -> PathBuf {
    photo_dir().join("overlay").join("overlay.png")
}

pub fn panel_pose_file() -> PathBuf {
    config_dir().join("panel_pose.json")
}

/// 🔘 Position/Größe des Knopfs (legt der Layer an)
pub fn button_pose_file() -> PathBuf {
    config_dir().join("button_pose.json")
}

/// Solange die App diese Datei gesperrt hält (flock), macht sie alles selbst.
pub fn app_lock_file() -> PathBuf {
    state_dir().join("app.lock")
}

pub fn log_file() -> PathBuf {
    state_dir().join("daemon.log")
}

/// Ist das PNG fertig geschrieben? (endet mit IEND – wie paths.photo_ready)
pub fn photo_ready(path: &std::path::Path) -> bool {
    use std::io::{Read, Seek, SeekFrom};
    let Ok(mut f) = std::fs::File::open(path) else { return false };
    let mut head = [0u8; 8];
    if f.read_exact(&mut head).is_err() || &head != b"\x89PNG\r\n\x1a\n" {
        return false;
    }
    let mut tail = [0u8; 12];
    f.seek(SeekFrom::End(-12)).is_ok() && f.read_exact(&mut tail).is_ok() && &tail[4..8] == b"IEND"
}

/// Neuestes Foto im Foto-Ordner (nur *.png direkt darin – nicht live/ panel/ overlay/)
pub fn newest_photo() -> Option<PathBuf> {
    let rd = std::fs::read_dir(photo_dir()).ok()?;
    rd.flatten()
        .filter(|e| e.path().extension().is_some_and(|x| x.eq_ignore_ascii_case("png")))
        .filter_map(|e| Some((e.metadata().ok()?.modified().ok()?, e.path())))
        .max_by_key(|(t, _)| *t)
        .map(|(_, p)| p)
}

/// Hilfsordner im Foto-Ordner – nie in der Galerie (wie HELPER_DIRS in paths.py)
const HELPER_DIRS: [&str; 4] = ["panel", "overlay", "live", "backup"]; // backup = 🗜 Original vor dem Komprimieren
const IMAGE_EXTS: [&str; 4] = ["png", "jpg", "jpeg", "gif"]; // gif = 🎞 GIF-Aufnahmen
/// so tief in Unterordner (VRChat: VRChat/2026-10/…)
const MAX_DEPTH: usize = 4;

/// Ein Galerie-Bild: Pfad, Änderungszeit, (Jahr, Monat) für die Monats-Trenner
#[derive(Clone, Debug, PartialEq)]
pub struct GalleryPhoto {
    pub path: PathBuf,
    pub mtime: std::time::SystemTime,
    pub month: (i32, u32),
}

/// Ordner der Galerie: Foto-Ordner zuerst, dann ui.json "gallery_folders" (wie gallery_folders in paths.py)
pub fn gallery_folders(cfg: &crate::settings::Cfg) -> Vec<(PathBuf, bool)> {
    let mut found = vec![(photo_dir(), cfg.b("gallery_main_subfolders"))];
    if let Some(list) = cfg.0.get("gallery_folders").and_then(|v| v.as_array()) {
        for e in list {
            let Some(p) = e["path"].as_str().filter(|p| !p.is_empty()) else { continue };
            let path = match p.strip_prefix("~/") {
                Some(rest) => home().join(rest),
                None => PathBuf::from(p),
            };
            if !found.iter().any(|(f, _)| *f == path) {
                found.push((path, e["subfolders"].as_bool().unwrap_or(false)));
            }
        }
    }
    found
}

fn scan_folder(folder: &std::path::Path, subfolders: bool, out: &mut Vec<(PathBuf, std::time::SystemTime)>) {
    let main = folder == photo_dir();
    let mut todo = vec![(folder.to_path_buf(), 0usize)];
    while let Some((dir, depth)) = todo.pop() {
        let Ok(rd) = std::fs::read_dir(&dir) else { continue };
        for e in rd.flatten() {
            let name = e.file_name().to_string_lossy().to_string();
            if name.starts_with('.') {
                continue;
            }
            let Ok(ft) = e.file_type() else { continue };
            if ft.is_dir() {
                if subfolders && depth < MAX_DEPTH && !(main && depth == 0 && HELPER_DIRS.contains(&name.as_str())) {
                    todo.push((e.path(), depth + 1));
                }
            } else if ft.is_file() {
                let ext = e.path().extension().map(|x| x.to_string_lossy().to_lowercase()).unwrap_or_default();
                if IMAGE_EXTS.contains(&ext.as_str()) {
                    if let Ok(m) = e.metadata().and_then(|m| m.modified()) {
                        out.push((e.path(), m));
                    }
                }
            }
        }
    }
}

/// Alle Galerie-Bilder aus allen Ordnern, neueste zuerst (wie gallery_photos in paths.py)
pub fn gallery_photos(cfg: &crate::settings::Cfg) -> Vec<GalleryPhoto> {
    use chrono::Datelike;
    let mut found = Vec::new();
    for (folder, sub) in gallery_folders(cfg) {
        scan_folder(&folder, sub, &mut found);
    }
    found.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    found.dedup_by(|a, b| a.0 == b.0);
    found
        .into_iter()
        .map(|(path, mtime)| {
            let local: chrono::DateTime<chrono::Local> = mtime.into();
            GalleryPhoto { path, mtime, month: (local.year(), local.month()) }
        })
        .collect()
}

/// In den Papierkorb (freedesktop.org-Papierkorb im Home, wie jeder Dateimanager).
/// Klappt das nicht (z. B. anderes Laufwerk), versucht es `gio trash`.
pub fn trash(path: &std::path::Path) -> bool {
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .unwrap_or_else(|| home().join(".local/share"))
        .join("Trash");
    if trash_into(path, &base) {
        return true;
    }
    std::process::Command::new("gio")
        .arg("trash")
        .arg(path)
        .status()
        .is_ok_and(|s| s.success())
        && !path.exists()
}

/// Datei nach <trash>/files verschieben + <trash>/info/<Name>.trashinfo schreiben
fn trash_into(path: &std::path::Path, trash: &std::path::Path) -> bool {
    let Some(name) = path.file_name().map(|n| n.to_string_lossy().to_string()) else { return false };
    let Ok(abs) = std::fs::canonicalize(path) else { return false };
    let (files, info) = (trash.join("files"), trash.join("info"));
    if std::fs::create_dir_all(&files).is_err() || std::fs::create_dir_all(&info).is_err() {
        return false;
    }
    // freien Namen suchen: Foto.png, Foto.1.png, Foto.2.png …
    let (stem, ext) = match name.rsplit_once('.') {
        Some((s, e)) => (s.to_string(), format!(".{e}")),
        None => (name.clone(), String::new()),
    };
    let mut target = name.clone();
    let mut n = 0;
    while files.join(&target).exists() || info.join(format!("{target}.trashinfo")).exists() {
        n += 1;
        target = format!("{stem}.{n}{ext}");
    }
    let encoded: String = abs
        .to_string_lossy()
        .bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'/' | b'.' | b'_' | b'~' | b'-' => (b as char).to_string(),
            _ => format!("%{b:02X}"),
        })
        .collect();
    let text = format!("[Trash Info]\nPath={encoded}\nDeletionDate={}\n", chrono::Local::now().format("%Y-%m-%dT%H:%M:%S"));
    let info_file = info.join(format!("{target}.trashinfo"));
    if std::fs::write(&info_file, text).is_err() {
        return false;
    }
    if std::fs::rename(path, files.join(&target)).is_err() {
        let _ = std::fs::remove_file(&info_file);
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gallery_folders_and_subfolders() {
        let dir = std::env::temp_dir().join(format!("viewshot-gal-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        for f in ["p/a.png", "p/panel/panel.png", "p/sub/b.jpg", "x/c.png", "x/d/e.PNG", "x/.hidden/f.png", "x/n.txt"] {
            let path = dir.join(f);
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(&path, b"x").unwrap();
        }
        set_photo_dir(dir.join("p"));
        let mut cfg = crate::settings::Cfg::default();
        let x = dir.join("x").to_string_lossy().to_string();
        cfg.0.insert("gallery_folders".into(), serde_json::json!([{"path": x, "subfolders": false}, {"path": x, "subfolders": true}]));
        let names = |cfg: &crate::settings::Cfg| {
            let mut n: Vec<String> = gallery_photos(cfg).iter().map(|p| p.path.file_name().unwrap().to_string_lossy().to_string()).collect();
            n.sort();
            n
        };
        assert_eq!(names(&cfg), ["a.png", "c.png"]);
        cfg.0.insert("gallery_main_subfolders".into(), serde_json::json!(true));
        cfg.0.insert("gallery_folders".into(), serde_json::json!([{"path": x, "subfolders": true}]));
        assert_eq!(names(&cfg), ["a.png", "b.jpg", "c.png", "e.PNG"]);
        *PHOTO_DIR.lock().unwrap() = None;
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn trash_moves_and_writes_info() {
        let dir = std::env::temp_dir().join(format!("viewshot-trash-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let (a, b) = (dir.join("Foto 1.png"), dir.join("sub"));
        std::fs::write(&a, b"x").unwrap();
        std::fs::create_dir_all(&b).unwrap();
        let trash = dir.join("Trash");
        assert!(trash_into(&a, &trash));
        assert!(!a.exists() && trash.join("files/Foto 1.png").exists());
        let info = std::fs::read_to_string(trash.join("info/Foto 1.png.trashinfo")).unwrap();
        assert!(info.starts_with("[Trash Info]\nPath=") && info.contains("Foto%201.png"), "{info}");
        // gleicher Name nochmal → eigener Name im Papierkorb
        std::fs::write(&a, b"y").unwrap();
        assert!(trash_into(&a, &trash));
        assert!(trash.join("files/Foto 1.1.png").exists());
        assert!(!trash_into(&dir.join("gibt-es-nicht.png"), &trash));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
