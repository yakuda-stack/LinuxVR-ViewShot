//! viewshot-daemon – LinuxVR-ViewShot ohne offene Desktop-App.
//!
//! Macht im Hintergrund, was sonst die App macht: neues Foto → Text lesen →
//! übersetzen (gleiche Dienste, gleicher Cache) → 🪟 Panel und 🔁 Lens in VR.
//! Ist die App offen, hält sie ~/.local/state/linuxvr-viewshot/app.lock – dann
//! wartet der Dienst nur und die App macht alles wie gewohnt.
//!
//!   viewshot-daemon            normal starten (auch per systemd-Socket)
//!   viewshot-daemon --stay     nicht von selbst beenden (von Hand gestartet)
//!   viewshot-daemon ocr BILD   nur Text lesen (Test)

mod actions;
mod app;
mod i18n;
mod imgops;
mod log;
mod ocr;
mod overlay;
mod panel;
mod paths;
mod render;
mod settings;
mod tr;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("ocr") => {
            let Some(path) = args.get(2) else {
                eprintln!("viewshot-daemon ocr BILD");
                std::process::exit(2);
            };
            let t = std::time::Instant::now();
            let mut engine = match ocr::Engine::load() {
                Ok(e) => e,
                Err(e) => {
                    eprintln!("{e}");
                    std::process::exit(1);
                }
            };
            let loaded = t.elapsed();
            match engine.read(std::path::Path::new(path)) {
                Ok(lines) => {
                    eprintln!("geladen {loaded:?}, gelesen {:?}", t.elapsed() - loaded);
                    println!("{}", serde_json::to_string(&lines).unwrap_or_default());
                }
                Err(e) => {
                    eprintln!("{e}");
                    std::process::exit(1);
                }
            }
        }
        Some("--version") => println!("viewshot-daemon {}", env!("CARGO_PKG_VERSION")),
        Some("--stay") => app::run(true),
        None => app::run(false),
        Some(other) => {
            eprintln!("unbekannt: {other}\n  viewshot-daemon [--stay]   ·   viewshot-daemon ocr BILD");
            std::process::exit(2);
        }
    }
}
