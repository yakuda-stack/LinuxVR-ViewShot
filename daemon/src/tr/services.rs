//! Klassische Übersetzer – wie UI/core/translators.py (aus OSC-DreamChatbox):
//! Lingva, Google (ohne/mit Schlüssel), LibreTranslate (lokal/online), DeepL.

use crate::settings::Cfg;
use serde_json::Value;
use std::time::Duration;

pub const LINGVA: &str = "lingva";
pub const GOOGLE: &str = "google";
pub const LIBRE: &str = "libre";
pub const LIBRE_ONLINE: &str = "libre_online";
pub const DEEPL: &str = "deepl";
pub const CUSTOM: &str = "custom";

const DEFAULT_LINGVA_URL: &str = "https://lingva.adminforge.de";
pub const DEFAULT_LIBRE_URL: &str = "http://127.0.0.1:5000";
const DEFAULT_LIBRE_ONLINE_URL: &str = "https://de.libretranslate.com";
const LIBRE_UA: &str = "Mozilla/5.0 (X11; Linux x86_64) OSC-DreamChatbox (+https://github.com/yakuda-stack/OSC-DreamChatbox)";
const TIMEOUT: Duration = Duration::from_secs(8);

fn agent() -> ureq::Agent {
    ureq::AgentBuilder::new().timeout(TIMEOUT).build()
}

/// 'zh-CN' → 'zh'
pub fn lang_base(code: &str) -> String {
    code.split('-').next().unwrap_or("").to_lowercase()
}

fn libre_code(code: &str) -> String {
    let low = code.trim().to_lowercase();
    match low.as_str() {
        "zh" | "zh-cn" | "zh-sg" | "zh-hans" => "zh-Hans".into(),
        "zh-tw" | "zh-hk" | "zh-hant" => "zh-Hant".into(),
        "pt-br" => "pt-BR".into(),
        _ => lang_base(&low),
    }
}

/// urllib.parse.quote(text, safe=…)
pub fn quote(s: &str, safe: &str) -> String {
    let mut out = String::new();
    for b in s.bytes() {
        let c = b as char;
        if c.is_ascii_alphanumeric() || "_.-~".contains(c) || safe.contains(c) {
            out.push(c);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

fn form(params: &[(&str, &str)]) -> String {
    // urlencode: Leerzeichen → "+"
    params
        .iter()
        .map(|(k, v)| format!("{}={}", quote(k, "").replace("%20", "+"), quote(v, " ").replace(' ', "+")))
        .collect::<Vec<_>>()
        .join("&")
}

fn html_unescape(s: &str) -> String {
    let re = regex::Regex::new(r"&(#x[0-9a-fA-F]+|#[0-9]+|amp|lt|gt|quot|apos|#39);").unwrap();
    re.replace_all(s, |c: &regex::Captures| {
        let e = &c[1];
        match e {
            "amp" => "&".to_string(),
            "lt" => "<".to_string(),
            "gt" => ">".to_string(),
            "quot" => "\"".to_string(),
            "apos" | "#39" => "'".to_string(),
            _ if e.starts_with("#x") => u32::from_str_radix(&e[2..], 16).ok().and_then(char::from_u32).map(String::from).unwrap_or_default(),
            _ => e[1..].parse().ok().and_then(char::from_u32).map(String::from).unwrap_or_default(),
        }
    })
    .to_string()
}

fn nonempty(s: String) -> Option<String> {
    let t = s.trim().to_string();
    (!t.is_empty()).then_some(t)
}

/// (Übersetzung oder None, Fehlertext)
pub fn translate(method: &str, cfg: &Cfg, text: &str, src: &str, tgt: &str) -> (Option<String>, String) {
    match method {
        GOOGLE => google(cfg, text, src, tgt),
        LIBRE => libre(&cfg.s("tr_libre_url"), "", text, src, tgt, false),
        LIBRE_ONLINE => libre(&cfg.s("tr_libre_online_url"), &cfg.s("tr_libre_online_key"), text, src, tgt, true),
        DEEPL => deepl(&cfg.s("tr_deepl_key"), text, src, tgt),
        CUSTOM => (None, "Custom: eigener Übersetzer geht nur mit offener App".into()),
        _ => lingva(text, src, tgt),
    }
}

fn lingva(text: &str, src: &str, tgt: &str) -> (Option<String>, String) {
    let s = { let b = lang_base(src); if b.is_empty() { "auto".to_string() } else { b } };
    let t = lang_base(tgt);
    if t.is_empty() {
        return (None, String::new());
    }
    let url = format!("{DEFAULT_LINGVA_URL}/api/v1/{s}/{t}/{}", quote(text, ""));
    match agent().get(&url).set("User-Agent", "OSC-DreamChatbox").call() {
        Ok(r) => match r.into_json::<Value>() {
            Ok(v) => (nonempty(v["translation"].as_str().unwrap_or("").to_string()), String::new()),
            Err(e) => (None, format!("Lingva: {e}")),
        },
        Err(e) => (None, format!("Lingva: {e}")),
    }
}

fn google(cfg: &Cfg, text: &str, src: &str, tgt: &str) -> (Option<String>, String) {
    let t = lang_base(tgt);
    if t.is_empty() {
        return (None, String::new());
    }
    let s = { let b = lang_base(src); if b.is_empty() { "auto".to_string() } else { b } };
    let key = cfg.s("tr_google_key").trim().to_string();
    if !key.is_empty() {
        let mut params = vec![("key", key.as_str()), ("q", text), ("target", t.as_str()), ("format", "text")];
        if s != "auto" {
            params.push(("source", s.as_str()));
        }
        return match agent()
            .post("https://translation.googleapis.com/language/translate/v2")
            .set("User-Agent", "OSC-DreamChatbox")
            .set("Content-Type", "application/x-www-form-urlencoded")
            .send_string(&form(&params))
        {
            Ok(r) => match r.into_json::<Value>() {
                Ok(v) => (
                    nonempty(html_unescape(v["data"]["translations"][0]["translatedText"].as_str().unwrap_or(""))),
                    String::new(),
                ),
                Err(e) => (None, format!("Google API: {e}")),
            },
            Err(ureq::Error::Status(code, _)) if [400, 401, 403].contains(&code) => (
                None,
                format!("Google API: key rejected (HTTP {code}) – check the key and make sure the Cloud Translation API is enabled for the project."),
            ),
            Err(ureq::Error::Status(code, _)) => (None, format!("Google API: HTTP {code}")),
            Err(e) => (None, format!("Google API: {e}")),
        };
    }
    let url = format!(
        "https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl={}&tl={}&q={}",
        quote(&s, "/"),
        quote(&t, "/"),
        quote(text, "/")
    );
    match agent().get(&url).set("User-Agent", "OSC-DreamChatbox").call() {
        Ok(r) => match r.into_json::<Value>() {
            Ok(v) => {
                let out: String = v[0]
                    .as_array()
                    .map(|segs| segs.iter().filter_map(|seg| seg[0].as_str()).collect::<Vec<_>>().join(""))
                    .unwrap_or_default();
                (nonempty(out), String::new())
            }
            Err(e) => (None, format!("Google (keyless): {e}")),
        },
        Err(ureq::Error::Status(code, _)) if code == 429 || code == 403 => (
            None,
            format!("Google (keyless): blocked/rate-limited (HTTP {code}). The unofficial endpoint is shared by everyone – enter your own API key or use Lingva."),
        ),
        Err(ureq::Error::Status(code, _)) => (None, format!("Google (keyless): HTTP {code}")),
        Err(e) => (None, format!("Google (keyless): {e}")),
    }
}

fn libre(url: &str, key: &str, text: &str, src: &str, tgt: &str, online: bool) -> (Option<String>, String) {
    let (default, scheme, name) = if online {
        (DEFAULT_LIBRE_ONLINE_URL, "https", "LibreTranslate Online")
    } else {
        (DEFAULT_LIBRE_URL, "http", "LibreTranslate")
    };
    let mut url = if url.trim().is_empty() { default.to_string() } else { url.trim().trim_end_matches('/').to_string() };
    if !url.contains("://") {
        url = format!("{scheme}://{url}");
    }
    let t = libre_code(tgt);
    if t.is_empty() {
        return (None, String::new());
    }
    let s = { let c = libre_code(src); if c.is_empty() { "auto".to_string() } else { c } };
    let mut attempts = vec![(s.clone(), t.clone())];
    if s != "auto" {
        attempts.push(("auto".into(), t.clone()));
    }
    let base = lang_base(&t);
    if base != t {
        attempts.push(("auto".into(), base));
    }
    let mut msg = String::new();
    for (a_src, a_tgt) in attempts {
        let mut payload = serde_json::json!({"q": text, "source": a_src, "target": a_tgt, "format": "text"});
        if !key.is_empty() {
            payload["api_key"] = Value::from(key);
        }
        match agent()
            .post(&format!("{url}/translate"))
            .set("Content-Type", "application/json")
            .set("Accept", "application/json")
            .set("User-Agent", LIBRE_UA)
            .send_json(payload)
        {
            Ok(r) => {
                let v: Value = r.into_json().unwrap_or_default();
                return (nonempty(v["translatedText"].as_str().unwrap_or("").to_string()), String::new());
            }
            Err(ureq::Error::Status(code, r)) => {
                let body: Value = r.into_json().unwrap_or_default();
                msg = body["error"].as_str().map(String::from).unwrap_or_else(|| format!("HTTP {code}"));
                if code != 400 {
                    break;
                }
            }
            Err(e) => {
                if online {
                    return (None, format!("LibreTranslate Online: {url} did not answer. The public instance may be down or blocking you - try another server, or run a local one."));
                }
                return (None, format!("LibreTranslate not reachable at {url} ({e}) – is the local instance running?"));
            }
        }
    }
    (None, format!("{name}: {msg}"))
}

fn deepl(key: &str, text: &str, src: &str, tgt: &str) -> (Option<String>, String) {
    let key = key.trim();
    if key.is_empty() {
        return (None, "DeepL: no API key configured".into());
    }
    let low = tgt.to_lowercase();
    let target = match low.as_str() {
        "en" => "EN-US".to_string(),
        "pt" => "PT-PT".to_string(),
        "zh" | "zh-cn" => "ZH".to_string(),
        _ => lang_base(&low).to_uppercase(),
    };
    let host = if key.ends_with(":fx") { "api-free.deepl.com" } else { "api.deepl.com" };
    let s = lang_base(src).to_uppercase();
    let mut params = vec![("text", text), ("target_lang", target.as_str())];
    if !s.is_empty() {
        params.push(("source_lang", s.as_str()));
    }
    match agent()
        .post(&format!("https://{host}/v2/translate"))
        .set("Authorization", &format!("DeepL-Auth-Key {key}"))
        .set("Content-Type", "application/x-www-form-urlencoded")
        .send_string(&form(&params))
    {
        Ok(r) => {
            let v: Value = r.into_json().unwrap_or_default();
            let out = v["translations"]
                .as_array()
                .map(|a| a.iter().filter_map(|t| t["text"].as_str()).collect::<Vec<_>>().join(" "))
                .unwrap_or_default();
            (nonempty(out), String::new())
        }
        Err(ureq::Error::Status(456, _)) => (None, "DeepL: monthly character limit reached (quota exceeded)".into()),
        Err(ureq::Error::Status(401 | 403, _)) => (None, "DeepL: invalid API key".into()),
        Err(ureq::Error::Status(429, _)) => (None, "DeepL: rate limit hit".into()),
        Err(ureq::Error::Status(code, _)) => (None, format!("DeepL: HTTP {code}")),
        Err(e) => (None, format!("DeepL: {e}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quote_like_python() {
        assert_eq!(quote("a b/ä?", ""), "a%20b%2F%C3%A4%3F");
        assert_eq!(quote("a/b", "/"), "a/b");
        assert_eq!(form(&[("q", "a b&c")]), "q=a+b%26c");
    }

    #[test]
    fn codes() {
        assert_eq!(lang_base("zh-CN"), "zh");
        assert_eq!(libre_code("zh-CN"), "zh-Hans");
        assert_eq!(html_unescape("a &amp; b &#39;c&#39;"), "a & b 'c'");
    }
}
