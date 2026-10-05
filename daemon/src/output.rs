//! 📤 Übersetzung weitergeben – genau wie UI/core/output.py, wenn die App zu ist:
//!   📡 OSC   UDP an out_osc_host:out_osc_port, Adresse /viewshot/translation,
//!            Strings: Übersetzung, Originaltext, Quelle ("photo" / "lens")
//!   📄 Datei out_file_path (leer = ~/.local/state/linuxvr-viewshot/translation.json),
//!            gleiche Infos wie OSC als JSON, immer nur die letzte Übersetzung:
//!            {"id": ms seit 1970, "time": "…", "translation", "original", "source"}

use crate::settings::Cfg;
use std::net::UdpSocket;
use std::path::PathBuf;

pub const OSC_ADDRESS: &str = "/viewshot/translation";
const MAX_ARG_BYTES: usize = 16000;

/// OSC-String: UTF-8 + 0-Bytes bis zum nächsten Vielfachen von 4 (mindestens eins)
fn osc_string(out: &mut Vec<u8>, text: &str) {
    let mut end = text.len().min(MAX_ARG_BYTES);
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    out.extend_from_slice(&text.as_bytes()[..end]);
    out.extend(std::iter::repeat_n(0u8, 4 - end % 4));
}

pub fn osc_message(address: &str, args: &[&str]) -> Vec<u8> {
    let mut out = Vec::new();
    osc_string(&mut out, address);
    osc_string(&mut out, &format!(",{}", "s".repeat(args.len())));
    for a in args {
        osc_string(&mut out, a);
    }
    out
}

pub fn file_path(cfg: &Cfg) -> PathBuf {
    let custom = cfg.s("out_file_path");
    let custom = custom.trim();
    if custom.is_empty() {
        crate::paths::state_dir().join("translation.json")
    } else if let Some(rest) = custom.strip_prefix("~/") {
        dirs::home_dir().unwrap_or_default().join(rest)
    } else {
        PathBuf::from(custom)
    }
}

/// Inhalt der Datei – wie file_entry() in UI/core/output.py
fn file_entry(translated: &str, original: &str, source: &str) -> serde_json::Value {
    let id = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or_default();
    serde_json::json!({
        "id": id,
        "time": chrono::Local::now().format("%Y-%m-%dT%H:%M:%S").to_string(),
        "translation": translated,
        "original": original,
        "source": source,
    })
}

fn write_file(path: &std::path::Path, translated: &str, original: &str, source: &str) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let tmp = path.with_file_name(format!(".{name}.tmp"));
    let mut text = serde_json::to_string_pretty(&file_entry(translated, original, source)).map_err(std::io::Error::other)?;
    text.push('\n');
    std::fs::write(&tmp, text)?;
    std::fs::rename(&tmp, path)
}

/// Neue Übersetzung ausgeben (was in ui.json eingeschaltet ist).
pub fn publish(cfg: &Cfg, translated: &str, original: &str, source: &str) {
    let translated = translated.trim();
    if translated.is_empty() {
        return;
    }
    if cfg.b("out_osc") {
        let host = cfg.s("out_osc_host");
        let host = if host.trim().is_empty() { "127.0.0.1".to_string() } else { host.trim().to_string() };
        let port = cfg.f("out_osc_port", 9025.0) as u16;
        let msg = osc_message(OSC_ADDRESS, &[translated, original, source]);
        let sent = UdpSocket::bind(("0.0.0.0", 0)).and_then(|s| s.send_to(&msg, (host.as_str(), port)));
        if let Err(e) = sent {
            crate::log::line(&format!("OSC an {host}:{port} fehlgeschlagen: {e}"));
        }
    }
    if cfg.b("out_file") {
        let path = file_path(cfg);
        if let Err(e) = write_file(&path, translated, original, source) {
            crate::log::line(&format!("{} schreiben fehlgeschlagen: {e}", path.display()));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn osc_strings_are_padded() {
        let m = osc_message("/viewshot/translation", &["Hallo", ""]);
        // Adresse 21 Bytes → 24, ",ss" → 4, "Hallo" → 8, "" → 4
        assert_eq!(m.len(), 24 + 4 + 8 + 4);
        assert_eq!(&m[24..28], b",ss\0");
        assert_eq!(&m[28..36], b"Hallo\0\0\0");
        assert_eq!(m.len() % 4, 0);
    }

    #[test]
    fn same_bytes_as_python() {
        // gleiche Nachricht wie tests/test_core.py::test_osc_message
        let m = osc_message("/a", &["äb"]);
        assert_eq!(m, b"/a\0\0,s\0\0\xc3\xa4b\0".to_vec());
    }

    #[test]
    fn udp_and_file() {
        let rx = UdpSocket::bind("127.0.0.1:0").unwrap();
        let port = rx.local_addr().unwrap().port();
        let dir = std::env::temp_dir().join(format!("vs-out-{}", std::process::id()));
        let file = dir.join("t.json");
        let mut cfg = Cfg::with_defaults(crate::settings::UI_DEFAULTS, None).with(&[
            ("out_osc", "x"),
            ("out_file", "x"),
            ("out_file_path", file.to_str().unwrap()),
        ]);
        cfg.set("out_osc_port", port);
        publish(&cfg, " Hallo Welt ", "Hello world", "photo");
        let mut buf = [0u8; 256];
        let n = rx.recv(&mut buf).unwrap();
        assert!(buf[..n].starts_with(b"/viewshot/translation\0\0\0,sss\0"));
        let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&file).unwrap()).unwrap();
        assert_eq!((v["translation"].as_str(), v["original"].as_str(), v["source"].as_str()),
                   (Some("Hallo Welt"), Some("Hello world"), Some("photo")));
        assert!(v["id"].as_u64().unwrap() > 1_700_000_000_000);
        std::fs::remove_dir_all(&dir).ok();
    }
}
