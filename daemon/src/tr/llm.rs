//! KI über ihr Kommandozeilen-Programm – wie UI/core/llm_translator.py:
//! Claude Code, Gemini CLI, ChatGPT (Codex CLI) oder ein eigener Befehl.
//! Die Prompts sind Wort für Wort dieselben (geprüft über daemon_contract.json).

use super::vision;
use crate::settings::Cfg;
use std::io::{Read, Write};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub const CLAUDE: &str = "llm_claude";
pub const GEMINI: &str = "llm_gemini";
pub const CHATGPT: &str = "llm_chatgpt";
pub const LLM_CUSTOM: &str = "llm_custom";
pub const VISION: &str = "llm_vision";
pub const METHODS: [&str; 5] = [CLAUDE, GEMINI, CHATGPT, LLM_CUSTOM, VISION];

pub const MODE_TRANSLATE: &str = "translate";
pub const MODE_EXPLAIN: &str = "explain";
pub const MODE_ANSWER: &str = "answer";
pub const MODE_AUTO: &str = "auto";
pub const MODE_CLASSIFY: &str = "classify";
pub const MODES: [&str; 3] = [MODE_TRANSLATE, MODE_EXPLAIN, MODE_ANSWER];
pub const TASK_KEYS: [(&str, &str); 2] = [(MODE_EXPLAIN, "tr_explain_method"), (MODE_ANSWER, "tr_answer_method")];

const RETRIES: usize = 2;
const TIMEOUT: u64 = 300;

pub fn is_llm(method: &str) -> bool {
    METHODS.contains(&method)
}

pub fn binary(method: &str) -> Option<&'static str> {
    match method {
        CLAUDE => Some("claude"),
        GEMINI => Some("gemini"),
        CHATGPT => Some("codex"),
        VISION => Some("ollama"),
        _ => None,
    }
}

pub fn model_key(method: &str) -> Option<&'static str> {
    match method {
        CLAUDE => Some("tr_llm_claude_model"),
        GEMINI => Some("tr_llm_gemini_model"),
        CHATGPT => Some("tr_llm_chatgpt_model"),
        VISION => Some("tr_llm_vision_model"),
        _ => None,
    }
}

/// Eingestelltes Modell; leer → Standard-Modell der Vorlage
pub fn model_of(method: &str, cfg: &Cfg) -> String {
    let Some(key) = model_key(method) else { return String::new() };
    let m = cfg.s(key).trim().to_string();
    if !m.is_empty() {
        return m;
    }
    crate::settings::Cfg::with_defaults(crate::settings::UI_DEFAULTS, None).s(key)
}

/// Programm im PATH suchen – und in ~/.local/bin (dort landet der Installier-Knopf)
pub fn find_binary(name: &str) -> Option<PathBuf> {
    let mut dirs: Vec<PathBuf> = std::env::var_os("PATH").map(|p| std::env::split_paths(&p).collect()).unwrap_or_default();
    let home = dirs::home_dir().unwrap_or_default();
    dirs.push(home.join(".local/bin"));
    dirs.push(home.join(".npm-global/bin"));
    // nvm: ~/.nvm/versions/node/<Version>/bin (neueste zuerst)
    if let Ok(rd) = std::fs::read_dir(home.join(".nvm/versions/node")) {
        let mut v: Vec<PathBuf> = rd.flatten().map(|e| e.path().join("bin")).collect();
        v.sort();
        dirs.extend(v.into_iter().rev());
    }
    for d in ["/usr/local/bin", "/usr/bin", "/bin"] {
        dirs.push(PathBuf::from(d));
    }
    dirs.into_iter().map(|d| d.join(name)).find(|p| is_exe(p))
}

fn is_exe(p: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    std::fs::metadata(p).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
}

pub fn installed(method: &str) -> bool {
    binary(method).is_some_and(|b| find_binary(b).is_some())
}

pub fn lang_name(code: &str) -> String {
    match code.to_lowercase().as_str() {
        "de" => "German",
        "en" => "English",
        "fr" => "French",
        "es" => "Spanish",
        "it" => "Italian",
        "pt" => "Portuguese",
        "nl" => "Dutch",
        "pl" => "Polish",
        "ru" => "Russian",
        "uk" => "Ukrainian",
        "tr" => "Turkish",
        "ja" => "Japanese",
        "ko" => "Korean",
        "zh" | "zh-cn" => "Chinese (Simplified)",
        _ => return code.to_string(),
    }
    .to_string()
}

/// „1) …“ je Zeile (ab 2 Zeilen)
pub fn numbered_lines(text: &str) -> String {
    let all = crate::ocr::splitlines(text);
    let lines: Vec<&String> = all.iter().filter(|t| !t.trim().is_empty()).collect();
    if lines.len() < 2 {
        return text.to_string();
    }
    lines.iter().enumerate().map(|(i, t)| format!("{}) {t}", i + 1)).collect::<Vec<_>>().join("\n")
}

/// Prompt-Version für den Cache-Schlüssel ("" = keine)
pub fn prompt_version(method: &str, mode: &str) -> String {
    let v = match (method, mode) {
        (CHATGPT, MODE_ANSWER) => 5,
        (VISION, MODE_EXPLAIN) => 2,
        (VISION, MODE_ANSWER) => 4,
        (_, MODE_EXPLAIN) => 3,
        (_, MODE_ANSWER) => 4,
        _ => return String::new(),
    };
    v.to_string()
}

const OCR_NOTE: &str = "The text was read from a screenshot by OCR, so ignore obvious OCR mistakes. ";
const PLAIN: &str = "Plain text only, no Markdown (no ** or #); simple '- ' lists are fine. ";
const FAST: &str = "Answer immediately from your own knowledge: do NOT use any tools, do NOT search the web, do NOT read files, do not think for long. Keep it SHORT – no essay. ";

fn answer_prompt(tgt: &str) -> String {
    format!(
        "The following text was photographed in a VR game (e.g. VRChat) – often a quiz, puzzle, riddle or escape room. {OCR_NOTE}\
The lines are in reading order; answer choices / buttons usually come as separate short lines after the question.\n\
What to do:\n\
- Multiple choice (buttons, options): say which option is correct. Quote it EXACTLY as written in the photo (original language and script), so the user can find and click it.\n\
- Fill in the blank (○○, __, ??, □, …): say exactly what to enter, in the original script, and the complete word/phrase.\n\
- Riddle, question, math, code: give the solution.\n\
- If there is no question or task at all: reply ONLY with the translation into {tgt} (no ➜, no comment).\n\
If the lines are numbered (1), 2), …): the user sees the SAME numbers next to the text in the photo – start your answer with the number of the correct option.\n\
Answer format (only when there is a question/task):\n\
First line: '➜ ' followed ONLY by the option number (if numbered) and what to click / enter / the answer, e.g. '➜ 4) … (…)' (original script, then its meaning in {tgt} in brackets).\n\
Then ONE short line in {tgt}: why (e.g. the full phrase and what it means). Nothing else – no introduction, no translation of the whole text. {PLAIN}{FAST}"
    )
}

const CHATGPT_ANSWER_EXTRA: &str = "\nImportant: if there is a blank AND answer buttons, the answer is the button to click – quote the WHOLE button text exactly, never only the missing characters or the first letters. Example: '灯台○○' with buttons '足元暗し', '下暗し' → '➜ 下暗し', not '➜ 下'.";

pub fn make_prompt(text: &str, source: &str, target: &str, mode: &str, method: &str) -> String {
    let tgt = lang_name(target);
    let src = if source.is_empty() { String::new() } else { lang_name(source) };
    let frm = if src.is_empty() { String::new() } else { format!("from {src} ") };
    match mode {
        MODE_CLASSIFY => vision::task_prompt(text, false),
        MODE_EXPLAIN => format!(
            "The following text was photographed in a VR game (e.g. VRChat). {OCR_NOTE}Explain in {tgt} in at most 4 short lines what it is about and what it means: context, important terms, what the user can do. No introduction. {PLAIN}{FAST}\n\nText from the photo:\n<<<\n{text}\n>>>"
        ),
        MODE_ANSWER => {
            let extra = if method == CHATGPT { CHATGPT_ANSWER_EXTRA } else { "" };
            format!("{}{extra}\n\nText from the photo:\n<<<\n{}\n>>>", answer_prompt(&tgt), numbered_lines(text))
        }
        _ => format!(
            "Translate the following text {frm}into {tgt}. The text was read from a screenshot by OCR, so fix obvious OCR mistakes. Keep the line breaks. Reply with the translation ONLY – no explanations, no quotes, no notes. {FAST}\n\n{text}"
        ),
    }
}

/// (argv, stdin) für die Vorlage – ohne Streaming (der Dienst zeigt erst das Ergebnis)
pub fn build_command(method: &str, cfg: &Cfg, prompt: &str, text: &str, source: &str, target: &str) -> Result<(Vec<String>, Option<String>), String> {
    let model = model_of(method, cfg);
    let s = |v: &str| v.to_string();
    Ok(match method {
        CLAUDE => {
            let mut argv = vec![s("claude"), s("-p"), s(prompt)];
            if !model.is_empty() {
                argv.extend([s("--model"), model]);
            }
            (argv, None)
        }
        GEMINI => {
            let mut argv = vec![s("gemini")];
            if !model.is_empty() {
                argv.extend([s("-m"), model]);
            }
            argv.extend([s("-p"), s(prompt), s("--output-format"), s("json")]);
            (argv, None)
        }
        CHATGPT => {
            let mut argv: Vec<String> = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only", "-c", "model_reasoning_effort=low"]
                .iter()
                .map(|v| v.to_string())
                .collect();
            if !model.is_empty() {
                argv.extend([s("-m"), model]);
            }
            argv.push(s("-"));
            (argv, Some(prompt.to_string()))
        }
        _ => {
            let cmd = cfg.s("tr_llm_custom_cmd").trim().to_string();
            if cmd.is_empty() {
                return Err("kein Befehl eingetragen".into());
            }
            let parts = shlex::split(&cmd).ok_or("Befehl nicht lesbar")?;
            let src = if source.is_empty() { "auto" } else { source };
            let uses_input = parts.iter().any(|p| p.contains("{prompt}") || p.contains("{text}"));
            let argv = parts
                .into_iter()
                .map(|p| {
                    p.replace("{prompt}", prompt)
                        .replace("{text}", text)
                        .replace("{source}", src)
                        .replace("{target}", target)
                        .replace("{model}", &model)
                })
                .collect();
            (argv, (!uses_input).then(|| prompt.to_string()))
        }
    })
}

const LOGIN_HINTS: [&str; 8] = [
    "/login",
    "invalid api key",
    "not logged in",
    "please log in",
    "please login",
    "codex login",
    "authentication required",
    "native binary not installed",
];

pub fn clean(text: &str) -> String {
    let re = regex::Regex::new(r"\x1b\[[0-9;?]*[A-Za-z]").unwrap();
    re.replace_all(text, "").to_string()
}

fn gemini_response(output: &str) -> Result<String, String> {
    let Some(start) = output.find('{') else { return Ok(output.to_string()) };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&output[start..]) else { return Ok(output.to_string()) };
    if !v.is_object() {
        return Ok(output.to_string());
    }
    let resp = v["response"].as_str().unwrap_or("");
    if !v["error"].is_null() && resp.is_empty() {
        let e = &v["error"];
        let msg = e["message"].as_str().map(String::from).unwrap_or_else(|| e.to_string());
        return Err(format!("gemini: {msg}"));
    }
    Ok(resp.trim().to_string())
}

fn retry_settings(method: &str, cfg: &Cfg) -> (bool, u64) {
    let keys = match method {
        CLAUDE => ("tr_llm_claude_retry", "tr_llm_claude_retry_s"),
        GEMINI => ("tr_llm_gemini_retry", "tr_llm_gemini_retry_s"),
        CHATGPT => ("tr_llm_chatgpt_retry", "tr_llm_chatgpt_retry_s"),
        _ => return (false, TIMEOUT),
    };
    (cfg.b(keys.0), (cfg.f(keys.1, 60.0) as u64).max(1))
}

struct Run {
    code: i32,
    out: String,
    err: String,
}

/// Programm starten, bei Zeitüberschreitung die GANZE Prozessgruppe beenden.
fn run(argv: &[String], stdin: Option<&str>, timeout: Duration, cwd: &Path) -> Result<Option<Run>, String> {
    let mut cmd = Command::new(&argv[0]);
    // Ordner des Programms vorne in PATH: bei nvm & Co. liegt `node` direkt daneben
    // (der Dienst läuft unter systemd, dort fehlt der PATH der Shell)
    if let Some(dir) = Path::new(&argv[0]).parent() {
        let old = std::env::var_os("PATH").unwrap_or_default();
        let mut parts = vec![dir.to_path_buf()];
        parts.extend(std::env::split_paths(&old));
        if let Ok(p) = std::env::join_paths(parts) {
            cmd.env("PATH", p);
        }
    }
    cmd.args(&argv[1..])
        .current_dir(cwd)
        .env("GEMINI_CLI_TRUST_WORKSPACE", "true")
        .env("NO_COLOR", "1")
        .stdin(if stdin.is_some() { Stdio::piped() } else { Stdio::null() })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0);
    let mut child = cmd.spawn().map_err(|e| format!("Programm nicht gefunden: {} ({e})", argv[0]))?;
    if let (Some(text), Some(mut pipe)) = (stdin, child.stdin.take()) {
        let text = text.to_string();
        std::thread::spawn(move || {
            let _ = pipe.write_all(text.as_bytes());
        });
    }
    let mut out_pipe = child.stdout.take().unwrap();
    let mut err_pipe = child.stderr.take().unwrap();
    let out_t = std::thread::spawn(move || {
        let mut b = Vec::new();
        let _ = out_pipe.read_to_end(&mut b);
        b
    });
    let err_t = std::thread::spawn(move || {
        let mut b = Vec::new();
        let _ = err_pipe.read_to_end(&mut b);
        b
    });
    let start = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
            // übrig gebliebene Unterprozesse (halten sonst stdout offen → join hinge ewig)
            unsafe {
                libc::killpg(child.id() as i32, libc::SIGKILL);
            }
            let out = String::from_utf8_lossy(&out_t.join().unwrap_or_default()).to_string();
            let err = String::from_utf8_lossy(&err_t.join().unwrap_or_default()).to_string();
            return Ok(Some(Run { code: status.code().unwrap_or(-1), out, err }));
        }
        if start.elapsed() > timeout {
            unsafe {
                libc::killpg(child.id() as i32, libc::SIGKILL);
            }
            let _ = child.wait();
            return Ok(None);
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

/// Mit der KI übersetzen / erklären / antworten (Aufgabe = cfg["tr_llm_mode"]).
pub fn translate(method: &str, cfg: &Cfg, text: &str, source: &str, target: &str, image: Option<&Path>) -> Result<String, String> {
    if method == VISION {
        return vision::translate(cfg, text, source, target, image);
    }
    let mode = { let m = cfg.s("tr_llm_mode"); if m.is_empty() { MODE_TRANSLATE.to_string() } else { m } };
    let prompt = make_prompt(text, source, target, &mode, method);
    let (mut argv, stdin) = build_command(method, cfg, &prompt, text, source, target)?;
    let exe = find_binary(&argv[0]).ok_or_else(|| format!("Programm nicht gefunden: {}", argv[0]))?;
    let name = exe.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    argv[0] = exe.to_string_lossy().to_string();
    static N: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let n = N.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let tmp = std::env::temp_dir().join(format!("viewshot-llm-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
    let result = (|| {
        let last_msg = tmp.join("answer.txt");
        if method == CHATGPT {
            argv.splice(2..2, ["--output-last-message".to_string(), last_msg.to_string_lossy().to_string()]);
        }
        let (retry, secs) = retry_settings(method, cfg);
        let timeout = if retry { secs } else { TIMEOUT };
        let attempts = if retry { 1 + RETRIES } else { 1 };
        let mut res = None;
        for _ in 0..attempts {
            if let Some(r) = run(&argv, stdin.as_deref(), Duration::from_secs(timeout), &tmp)? {
                res = Some(r);
                break;
            }
        }
        let Some(res) = res else {
            let tries = if attempts > 1 { format!(" ({attempts} Versuche)") } else { String::new() };
            return Err(format!("{name} hat länger als {timeout} s gebraucht{tries}"));
        };
        if res.code != 0 {
            let err = clean(if res.err.trim().is_empty() { &res.out } else { &res.err });
            let last = err.trim().lines().last().unwrap_or("").to_string();
            return Err(format!("{name} beendet mit Fehler {}{}", res.code, if last.is_empty() { String::new() } else { format!(": {last}") }));
        }
        let mut out = String::new();
        if method == CHATGPT {
            out = std::fs::read_to_string(&last_msg).unwrap_or_default();
        }
        if out.is_empty() {
            out = res.out.clone();
        }
        let mut out = clean(&out).trim().to_string();
        if method == GEMINI {
            out = gemini_response(&out)?;
        }
        Ok(out)
    })();
    let _ = std::fs::remove_dir_all(&tmp);
    let out = result?;
    if out.is_empty() {
        return Err(format!("{name} hat nichts geantwortet"));
    }
    let low = out.to_lowercase();
    if out.len() < 300 && LOGIN_HINTS.iter().any(|h| low.contains(h)) {
        let first: String = out.lines().next().unwrap_or("").chars().take(120).collect();
        return Err(format!("{name}: nicht angemeldet – Optionen → Übersetzung → Anmelden ({first})"));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn custom_command_placeholders() {
        let mut cfg = Cfg::with_defaults(crate::settings::UI_DEFAULTS, None);
        cfg.set("tr_llm_custom_cmd", "echo {target} {prompt}");
        let (argv, stdin) = build_command(LLM_CUSTOM, &cfg, "P", "T", "", "de").unwrap();
        assert_eq!(argv, vec!["echo", "de", "P"]);
        assert!(stdin.is_none());
    }

    #[test]
    fn custom_command_runs() {
        let mut cfg = Cfg::with_defaults(crate::settings::UI_DEFAULTS, None);
        cfg.set("tr_llm_custom_cmd", "printf Hallo");
        assert_eq!(translate(LLM_CUSTOM, &cfg, "x", "", "de", None).unwrap(), "Hallo");
    }

    #[test]
    fn numbering() {
        assert_eq!(numbered_lines("A\nB"), "1) A\n2) B");
        assert_eq!(numbered_lines("A"), "A");
    }
}
