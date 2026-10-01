//! Einfaches Logging: jede Zeile geht nach stderr UND in
//! ~/.local/state/linuxvr-viewshot/layer.log
//! So siehst du auch bei Steam-Spielen, was der Layer macht.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;

/// Name der App in diesem Prozess (für das Log)
static APP: Mutex<String> = Mutex::new(String::new());

/// Name der App (aus xrCreateInstance)
pub fn app() -> String {
    APP.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

pub fn set_app(name: &str) {
    // Test-Instanzen von wineopenxr/steam sollen den echten Namen nicht überschreiben
    let mut a = APP.lock().unwrap_or_else(|e| e.into_inner());
    if a.is_empty() || !name.contains("test instance") {
        *a = name.to_string();
    }
}

pub fn log_file_path() -> Option<PathBuf> {
    let dir = dirs::state_dir()
        .or_else(|| dirs::home_dir().map(|h| h.join(".local/state")))?
        .join("linuxvr-viewshot");
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir.join("layer.log"))
}

pub fn write_line(msg: &str) {
    let app = APP.lock().map(|a| a.clone()).unwrap_or_default();
    let line = format!(
        "[{}] [ViewShot] [pid {} {}] {}",
        chrono::Local::now().format("%H:%M:%S"),
        std::process::id(),
        if app.is_empty() { "?" } else { &app },
        msg
    );
    eprintln!("{line}");
    if let Some(path) = log_file_path() {
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(f, "{line}");
        }
    }
}

/// Wie `println!`, nur ins Layer-Log.
#[macro_export]
macro_rules! log {
    ($($arg:tt)*) => { $crate::log::write_line(&format!($($arg)*)) };
}
