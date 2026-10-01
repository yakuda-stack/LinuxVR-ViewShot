//! Einstellungen der App (ui.json) und des Layers (layer.json) – lesen und
//! einzelne Werte ändern (z. B. Klick im VR-Panel), genau wie die App:
//! frisch laden, Wert setzen, über eine Hilfsdatei ersetzen. Unbekannte Werte bleiben.

use serde_json::{Map, Value};
use std::path::{Path, PathBuf};

/// Standardwerte – müssen zu UI/core/config.py + translation.py + llm_translator.py passen
/// (geprüft über tests/fixtures/daemon_contract.json).
pub const UI_DEFAULTS: &str = r#"{
  "language": "de",
  "gallery_main_subfolders": false,
  "gallery_folders": [],
  "history": false,
  "tr_method": "lingva",
  "tr_source": "",
  "tr_target": "de",
  "tr_auto": true,
  "tr_google_key": "",
  "tr_deepl_key": "",
  "tr_libre_url": "http://127.0.0.1:5000",
  "tr_libre_online_url": "",
  "tr_libre_online_key": "",
  "tr_libre_seen": false,
  "tr_llm_claude_model": "sonnet",
  "tr_llm_gemini_model": "flash",
  "tr_llm_chatgpt_model": "gpt-5.6-luna",
  "tr_llm_custom_cmd": "",
  "tr_llm_vision_model": "qwen2.5vl:7b",
  "tr_vision_url": "",
  "tr_vision_keep_alive": "2m",
  "tr_explain_method": "",
  "tr_answer_method": "",
  "tr_route": "auto",
  "tr_auto_once": "",
  "tr_auto_once_photo": "",
  "tr_auto_once_next": "",
  "tr_llm_mode": "translate",
  "tr_llm_gemini_retry": false,
  "tr_llm_gemini_retry_s": 60,
  "tr_llm_claude_retry": false,
  "tr_llm_claude_retry_s": 60,
  "tr_llm_chatgpt_retry": false,
  "tr_llm_chatgpt_retry_s": 60
}"#;

/// layer.json – nur, was der Dienst braucht (Rest: layer/src/config.rs)
pub const LAYER_DEFAULTS: &str = r##"{
  "live_interval_s": 3,
  "overlay": false,
  "panel": true,
  "panel_edit": false,
  "panel_port": 47931,
  "panel_opacity": 100,
  "panel_anchor": "left",
  "detect_mode": "auto",
  "shutter": "right",
  "mode_button": "left",
  "panel_button": true,
  "panel_button_color": "#5b8dc9",
  "panel_open_on_shot": true
}"##;

#[derive(Clone, Debug, Default)]
pub struct Cfg(pub Map<String, Value>);

impl Cfg {
    pub fn with_defaults(defaults: &str, file: Option<&Path>) -> Cfg {
        let mut map: Map<String, Value> = serde_json::from_str(defaults).unwrap_or_default();
        if let Some(file) = file {
            if let Ok(text) = std::fs::read_to_string(file) {
                if let Ok(Value::Object(user)) = serde_json::from_str::<Value>(&text) {
                    for (k, v) in user {
                        map.insert(k, v);
                    }
                }
            }
        }
        Cfg(map)
    }

    pub fn s(&self, key: &str) -> String {
        match self.0.get(key) {
            Some(Value::String(s)) => s.clone(),
            Some(Value::Null) | None => String::new(),
            Some(v) => v.to_string(),
        }
    }

    /// Python-Wahrheit: "", 0, false, null, [] → falsch
    pub fn b(&self, key: &str) -> bool {
        truthy(self.0.get(key))
    }

    pub fn f(&self, key: &str, default: f64) -> f64 {
        match self.0.get(key) {
            Some(Value::Number(n)) => n.as_f64().unwrap_or(default),
            Some(Value::String(s)) => s.trim().parse().unwrap_or(default),
            Some(Value::Bool(b)) => f64::from(u8::from(*b)),
            _ => default,
        }
    }

    pub fn set(&mut self, key: &str, value: impl Into<Value>) {
        self.0.insert(key.to_string(), value.into());
    }

    /// Kopie mit geänderten Werten (wie dict(cfg, k=v) in Python)
    pub fn with(&self, pairs: &[(&str, &str)]) -> Cfg {
        let mut c = self.clone();
        for (k, v) in pairs {
            c.set(k, *v);
        }
        c
    }
}

pub fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

pub fn ui_file() -> PathBuf {
    crate::paths::config_dir().join("ui.json")
}

pub fn layer_file() -> PathBuf {
    crate::paths::config_dir().join("layer.json")
}

pub fn load_ui() -> Cfg {
    Cfg::with_defaults(UI_DEFAULTS, Some(&ui_file()))
}

pub fn load_layer() -> Cfg {
    Cfg::with_defaults(LAYER_DEFAULTS, Some(&layer_file()))
}

/// Werte in einer JSON-Datei ändern: frisch lesen, setzen, atomar ersetzen.
/// Nur diese Schlüssel werden angefasst – alles andere bleibt, wie es ist.
pub fn update_file(file: &Path, changes: &[(&str, Value)]) -> std::io::Result<()> {
    // ui.json und layer.json schreibt die App mit indent=2
    let mut map: Map<String, Value> = std::fs::read_to_string(file)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default();
    for (k, v) in changes {
        map.insert((*k).to_string(), v.clone());
    }
    write_json(file, &Value::Object(map), 2)
}

/// Wie json.dumps(indent=…, ensure_ascii=False) + Hilfsdatei → umbenennen
pub fn write_json(file: &Path, value: &Value, indent: usize) -> std::io::Result<()> {
    if let Some(dir) = file.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let ind = vec![b' '; indent];
    let fmt = serde_json::ser::PrettyFormatter::with_indent(&ind);
    let mut out = Vec::new();
    let mut ser = serde_json::Serializer::with_formatter(&mut out, fmt);
    serde::Serialize::serialize(value, &mut ser).map_err(std::io::Error::other)?;
    let tmp = file.with_extension("json.daemon-tmp");
    std::fs::write(&tmp, out)?;
    std::fs::rename(&tmp, file)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn user_values_override_defaults() {
        let dir = std::env::temp_dir().join(format!("vs-settings-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let f = dir.join("ui.json");
        std::fs::write(&f, r#"{"tr_method": "libre", "extra": [1]}"#).unwrap();
        let c = Cfg::with_defaults(UI_DEFAULTS, Some(&f));
        assert_eq!(c.s("tr_method"), "libre");
        assert_eq!(c.s("tr_target"), "de");
        update_file(&f, &[("tr_target", Value::from("en"))]).unwrap();
        let text = std::fs::read_to_string(&f).unwrap();
        assert!(text.contains("\"extra\"") && text.contains("\"en\""));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn python_truthiness() {
        assert!(!truthy(Some(&Value::from(""))));
        assert!(!truthy(Some(&Value::from(0))));
        assert!(truthy(Some(&Value::from("x"))));
    }
}
