//! Foto-Aktionen im VR-Panel ohne App – wie in der Desktop-Galerie:
//!   📋 Kopieren          → Zwischenablage (wie core/clipboard.py: an JEDEN Wayland-Server, sonst X11)
//!   ↗ Teilen             → Discord/Vesktop/WebCord (Bild kopieren + öffnen), Telegram, E-Mail
//!                          (wie core/share.py – auch als Flatpak, z. B. dev.vencord.Vesktop)
//!   ☁ Hochladen + Link   → directupload.eu (wie core/uploader.py), Links in uploads.json
//!   ⓘ Info              → Ordner, Datum, Größe, Typ (tags.json), Link (uploads.json)

use serde_json::Value;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

// ─────────────────────────── Programme finden ───────────────────────────

fn which(cmd: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).map(|d| d.join(cmd)).find(|p| p.is_file())
}

fn flatpak_installed(app_id: &str) -> bool {
    which("flatpak").is_some()
        && Command::new("flatpak")
            .args(["info", app_id])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|s| s.success())
}

/// Läuft der Dienst unter systemd? Dann Hilfsprogramme (wl-copy, Discord …) in einen eigenen
/// Bereich starten – sonst beendet systemd sie mit dem Dienst (Zwischenablage wäre weg).
fn detached(argv: &[&str]) -> Command {
    if std::env::var_os("INVOCATION_ID").is_some() && which("systemd-run").is_some() {
        let mut c = Command::new("systemd-run");
        c.args(["--user", "--scope", "--quiet", "--collect", "--"]).args(argv);
        c
    } else {
        let mut c = Command::new(argv[0]);
        c.args(&argv[1..]);
        c
    }
}

// ─────────────────────────── 📋 Zwischenablage ───────────────────────────

fn runtime_dir() -> PathBuf {
    std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(format!("/run/user/{}", unsafe { libc::getuid() })))
}

/// Alle Wayland-Sockets (wayland-0, wayland-1 …) – Desktop UND z. B. WayVR
fn wayland_displays() -> Vec<String> {
    use std::os::unix::fs::FileTypeExt;
    let mut found: Vec<String> = std::fs::read_dir(runtime_dir())
        .map(|rd| {
            rd.flatten()
                .filter(|e| {
                    let n = e.file_name().to_string_lossy().to_string();
                    n.strip_prefix("wayland-").is_some_and(|r| !r.is_empty() && r.chars().all(|c| c.is_ascii_digit()))
                        && e.file_type().is_ok_and(|t| t.is_socket())
                })
                .map(|e| e.file_name().to_string_lossy().to_string())
                .collect()
        })
        .unwrap_or_default();
    found.sort();
    found
}

fn feed(mut cmd: Command, data: &[u8]) -> bool {
    let Ok(mut child) = cmd.stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null()).spawn() else {
        return false;
    };
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(data);
    }
    // wl-copy/xclip geben sofort zurück (ein Kind-Prozess liefert den Inhalt aus)
    child.wait().is_ok_and(|s| s.success())
}

/// Inhalt in die Zwischenablage – an jeden Wayland-Server, sonst X11 (xclip/xsel)
pub fn copy(data: &[u8], mime: &str) -> bool {
    let mut ok = false;
    if which("wl-copy").is_some() {
        for display in wayland_displays() {
            let mut cmd = detached(&["wl-copy", "--type", mime]);
            cmd.env("WAYLAND_DISPLAY", &display);
            ok |= feed(cmd, data);
        }
    }
    if ok {
        return true;
    }
    let display = std::env::var("DISPLAY").unwrap_or_else(|_| ":0".into());
    if which("xclip").is_some() {
        let mut cmd = detached(&["xclip", "-selection", "clipboard", "-t", mime]);
        cmd.env("DISPLAY", &display);
        return feed(cmd, data);
    }
    if which("xsel").is_some() && mime.starts_with("text/") {
        let mut cmd = detached(&["xsel", "--clipboard", "--input"]);
        cmd.env("DISPLAY", &display);
        return feed(cmd, data);
    }
    false
}

pub fn copy_text(text: &str) -> bool {
    copy(text.as_bytes(), "text/plain;charset=utf-8")
}

/// Bild kopieren (PNG; JPG wird umgewandelt – Discord & Co. wollen image/png)
pub fn copy_image(photo: &Path) -> bool {
    let is_png = photo.extension().is_some_and(|e| e.eq_ignore_ascii_case("png"));
    let data = if is_png {
        std::fs::read(photo).ok()
    } else {
        image::open(photo).ok().and_then(|img| {
            let mut out = std::io::Cursor::new(Vec::new());
            img.write_to(&mut out, image::ImageFormat::Png).ok().map(|_| out.into_inner())
        })
    };
    data.is_some_and(|d| copy(&d, "image/png"))
}

// ─────────────────────────── ↗ Teilen ───────────────────────────

/// (Schlüssel, Name, Befehle, Flatpak-IDs, Art) – wie TARGETS in core/share.py
type Target = (&'static str, &'static str, &'static [&'static str], &'static [&'static str], &'static str);
const TARGETS: [Target; 3] = [
    (
        "discord",
        "Discord",
        &["discord", "vesktop", "discord-canary", "webcord"],
        &["com.discordapp.Discord", "dev.vencord.Vesktop", "com.discordapp.DiscordCanary", "io.github.spacingbat3.webcord"],
        "paste",
    ),
    ("telegram", "Telegram", &["telegram-desktop", "Telegram"], &["org.telegram.desktop"], "sendpath"),
    ("email", "E-Mail", &["xdg-email"], &[], "email"),
];

fn find(cmds: &[&str], flatpaks: &[&str]) -> Option<Vec<String>> {
    if let Some(c) = cmds.iter().find(|c| which(c).is_some()) {
        return Some(vec![c.to_string()]);
    }
    flatpaks.iter().find(|id| flatpak_installed(id)).map(|id| vec!["flatpak".into(), "run".into(), id.to_string()])
}

/// Installierte Ziele: [(Schlüssel, Name)]
pub fn share_targets() -> Vec<(String, String)> {
    TARGETS.iter().filter(|t| find(t.2, t.3).is_some()).map(|t| (t.0.to_string(), t.1.to_string())).collect()
}

/// Programm starten. Ok("paste") = Bild liegt in der Zwischenablage, dort Strg+V drücken.
pub fn share(key: &str, photo: &Path) -> Result<&'static str, String> {
    let Some(t) = TARGETS.iter().find(|t| t.0 == key) else { return Err(key.to_string()) };
    let Some(cmd) = find(t.2, t.3) else { return Err(format!("{} fehlt", t.1)) };
    let mut argv: Vec<String> = cmd;
    let p = photo.to_string_lossy().to_string();
    match t.4 {
        "sendpath" => argv.extend(["-sendpath".to_string(), p]),
        "email" => argv.extend(["--attach".to_string(), p]),
        _ => {
            if !copy_image(photo) {
                return Err("Zwischenablage".into());
            }
        }
    }
    let refs: Vec<&str> = argv.iter().map(String::as_str).collect();
    detached(&refs).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().map_err(|e| e.to_string())?;
    Ok(if t.4 == "paste" { "paste" } else { "opened" })
}

// ─────────────────────────── ☁ Hochladen ───────────────────────────

const BASE: &str = "https://www.directupload.eu";
const USER_AGENT: &str = "Mozilla/5.0 (X11; Linux x86_64) LinuxVR-ViewShot";
const MAX_BYTES: usize = 8 * 1024 * 1024;

fn uploads_file() -> PathBuf {
    crate::paths::config_dir().join("uploads.json")
}

/// {"view": …, "delete": …}, falls das Foto schon hochgeladen wurde (Schlüssel = Dateiname)
pub fn saved_links(photo: &Path) -> Option<(String, String)> {
    let name = photo.file_name()?.to_string_lossy().to_string();
    let v: Value = serde_json::from_str(&std::fs::read_to_string(uploads_file()).ok()?).ok()?;
    let e = &v[name.as_str()];
    Some((e["view"].as_str()?.to_string(), e["delete"].as_str()?.to_string()))
}

fn remember(photo: &Path, view: &str, delete: &str) {
    let file = uploads_file();
    let mut v: Value = std::fs::read_to_string(&file).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_else(|| serde_json::json!({}));
    if let (Some(map), Some(name)) = (v.as_object_mut(), photo.file_name()) {
        map.insert(name.to_string_lossy().to_string(), serde_json::json!({"view": view, "delete": delete}));
        let _ = crate::settings::write_json(&file, &v, 2);
    }
}

/// Cookies wie ein Browser merken (PHP-Session der Seite)
fn keep_cookies(jar: &mut Vec<(String, String)>, resp: &ureq::Response) {
    for c in resp.all("set-cookie") {
        if let Some((k, v)) = c.split(';').next().and_then(|kv| kv.split_once('=')) {
            let k = k.trim().to_string();
            jar.retain(|(name, _)| *name != k);
            jar.push((k, v.trim().to_string()));
        }
    }
}

fn cookie_header(jar: &[(String, String)]) -> String {
    jar.iter().map(|(k, v)| format!("{k}={v}")).collect::<Vec<_>>().join("; ")
}

fn form_encode(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => (b as char).to_string(),
            b' ' => "+".to_string(),
            _ => format!("%{b:02X}"),
        })
        .collect()
}

/// Bild- und Lösch-Link aus der Ergebnis-Seite (wie uploader.parse_links)
pub fn parse_links(html: &str) -> Option<(String, String)> {
    let view = regex::Regex::new(r"https?://(?:www\.)?directupload\.eu/file/d/\d+/[A-Za-z0-9_]+\.htm").ok()?;
    let delete = regex::Regex::new(r"https?://(?:www\.)?directupload\.eu/delfile/[A-Za-z0-9=_%+-]+/?").ok()?;
    Some((view.find(html)?.as_str().to_string(), delete.find(html)?.as_str().to_string()))
}

/// Lädt hoch (blockiert – im eigenen Thread aufrufen) und merkt die Links in uploads.json
pub fn upload(photo: &Path) -> Result<(String, String), String> {
    use base64::Engine;
    let mut data = std::fs::read(photo).map_err(|e| e.to_string())?;
    let mut mime = if photo.extension().is_some_and(|e| e.eq_ignore_ascii_case("png")) { "image/png" } else { "image/jpeg" };
    if data.len() > MAX_BYTES {
        // über 8 MB → als JPG verkleinern (Limit der Seite)
        let img = image::open(photo).map_err(|e| e.to_string())?.to_rgb8();
        let mut out = std::io::Cursor::new(Vec::new());
        image::codecs::jpeg::JpegEncoder::new_with_quality(&mut out, 92).encode_image(&img).map_err(|e| e.to_string())?;
        data = out.into_inner();
        mime = "image/jpeg";
        if data.len() > MAX_BYTES {
            return Err("Bild größer als 8 MB".into());
        }
    }
    let name = photo.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let agent = ureq::AgentBuilder::new().timeout(std::time::Duration::from_secs(60)).build();
    let mut jar = Vec::new();
    let start = agent.get(&format!("{BASE}/")).set("User-Agent", USER_AGENT).call().map_err(|e| e.to_string())?;
    keep_cookies(&mut jar, &start);

    // Schritt 1: Bild senden → ID
    let boundary = format!("viewshot{:x}", std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0));
    let data_url = format!("data:{mime};base64,{}", base64::engine::general_purpose::STANDARD.encode(&data));
    let mut body = String::new();
    for (k, v) in [("file", data_url.as_str()), ("filename", name.as_str()), ("showtext", "0")] {
        body.push_str(&format!("--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"));
    }
    body.push_str(&format!("--{boundary}--\r\n"));
    let resp = agent
        .post(&format!("{BASE}/api/upload_http_resize.php"))
        .set("User-Agent", USER_AGENT)
        .set("Referer", &format!("{BASE}/"))
        .set("Cookie", &cookie_header(&jar))
        .set("Content-Type", &format!("multipart/form-data; boundary={boundary}"))
        .send_string(&body)
        .map_err(|e| e.to_string())?;
    keep_cookies(&mut jar, &resp);
    let id = resp.into_string().map_err(|e| e.to_string())?.trim().to_string();
    if id.is_empty() || id.len() > 200 || id.contains('<') {
        return Err("Keine Bild-ID erhalten".into());
    }

    // Schritt 2: Formular abschicken → Ergebnis-Seite mit Links
    let form = format!("img_id%5B%5D={}&file_name%5B%5D={}&img_resize=0&autodel=0", form_encode(&id), form_encode(&name));
    let html = agent
        .post(&format!("{BASE}/upload_a2/"))
        .set("User-Agent", USER_AGENT)
        .set("Referer", &format!("{BASE}/"))
        .set("Cookie", &cookie_header(&jar))
        .set("Content-Type", "application/x-www-form-urlencoded")
        .send_string(&form)
        .map_err(|e| e.to_string())?
        .into_string()
        .map_err(|e| e.to_string())?;
    let (view, delete) = parse_links(&html).ok_or("Links nicht gefunden")?;
    remember(photo, &view, &delete);
    Ok((view, delete))
}

// ─────────────────────────── ⓘ Info ───────────────────────────

/// Typ-Tags aus tags.json („text“, „qr“, „image“) – wie core/tags.get
pub fn photo_tags(photo: &Path) -> Vec<String> {
    let Some(name) = photo.file_name().map(|n| n.to_string_lossy().to_string()) else { return Vec::new() };
    std::fs::read_to_string(crate::paths::config_dir().join("tags.json"))
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v[name.as_str()]["tags"].as_array().cloned())
        .map(|a| a.iter().filter_map(|t| t.as_str().map(String::from)).collect())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn links_and_form_like_python() {
        let html = r#"<a href="https://www.directupload.eu/file/d/9420/9ke32u3k_png.htm">x</a>
                      <input value="https://www.directupload.eu/delfile/QUEzZ3dT%2Bab=/">"#;
        let (view, delete) = parse_links(html).unwrap();
        assert_eq!(view, "https://www.directupload.eu/file/d/9420/9ke32u3k_png.htm");
        assert_eq!(delete, "https://www.directupload.eu/delfile/QUEzZ3dT%2Bab=/");
        assert!(parse_links("nichts").is_none());
        assert_eq!(form_encode("a b/ä"), "a+b%2F%C3%A4");
        let mut jar = vec![("PHPSESSID".to_string(), "1".to_string())];
        jar.retain(|(k, _)| k != "PHPSESSID");
        jar.push(("PHPSESSID".into(), "2".into()));
        assert_eq!(cookie_header(&jar), "PHPSESSID=2");
    }

    #[test]
    fn share_targets_include_vesktop_flatpak() {
        let discord = TARGETS.iter().find(|t| t.0 == "discord").unwrap();
        assert!(discord.2.contains(&"vesktop") && discord.3.contains(&"dev.vencord.Vesktop"));
    }
}
