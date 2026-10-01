//! Texte fürs VR-Panel – kommen aus der App (daemon/contract.json, erzeugt von
//! scripts/make_daemon_contract.py) und werden beim Kompilieren eingebaut.

use serde_json::Value;
use std::sync::OnceLock;

pub const CONTRACT: &str = include_str!("../contract.json");

fn contract() -> &'static Value {
    static C: OnceLock<Value> = OnceLock::new();
    C.get_or_init(|| serde_json::from_str(CONTRACT).unwrap_or_default())
}

/// Text in der Sprache der App ("de"/"en"); {name} usw. werden ersetzt.
pub fn tr(lang: &str, key: &str, args: &[(&str, &str)]) -> String {
    let entry = &contract()["i18n"][key];
    let mut s = entry[lang]
        .as_str()
        .or_else(|| entry["en"].as_str())
        .map(String::from)
        .unwrap_or_else(|| key.to_string());
    for (k, v) in args {
        s = s.replace(&format!("{{{k}}}"), v);
    }
    s
}

/// (Code, Deutsch, Englisch) – erster Eintrag = „Automatisch erkennen“ (Code "")
pub fn languages() -> Vec<(String, String, String)> {
    contract()["languages"]
        .as_array()
        .map(|a| {
            a.iter()
                .map(|l| {
                    let s = |i: usize| l[i].as_str().unwrap_or("").to_string();
                    (s(0), s(1), s(2))
                })
                .collect()
        })
        .unwrap_or_default()
}

pub fn language_name(lang: &str, code: &str, source: bool) -> String {
    for (i, (c, de, en)) in languages().into_iter().enumerate() {
        if i == 0 && !source {
            continue;
        }
        if c == code {
            return if lang == "de" { de } else { en };
        }
    }
    if code.is_empty() { "auto".into() } else { code.into() }
}

#[cfg(test)]
pub fn contract_value() -> &'static Value {
    contract()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{Cfg, LAYER_DEFAULTS, UI_DEFAULTS};
    use crate::tr::{self, llm, vision};

    #[test]
    fn texts_and_languages() {
        assert_eq!(tr("de", "back", &[]), "Zurück");
        assert_eq!(tr("en", "tr_step_service", &[("name", "X")]), "Translating with X …");
        assert_eq!(language_name("de", "", true), "Automatisch erkennen");
        assert_eq!(language_name("en", "ja", false), "Japanese");
    }

    #[test]
    fn defaults_match_app() {
        let c = contract_value();
        let ui: Value = serde_json::from_str(UI_DEFAULTS).unwrap();
        assert_eq!(ui, c["defaults"]["ui"], "settings::UI_DEFAULTS ≠ App");
        let layer: Value = serde_json::from_str(LAYER_DEFAULTS).unwrap();
        assert_eq!(layer, c["defaults"]["layer"], "settings::LAYER_DEFAULTS ≠ App");
    }

    #[test]
    fn cache_keys_match_app() {
        for case in contract_value()["keys"].as_array().unwrap() {
            let mut cfg = Cfg::with_defaults(UI_DEFAULTS, None);
            for (k, v) in case["cfg"].as_object().unwrap() {
                cfg.0.insert(k.clone(), v.clone());
            }
            assert_eq!(tr::key(&cfg), case["key"].as_str().unwrap(), "Fall {}", case["cfg"]);
        }
    }

    #[test]
    fn prompts_match_app() {
        for p in contract_value()["prompts"].as_array().unwrap() {
            let s = |k: &str| p[k].as_str().unwrap_or("").to_string();
            let image = p["image"].as_bool().unwrap_or(false);
            let got = match s("kind").as_str() {
                "llm" => llm::make_prompt(&s("text"), &s("source"), &s("target"), &s("mode"), &s("method")),
                "vision" => vision::build_prompt(&s("text"), &s("target"), &s("mode"), image),
                "classify" => vision::classify_prompt(&s("text"), image),
                "task" => vision::task_prompt(&s("text"), image),
                _ => vision::system_prompt(&s("target")),
            };
            assert_eq!(got, s("prompt"), "Prompt {p}");
        }
    }
}
