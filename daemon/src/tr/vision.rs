//! 🖼 Lokales Bild-LLM über Ollama – wie UI/core/vision.py (gleiche Prompts).
//! Bekommt das Foto mit; läuft komplett auf dem eigenen PC.

use super::llm::{self, lang_name, numbered_lines, MODE_ANSWER, MODE_EXPLAIN, MODE_TRANSLATE};
use crate::settings::Cfg;
use serde_json::{json, Value};
use std::path::Path;
use std::time::Duration;

pub const DEFAULT_URL: &str = "http://127.0.0.1:11434";
pub const NO_TEXT: &str = "NO_TEXT";
const MAX_IMAGE: u32 = 1600;

pub fn url_of(cfg: &Cfg) -> String {
    let u = cfg.s("tr_vision_url").trim().to_string();
    if u.is_empty() { DEFAULT_URL.to_string() } else { u }.trim_end_matches('/').to_string()
}

pub fn build_prompt(text: &str, target: &str, mode: &str, has_image: bool) -> String {
    let tgt = lang_name(target);
    let ocr = if text.trim().is_empty() { "(nothing found – read the text from the image yourself)".to_string() } else { text.trim().to_string() };
    let where_ = if has_image { "the image and the OCR text" } else { "the OCR text" };
    if mode == MODE_ANSWER {
        let numbered = numbered_lines(&ocr);
        return format!(
            "This is a quiz, riddle or task from a VR game. Look at {where_}. The numbered lines are the question and the answer options – the player sees the SAME numbers.\n<<<\n{numbered}\n>>>\n\nThink first, then answer. Do NOT just pick the first option.\nLine 1: 💡 what is asked – e.g. write the complete proverb/idiom/fact it refers to and what it means, in {tgt}.\nLine 2: ➜ <number>) <the option that fits line 1, exactly as written> (<its meaning in {tgt}>)\nReply with exactly these two lines."
        );
    }
    if mode != MODE_TRANSLATE {
        return format!(
            "Look at {where_}. Explain in {tgt}, in at most 4 short lines, what it is about and what it means for the player. No introduction.\n\nOCR text:\n<<<\n{ocr}\n>>>\n\nReply in {tgt}."
        );
    }
    let all = crate::ocr::splitlines(text);
    let lines: Vec<&String> = all.iter().filter(|t| !t.trim().is_empty()).collect();
    let intro = if has_image { "The attached image is a photo taken in a VR game (e.g. VRChat). " } else { "" };
    if lines.is_empty() {
        return format!(
            "{intro}Read ALL text in the image and translate it into {tgt}. One output line per text line, top to bottom. Reply with the translations only. If there is no text at all, reply exactly: {NO_TEXT}"
        );
    }
    let numbered = lines.iter().enumerate().map(|(i, t)| format!("{}) {t}", i + 1)).collect::<Vec<_>>().join("\n");
    let fix = if has_image { "use the image to correct them" } else { "fix obvious mistakes" };
    let n = lines.len();
    format!(
        "{intro}OCR read these {n} lines from it (they may contain OCR mistakes – {fix}):\n{numbered}\n\nTranslate each line into {tgt}. Reply with EXACTLY {n} lines in the same order – only the translations, no numbers, no quotes, no explanations. If a line is already in {tgt} or is a name, repeat it unchanged."
    )
}

pub fn classify_prompt(text: &str, has_image: bool) -> String {
    let where_ = if has_image { "the image and the OCR text" } else { "the OCR text" };
    let ocr = if text.trim().is_empty() { "(nothing found – look at the image)".to_string() } else { text.trim().to_string() };
    format!(
        "Look at {where_}. Is there a question, quiz, riddle, fill-in-the-blank or task that the player has to solve (for example with answer buttons)? Normal text, signs, stories and dialogue are NO.\n\nOCR text:\n<<<\n{ocr}\n>>>\n\nReply with exactly one word: YES or NO."
    )
}

pub fn task_prompt(text: &str, has_image: bool) -> String {
    let where_ = if has_image { "the image and the OCR text" } else { "the text" };
    let ocr = if text.trim().is_empty() { "(nothing found – look at the image)".to_string() } else { text.trim().to_string() };
    format!(
        "Look at {where_} from a VR game. What does the player need?\nQUIZ = there is a question, quiz, riddle, fill-in-the-blank or task to solve (for example with answer buttons).\nEXPLAIN = a joke, meme, pun, wordplay or cultural reference that a plain translation would not make understandable.\nTEXT = everything else (signs, menus, dialogue, stories, rules) – just translate.\n\nText:\n<<<\n{ocr}\n>>>\n\nReply with exactly one word: QUIZ, EXPLAIN or TEXT."
    )
}

pub fn parse_task(verdict: &str) -> &'static str {
    let v = verdict.to_uppercase();
    if v.contains("QUIZ") {
        MODE_ANSWER
    } else if v.contains("EXPLAIN") {
        MODE_EXPLAIN
    } else {
        MODE_TRANSLATE
    }
}

pub fn system_prompt(target: &str) -> String {
    let tgt = lang_name(target);
    format!(
        "You help a player inside a VR game (e.g. VRChat). ALWAYS write your reply in {tgt}. Only quote text in its original language when it is a button or option the player has to click. Plain text, no Markdown, short."
    )
}

pub fn clean_answer(out: &str, mode: &str) -> String {
    let mut out = out.trim().to_string();
    if out == NO_TEXT || out.to_uppercase().starts_with(NO_TEXT) {
        return String::new();
    }
    if let Some((first, rest)) = out.split_once('\n') {
        let f = first.trim().trim_matches(|c| ".:!".contains(c)).to_uppercase();
        if ["YES", "NO", "JA", "NEIN"].contains(&f.as_str()) && !rest.trim().is_empty() {
            out = rest.trim().to_string();
        }
    }
    if mode == MODE_TRANSLATE {
        let re = regex::Regex::new(r"^\s*\d{1,3}\s*[).:\]-]\s*").unwrap();
        out = crate::ocr::splitlines(&out).iter().map(|l| re.replace(l, "").to_string()).collect::<Vec<_>>().join("\n");
    }
    out.trim().to_string()
}

/// Foto als Base64-PNG, lange Seite höchstens 1600 px
pub fn image_b64(path: &Path) -> Result<String, String> {
    use base64::Engine as _;
    let mut img = image::open(path).map_err(|e| format!("Bild nicht lesbar: {e}"))?;
    if img.width().max(img.height()) > MAX_IMAGE {
        img = img.resize(MAX_IMAGE, MAX_IMAGE, image::imageops::FilterType::Triangle);
    }
    let mut buf = std::io::Cursor::new(Vec::new());
    img.write_to(&mut buf, image::ImageFormat::Png).map_err(|e| e.to_string())?;
    Ok(base64::engine::general_purpose::STANDARD.encode(buf.into_inner()))
}

fn base(cfg: &Cfg, target: &str, image: Option<&Path>) -> Result<Value, String> {
    let keep = { let k = cfg.s("tr_vision_keep_alive"); if k.is_empty() { "2m".to_string() } else { k } };
    let mut v = json!({
        "model": llm::model_of(llm::VISION, cfg),
        "system": system_prompt(target),
        "keep_alive": keep,
    });
    if let Some(p) = image {
        v["images"] = json!([image_b64(p)?]);
    }
    Ok(v)
}

fn generate(cfg: &Cfg, mut payload: Value, timeout: u64) -> Result<String, String> {
    let url = url_of(cfg);
    let model = payload["model"].as_str().unwrap_or("").to_string();
    payload["stream"] = Value::Bool(false);
    let agent = ureq::AgentBuilder::new().timeout(Duration::from_secs(timeout)).build();
    match agent.post(&format!("{url}/api/generate")).send_json(payload) {
        Ok(r) => {
            let v: Value = r.into_json().map_err(|e| format!("Ollama: {e}"))?;
            if let Some(e) = v["error"].as_str() {
                return Err(format!("Ollama: {e}"));
            }
            Ok(v["response"].as_str().unwrap_or("").to_string())
        }
        Err(ureq::Error::Status(code, r)) => {
            let body = r.into_string().unwrap_or_default();
            if code == 404 || body.to_lowercase().contains("not found") {
                Err(format!("Ollama: Modell „{model}“ fehlt – Optionen → Übersetzung → 📥 Modell laden (ollama pull {model})"))
            } else {
                Err(format!("Ollama: HTTP {code} {}", body.chars().take(160).collect::<String>()))
            }
        }
        Err(e) => Err(format!("Ollama nicht erreichbar ({url}) – läuft es? systemctl enable --now ollama ({e})")),
    }
}

/// 🤖 Auto mit dem Bild-LLM: Ein-Wort-Frage → Aufgabe
pub fn classify(cfg: &Cfg, text: &str, image: Option<&Path>) -> Result<&'static str, String> {
    let mut p = base(cfg, &cfg.s("tr_target"), image)?;
    p["prompt"] = Value::from(task_prompt(text, image.is_some()));
    p["options"] = json!({"temperature": 0.0, "num_predict": 4});
    Ok(parse_task(&generate(cfg, p, 60)?))
}

pub fn is_quiz(cfg: &Cfg, text: &str, image: Option<&Path>) -> Result<bool, String> {
    let mut p = base(cfg, &cfg.s("tr_target"), image)?;
    p["prompt"] = Value::from(classify_prompt(text, image.is_some()));
    p["options"] = json!({"temperature": 0.0, "num_predict": 4});
    let v = generate(cfg, p, 60)?.to_uppercase();
    Ok(v.contains("YES") || v.contains("JA"))
}

pub fn translate(cfg: &Cfg, text: &str, _source: &str, target: &str, image: Option<&Path>) -> Result<String, String> {
    let mut mode = { let m = cfg.s("tr_llm_mode"); if m.is_empty() { MODE_TRANSLATE.to_string() } else { m } };
    let mut p = base(cfg, target, image)?;
    // „Frage beantworten“ von Hand gewählt: erst „Quiz?“ (bei 🤖 Auto schon entschieden)
    if mode == MODE_ANSWER && !cfg.b("_routed") && !is_quiz(cfg, text, image)? {
        mode = MODE_TRANSLATE.to_string();
    }
    p["prompt"] = Value::from(build_prompt(text, target, &mode, image.is_some()));
    p["options"] = json!({"temperature": 0.2});
    Ok(clean_answer(&generate(cfg, p, 300)?, &mode))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean() {
        assert_eq!(clean_answer("YES\n➜ 3) x", MODE_ANSWER), "➜ 3) x");
        assert_eq!(clean_answer("1) Hallo\n2) Welt", MODE_TRANSLATE), "Hallo\nWelt");
        assert_eq!(clean_answer("NO_TEXT", MODE_TRANSLATE), "");
        assert_eq!(parse_task("quiz."), MODE_ANSWER);
    }
}
