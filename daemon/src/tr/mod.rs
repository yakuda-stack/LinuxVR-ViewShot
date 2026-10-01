//! Foto → Text → Übersetzung, genau wie UI/core/translation.py:
//! gleiche Dienste, gleiche Weiche (🤖 Auto / ✋ Manuell, Dienst je Aufgabe),
//! gleicher Cache (translations.json) mit gleichem Schlüssel – die App zeigt
//! also später an, was der Dienst übersetzt hat, ohne neu zu fragen.

pub mod llm;
pub mod services;
pub mod vision;

use crate::ocr::Line;
use crate::settings::{write_json, Cfg};
use llm::{is_llm, MODES, MODE_ANSWER, MODE_AUTO, MODE_CLASSIFY, MODE_TRANSLATE, TASK_KEYS};
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

pub const ROUTE_AUTO: &str = "auto";
pub const ROUTE_MANUAL: &str = "manual";

/// Reihenfolge wie im Dropdown der App
pub const METHODS: [&str; 11] = [
    services::LINGVA,
    services::GOOGLE,
    services::LIBRE,
    services::LIBRE_ONLINE,
    services::DEEPL,
    services::CUSTOM,
    llm::CLAUDE,
    llm::GEMINI,
    llm::CHATGPT,
    llm::LLM_CUSTOM,
    llm::VISION,
];

/// Ist der Dienst eingerichtet?
pub fn is_configured(method: &str, cfg: &Cfg) -> bool {
    match method {
        services::LINGVA | services::GOOGLE => true,
        services::LIBRE => {
            cfg.b("tr_libre_seen")
                || llm::find_binary("libretranslate").is_some()
                || {
                    let u = cfg.s("tr_libre_url");
                    !u.is_empty() && u != services::DEFAULT_LIBRE_URL
                }
        }
        services::LIBRE_ONLINE => cfg.b("tr_libre_online_key") || cfg.b("tr_libre_online_url"),
        services::DEEPL => cfg.b("tr_deepl_key"),
        // eigener Übersetzer = Python-Schnipsel → geht nur mit offener App
        llm::LLM_CUSTOM => !cfg.s("tr_llm_custom_cmd").trim().is_empty(),
        llm::VISION => llm::installed(method) || !cfg.s("tr_vision_url").trim().is_empty(),
        m if is_llm(m) => llm::installed(m),
        _ => false,
    }
}

fn mode_or_translate(cfg: &Cfg) -> String {
    let m = cfg.s("tr_llm_mode");
    if m.is_empty() { MODE_TRANSLATE.to_string() } else { m }
}

/// Welcher Dienst macht diese Aufgabe? "" = kann keiner (nur übersetzen)
pub fn task_method(cfg: &Cfg, mode: &str) -> String {
    let main = cfg.s("tr_method");
    let Some((_, key)) = TASK_KEYS.iter().find(|(m, _)| *m == mode) else { return main };
    let m = cfg.s(key);
    let method = if m.is_empty() { main } else { m };
    if is_llm(&method) { method } else { String::new() }
}

pub fn has_tasks(cfg: &Cfg) -> bool {
    TASK_KEYS.iter().any(|(m, _)| !task_method(cfg, m).is_empty())
}

pub fn route_mode(cfg: &Cfg) -> &'static str {
    let r = cfg.0.get("tr_route").and_then(Value::as_str).unwrap_or(ROUTE_AUTO);
    if r == ROUTE_AUTO && is_llm(&cfg.s("tr_method")) { ROUTE_AUTO } else { ROUTE_MANUAL }
}

/// Aufgabe, die JETZT gilt (Manuell: die gewählte; Auto: "auto" oder die 1× gewählte)
pub fn task_cfg(cfg: &Cfg) -> Cfg {
    let mut c = cfg.clone();
    if route_mode(cfg) == ROUTE_MANUAL {
        let m = cfg.s("tr_llm_mode");
        c.set("tr_llm_mode", if MODES.contains(&m.as_str()) { m } else { MODE_TRANSLATE.to_string() });
    } else {
        let once = cfg.s("tr_auto_once");
        c.set("tr_llm_mode", if MODES.contains(&once.as_str()) { once } else { MODE_AUTO.to_string() });
    }
    c
}

/// Wie task_cfg für ein bestimmtes Foto (1× gewählt: dieses + nächstes Foto, dann Auto).
/// Ändert cfg; true = in ui.json speichern.
pub fn photo_task_cfg(cfg: &mut Cfg, photo_name: &str) -> (Cfg, bool) {
    let mut changed = false;
    if route_mode(cfg) == ROUTE_AUTO && cfg.b("tr_auto_once") && !photo_name.is_empty() {
        let (a, b) = (cfg.s("tr_auto_once_photo"), cfg.s("tr_auto_once_next"));
        if photo_name != a && photo_name != b {
            if b.is_empty() {
                cfg.set("tr_auto_once_next", photo_name);
            } else {
                cfg.set("tr_auto_once", "");
                cfg.set("tr_auto_once_photo", "");
                cfg.set("tr_auto_once_next", "");
            }
            changed = true;
        }
    }
    (task_cfg(cfg), changed)
}

pub fn looks_like_quiz(text: &str) -> bool {
    let lines = crate::ocr::splitlines(text).into_iter().filter(|t| !t.trim().is_empty()).count();
    lines >= 3 && ["?", "？", "○", "〇", "＿", "___", "□"].iter().any(|m| text.contains(m))
}

pub trait Progress {
    fn step(&self, step: &str, arg: &str);
}

impl<F: Fn(&str, &str)> Progress for F {
    fn step(&self, step: &str, arg: &str) {
        self(step, arg)
    }
}

pub fn classify(cfg: &Cfg, text: &str, image: Option<&Path>, log: &mut Vec<String>, progress: &dyn Progress) -> String {
    let main = cfg.s("tr_method");
    if is_llm(&main) && is_configured(&main, cfg) && (!text.trim().is_empty() || main == llm::VISION) {
        progress.step("classify", &main);
        let r = if main == llm::VISION {
            vision::classify(cfg, text, image).map(String::from)
        } else {
            llm::translate(&main, &cfg.with(&[("tr_llm_mode", MODE_CLASSIFY)]), text, &cfg.s("tr_source"), &cfg.s("tr_target"), None)
                .map(|v| vision::parse_task(&v).to_string())
        };
        match r {
            Ok(m) => return m,
            Err(e) => log.push(e),
        }
    }
    if looks_like_quiz(text) { MODE_ANSWER.into() } else { MODE_TRANSLATE.into() }
}

/// Aufgabe + Dienst für diesen Text → cfg dafür
pub fn route(cfg: &Cfg, text: &str, image: Option<&Path>, log: &mut Vec<String>, progress: &dyn Progress) -> Cfg {
    let mut mode = mode_or_translate(cfg);
    let auto = mode == MODE_AUTO;
    if auto {
        mode = if has_tasks(cfg) { classify(cfg, text, image, log, progress) } else { MODE_TRANSLATE.into() };
        progress.step("auto", &mode);
    }
    let mut method = task_method(cfg, &mode);
    if mode != MODE_TRANSLATE
        && (method.is_empty() || !is_configured(&method, cfg) || (text.trim().is_empty() && method != llm::VISION))
    {
        method = cfg.s("tr_method");
        mode = MODE_TRANSLATE.into();
    }
    let mut out = cfg.clone();
    out.set("tr_method", if method.is_empty() { cfg.s("tr_method") } else { method });
    out.set("tr_llm_mode", mode);
    out.set("_routed", auto);
    out
}

fn chain(method: &str) -> Vec<String> {
    let mut c = vec![method.to_string()];
    for f in [services::LINGVA, services::GOOGLE] {
        if !c.iter().any(|m| m == f) {
            c.push(f.to_string());
        }
    }
    c
}

fn try_one(method: &str, text: &str, cfg: &Cfg, image: Option<&Path>) -> (Option<String>, String) {
    let (src, tgt) = (cfg.s("tr_source"), cfg.s("tr_target"));
    if is_llm(method) {
        return match llm::translate(method, cfg, text, &src, &tgt, image) {
            Ok(v) if !v.is_empty() => (Some(v), String::new()),
            Ok(_) => (None, String::new()),
            Err(e) => (None, e),
        };
    }
    services::translate(method, cfg, text, &src, &tgt)
}

pub struct Done {
    pub text: String,
    pub method: String,
    pub task: String,
}

/// Übersetzen mit Weiche + Ersatz-Kette (Lingva, Google). Fehlertexte landen in `log`.
pub fn translate_text_used(text: &str, cfg: &Cfg, log: &mut Vec<String>, progress: &dyn Progress, image: Option<&Path>) -> Option<Done> {
    let main = cfg.s("tr_method");
    let mut cfg = route(cfg, text, image, log, progress);
    let routed = cfg.s("tr_method");
    let mut ch = chain(&routed);
    if !ch.contains(&main) {
        ch.insert(1, main.clone());
    }
    for method in ch {
        if method != routed {
            cfg.set("tr_llm_mode", MODE_TRANSLATE);
        }
        if text.trim().is_empty() && method != llm::VISION {
            continue;
        }
        progress.step("service", &method);
        let start = std::time::Instant::now();
        let (out, error) = try_one(&method, text, &cfg, image);
        crate::log::line(&format!(
            "{} {method}: {:.1} s, {}",
            mode_or_translate(&cfg),
            start.elapsed().as_secs_f32(),
            if out.is_some() { "ok".to_string() } else { format!("Fehler: {error}") }
        ));
        if let Some(out) = out {
            return Some(Done { text: out, method, task: mode_or_translate(&cfg) });
        }
        log.push(if error.is_empty() { format!("{method}: keine Antwort") } else { error });
    }
    None
}

// ───────────────────────── Cache (translations.json) ─────────────────────────

fn svc(method: &str, cfg: &Cfg) -> String {
    let model = llm::model_of(method, cfg);
    if model.is_empty() { method.to_string() } else { format!("{method}@{model}") }
}

/// Cache-Schlüssel – exakt wie translation._key in der App
pub fn key(cfg: &Cfg) -> String {
    let main = cfg.s("tr_method");
    let mut method = svc(&main, cfg);
    let mode = mode_or_translate(cfg);
    if mode == MODE_AUTO && has_tasks(cfg) {
        method.push_str("#auto");
        for (m, _) in TASK_KEYS {
            let t = task_method(cfg, m);
            if !t.is_empty() {
                method.push_str(&format!("|{m}={}{}", svc(&t, cfg), llm::prompt_version(&t, m)));
            }
        }
    } else if TASK_KEYS.iter().any(|(m, _)| *m == mode) && !task_method(cfg, &mode).is_empty() {
        let s = task_method(cfg, &mode);
        method.push_str(&format!("#{mode}{}", llm::prompt_version(&s, &mode)));
        if s != main {
            method.push_str(&format!("={}", svc(&s, cfg)));
        }
    }
    let src = cfg.s("tr_source");
    format!("{method}|{}|{}", if src.is_empty() { "auto" } else { &src }, cfg.s("tr_target"))
}

static CACHE_LOCK: Mutex<()> = Mutex::new(());

pub fn cache_file() -> PathBuf {
    crate::paths::config_dir().join("translations.json")
}

/// Cache lesen. Err = Datei da, aber (gerade) nicht lesbar → dann NIE überschreiben,
/// sonst wären alle gespeicherten Übersetzungen weg.
fn try_load_cache() -> Result<Map<String, Value>, ()> {
    match std::fs::read_to_string(cache_file()) {
        Ok(t) => serde_json::from_str(&t).map_err(|_| ()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Map::new()),
        Err(_) => Err(()),
    }
}

fn load_cache() -> Map<String, Value> {
    try_load_cache().unwrap_or_default()
}

/// Darf der Dienst gerade schreiben? (App offen → sie schreibt selbst, nicht dazwischenfunken)
#[allow(non_snake_case)]
fn WRITE_ALLOWED() -> bool {
    !crate::app::app_running()
}

/// Eintrag eines Fotos ändern (frisch laden → ändern → speichern)
pub fn update_entry(photo: &str, f: impl FnOnce(&mut Map<String, Value>)) {
    let _g = CACHE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    if !WRITE_ALLOWED() {
        return;
    }
    let Ok(mut cache) = try_load_cache() else {
        crate::log::line("translations.json gerade nicht lesbar – nichts gespeichert");
        return;
    };
    let entry = cache.entry(photo.to_string()).or_insert_with(|| json!({}));
    if !entry.is_object() {
        *entry = json!({});
    }
    f(entry.as_object_mut().unwrap());
    let _ = write_json(&cache_file(), &Value::Object(cache), 1);
}

pub fn entry(photo: &str) -> Option<Map<String, Value>> {
    let _g = CACHE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    load_cache().get(photo).and_then(|v| v.as_object().cloned())
}

pub fn cached_lines(photo: &str) -> Vec<Line> {
    entry(photo)
        .and_then(|e| e.get("lines").cloned())
        .and_then(|v| serde_json::from_value(v).ok())
        .unwrap_or_default()
}

/// (Dienst, Aufgabe) der gespeicherten Antwort – „Letzte KI“
pub fn last_ai(photo: &str, cfg: &Cfg) -> Option<(String, String)> {
    let e = entry(photo)?;
    let who = e.get("who")?.get(key(cfg))?.as_array()?.clone();
    Some((who.first()?.as_str()?.to_string(), who.get(1)?.as_str()?.to_string()))
}

pub struct PhotoResult {
    pub ocr: String,
    pub lines: Vec<Line>,
    pub translated: String,
    pub method: String,
    pub task: String,
    pub cached: bool,
    pub errors: Vec<String>,
}

/// Foto lesen + übersetzen (mit Cache) – wie translation.translate_photo.
/// `force` = ↻ Nochmal senden: gespeicherte Antwort nicht nehmen (bleibt aber, bis die neue da ist)
pub fn translate_photo(
    photo: &Path,
    cfg: &Cfg,
    force: bool,
    ocr: &mut dyn FnMut(&Path) -> Result<Vec<Line>, String>,
    progress: &dyn Progress,
) -> Result<PhotoResult, String> {
    let name = photo.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let mut method = cfg.s("tr_method");
    let mut res = PhotoResult {
        ocr: String::new(),
        lines: Vec::new(),
        translated: String::new(),
        method: method.clone(),
        task: MODE_TRANSLATE.into(),
        cached: false,
        errors: Vec::new(),
    };
    progress.step("ocr", "");
    let hit = entry(&name);
    if let Some(e) = hit.as_ref().filter(|e| e.contains_key("ocr")) {
        res.ocr = e["ocr"].as_str().unwrap_or("").to_string();
        res.lines = e.get("lines").cloned().and_then(|v| serde_json::from_value(v).ok()).unwrap_or_default();
    } else {
        res.lines = ocr(photo)?;
        res.ocr = res.lines.iter().map(|l| l.text.as_str()).collect::<Vec<_>>().join("\n");
        let (t, l) = (res.ocr.clone(), serde_json::to_value(&res.lines).unwrap_or_default());
        update_entry(&name, |e| {
            e.insert("ocr".into(), Value::from(t));
            e.insert("lines".into(), l);
        });
    }
    if res.ocr.is_empty() && method != llm::VISION {
        return Ok(res);
    }
    let k = key(cfg);
    if let Some(t) = entry(&name).filter(|_| !force).and_then(|e| e.get("tr").and_then(|tr| tr.get(&k)).and_then(|v| v.as_str().map(String::from))) {
        res.translated = t;
        res.cached = true;
        if let Some((m, task)) = last_ai(&name, cfg) {
            res.method = m;
            res.task = task;
        }
        return Ok(res);
    }
    let Some(done) = translate_text_used(&res.ocr, cfg, &mut res.errors, progress, Some(photo)) else {
        if res.ocr.is_empty() {
            return Ok(res);
        }
        return Err(res.errors.join("; "));
    };
    method = done.method.clone();
    // unter dem Dienst merken, der es wirklich übersetzt hat
    let mut planned = vec![cfg.s("tr_method")];
    planned.extend(TASK_KEYS.iter().map(|(m, _)| task_method(cfg, m)));
    let used_key = if planned.contains(&method) {
        k
    } else {
        key(&cfg.with(&[("tr_method", &method), ("tr_llm_mode", MODE_TRANSLATE)]))
    };
    let (t, who) = (done.text.clone(), json!([done.method, done.task]));
    update_entry(&name, |e| {
        let tr = e.entry("tr").or_insert_with(|| json!({}));
        if let Some(o) = tr.as_object_mut() {
            o.insert(used_key.clone(), Value::from(t));
        }
        let w = e.entry("who").or_insert_with(|| json!({}));
        if let Some(o) = w.as_object_mut() {
            o.insert(used_key, who);
        }
    });
    res.translated = done.text;
    res.method = method;
    res.task = done.task;
    Ok(res)
}

/// 🕘 Verlauf (nur wenn in der App eingeschaltet) – wie core/history.add
pub fn add_history(cfg: &Cfg, photo: &str, ocr: &str, translated: &str, method: &str) {
    if !cfg.b("history") || translated.is_empty() || !WRITE_ALLOWED() {
        return;
    }
    let file = crate::paths::config_dir().join("history.json");
    let mut entries: Vec<Value> = std::fs::read_to_string(&file).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default();
    if entries.iter().any(|e| e["photo"] == photo && e["tr"] == translated) {
        return;
    }
    let time = chrono::Local::now().format("%Y-%m-%d %H:%M").to_string();
    entries.insert(0, json!({"time": time, "photo": photo, "ocr": ocr, "tr": translated, "method": method}));
    entries.truncate(200);
    let _ = write_json(&file, &Value::Array(entries), 1);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::UI_DEFAULTS;

    fn cfg(pairs: &[(&str, &str)]) -> Cfg {
        Cfg::with_defaults(UI_DEFAULTS, None).with(pairs)
    }

    #[test]
    fn keys_like_python() {
        assert_eq!(key(&cfg(&[])), "lingva|auto|de");
        let c = cfg(&[("tr_method", "llm_vision"), ("tr_llm_mode", "answer")]);
        assert_eq!(key(&c), "llm_vision@qwen2.5vl:7b#answer4|auto|de");
        let c = cfg(&[("tr_method", "libre"), ("tr_answer_method", "llm_claude"), ("tr_llm_mode", "answer")]);
        assert_eq!(key(&c), "libre#answer4=llm_claude@sonnet|auto|de");
    }

    #[test]
    fn auto_once_counts_for_two_photos() {
        let mut c = cfg(&[("tr_method", "llm_vision"), ("tr_auto_once", "explain"), ("tr_auto_once_photo", "a.png")]);
        assert_eq!(photo_task_cfg(&mut c, "a.png").0.s("tr_llm_mode"), "explain");
        assert_eq!(photo_task_cfg(&mut c, "b.png").0.s("tr_llm_mode"), "explain");
        assert_eq!(photo_task_cfg(&mut c, "c.png").0.s("tr_llm_mode"), "auto");
    }

    #[test]
    fn quiz_rule() {
        assert!(looks_like_quiz("Welches Tier?\nHund\nKatze"));
        assert!(!looks_like_quiz("Willkommen\nim Hotel"));
    }
}
