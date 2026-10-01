//! Der Dienst selbst: schaut nach neuen Fotos und Lens-Bildern, lässt sie im
//! Hintergrund-Thread lesen + übersetzen und zeichnet das 🪟 VR-Panel.
//!
//! Solange die Desktop-App offen ist (sie hält app.lock), wartet er nur –
//! dann macht die App alles wie gewohnt. Ohne Nachricht vom Layer („hello“)
//! beendet er sich nach IDLE_EXIT (systemd startet ihn beim nächsten Spiel neu).

use crate::i18n::{language_name, tr};
use crate::ocr::{Engine, Line};
use crate::panel::{self, Action, Choice, GRow, GalleryView, OpenPhoto, Page, Pics, Sub, Tile, View};
use crate::render::Fonts;
use crate::settings::{self, Cfg};
use crate::tr::{self as trn, llm, METHODS};
use crate::{actions, log, overlay, paths};
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::net::UdpSocket;
use std::os::fd::FromRawFd;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{channel, Receiver, Sender};
use std::time::{Duration, Instant, SystemTime};

pub const CONTROL_PORT: u16 = 47932;
const IDLE_EXIT: Duration = Duration::from_secs(120);
const BYE_EXIT: Duration = Duration::from_secs(15);
const TICK: Duration = Duration::from_millis(50);
const CHECK: Duration = Duration::from_millis(500);
const STALE_MIN_S: f64 = 10.0;
/// ⚙ Einstellungen gleiten in so vielen Bildern herein, je SLIDE_MS (der Layer schaut alle 80 ms)
const SLIDE_STEPS: usize = 4;
const SLIDE_MS: Duration = Duration::from_millis(80);

enum Job {
    /// Foto lesen + übersetzen. translate=false: nur Cache zeigen (tr_auto aus)
    Photo { id: u64, path: PathBuf, cfg: Cfg, translate: bool, force: bool },
    Live { id: u64, path: PathBuf, cfg: Cfg, last_text: String, last: Option<(String, String, String)> },
}

enum Msg {
    Progress { id: u64, step: String, arg: String },
    Photo { id: u64, path: PathBuf, res: Result<trn::PhotoResult, String> },
    Live { size: (u32, u32), lines: Vec<Line>, text: String, res: Result<Option<(String, String, String)>, String> },
    /// ☁ Hochladen fertig: (Bild-Link, Lösch-Link) oder Fehler
    Upload { path: PathBuf, res: Result<(String, String), String> },
}

/// Arbeiter: Texterkennung (Modell bleibt geladen) + Übersetzen.
/// Stürzt ein Auftrag ab (z. B. onnxruntime zu alt), kommt ein Fehler zurück – der Arbeiter läuft weiter.
fn worker(jobs: Receiver<Job>, out: Sender<Msg>) {
    let engine: std::cell::RefCell<Option<Engine>> = std::cell::RefCell::new(None);
    loop {
        // 1 Minute nichts zu tun → Modell aus dem Speicher (VR braucht den RAM), kommt in 0,3 s wieder
        let job = match jobs.recv_timeout(Duration::from_secs(60)) {
            Ok(j) => j,
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                if engine.borrow_mut().take().is_some() {
                    log::line("OCR: Modell entladen (nichts zu tun)");
                }
                continue;
            }
            Err(_) => return,
        };
        let (id, live, path) = match &job {
            Job::Photo { id, path, .. } => (*id, false, path.clone()),
            Job::Live { id, path, .. } => (*id, true, path.clone()),
        };
        let done = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handle(job, &engine, &out)));
        if let Err(p) = done {
            let why = p
                .downcast_ref::<String>()
                .cloned()
                .or_else(|| p.downcast_ref::<&str>().map(|s| s.to_string()))
                .unwrap_or_else(|| "unbekannter Fehler".into());
            log::line(&format!("Auftrag abgestürzt: {why}"));
            *engine.borrow_mut() = None;
            let res = Err(format!("interner Fehler: {why}"));
            let _ = out.send(if live {
                Msg::Live { size: (0, 0), lines: Vec::new(), text: String::new(), res }
            } else {
                Msg::Photo { id, path, res: Err(format!("interner Fehler: {why}")) }
            });
        }
    }
}

fn handle(job: Job, engine: &std::cell::RefCell<Option<Engine>>, out: &Sender<Msg>) {
    let ocr = |path: &Path| -> Result<Vec<Line>, String> {
        let mut engine = engine.borrow_mut();
        if engine.is_none() {
            let t = Instant::now();
            *engine = Some(Engine::load()?);
            log::line(&format!("OCR: Modell geladen in {:.1} s", t.elapsed().as_secs_f32()));
        }
        let t = Instant::now();
        let lines = engine.as_mut().unwrap().read(path)?;
        log::line(&format!(
            "OCR {}: {:.1} s, {} Zeilen",
            path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default(),
            t.elapsed().as_secs_f32(),
            lines.len()
        ));
        Ok(lines)
    };
    match job {
        Job::Photo { id, path, cfg, translate, force } => {
            let tx = out.clone();
            let progress = move |step: &str, arg: &str| {
                let _ = tx.send(Msg::Progress { id, step: step.into(), arg: arg.into() });
            };
            let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
            let res = if translate {
                trn::translate_photo(&path, &cfg, force, &mut |p: &Path| ocr(p), &progress)
            } else {
                // nur anzeigen, was schon übersetzt ist
                let e = trn::entry(&name).unwrap_or_default();
                let who = trn::last_ai(&name, &cfg).unwrap_or_default();
                Ok(trn::PhotoResult {
                    ocr: e.get("ocr").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                    lines: trn::cached_lines(&name),
                    translated: e.get("tr").and_then(|t| t.get(trn::key(&cfg))).and_then(|v| v.as_str()).unwrap_or("").to_string(),
                    method: who.0,
                    task: who.1,
                    cached: true,
                    errors: Vec::new(),
                })
            };
            let _ = out.send(Msg::Photo { id, path, res });
        }
        Job::Live { id, path, cfg, last_text, last } => {
            let tx = out.clone();
            let progress = move |step: &str, arg: &str| {
                let _ = tx.send(Msg::Progress { id, step: step.into(), arg: arg.into() });
            };
            let size = image::image_dimensions(&path).unwrap_or((0, 0));
            let lines = match ocr(&path) {
                Ok(l) => l,
                Err(e) => {
                    let _ = out.send(Msg::Live { size, lines: Vec::new(), text: String::new(), res: Err(e) });
                    return;
                }
            };
            let text = lines.iter().map(|l| l.text.as_str()).collect::<Vec<_>>().join("\n");
            let res = if text.is_empty() && cfg.s("tr_method") != llm::VISION {
                Ok(None)
            } else if !text.is_empty() && text == last_text && last.is_some() {
                Ok(last)
            } else {
                let mut errors = Vec::new();
                match trn::translate_text_used(&text, &cfg, &mut errors, &progress, Some(&path)) {
                    Some(d) => Ok(Some((d.text, d.method, d.task))),
                    None => Err(errors.join("; ")),
                }
            };
            let _ = out.send(Msg::Live { size, lines, text, res });
        }
    }
}

fn file_mtime(p: &Path) -> Option<SystemTime> {
    std::fs::metadata(p).ok()?.modified().ok()
}

/// Hält die App app.lock? (flock – verschwindet automatisch, wenn die App endet)
pub fn app_running() -> bool {
    use std::os::fd::AsRawFd;
    let Ok(f) = std::fs::OpenOptions::new().read(true).write(true).create(true).truncate(false).open(paths::app_lock_file()) else {
        return false;
    };
    let fd = f.as_raw_fd();
    unsafe {
        if libc::flock(fd, libc::LOCK_EX | libc::LOCK_NB) == 0 {
            libc::flock(fd, libc::LOCK_UN);
            false
        } else {
            true
        }
    }
}

/// Steuer-Socket: von systemd übergeben (Socket-Aktivierung) oder selbst öffnen
fn control_socket() -> Option<UdpSocket> {
    let pid_ok = std::env::var("LISTEN_PID").ok().and_then(|p| p.parse::<u32>().ok()) == Some(std::process::id());
    let fds = std::env::var("LISTEN_FDS").ok().and_then(|n| n.parse::<i32>().ok()).unwrap_or(0);
    let sock = if pid_ok && fds >= 1 {
        eprintln!("Gestartet von systemd (Socket-Aktivierung)");
        // nicht an claude & Co. weitervererben
        unsafe {
            libc::fcntl(3, libc::F_SETFD, libc::FD_CLOEXEC);
        }
        std::env::remove_var("LISTEN_FDS");
        std::env::remove_var("LISTEN_PID");
        std::env::remove_var("LISTEN_FDNAMES");
        unsafe { UdpSocket::from_raw_fd(3) }
    } else {
        match UdpSocket::bind(("127.0.0.1", CONTROL_PORT)) {
            Ok(s) => s,
            Err(e) => {
                eprintln!("Port {CONTROL_PORT} belegt – läuft der Dienst schon? ({e})");
                return None;
            }
        }
    };
    sock.set_nonblocking(true).ok()?;
    Some(sock)
}

/// (Foto, Änderungszeit, Zeilen) → verkleinertes Bild mit Nummern
type PhotoCache = ((PathBuf, Option<SystemTime>, Vec<Line>), Option<image::RgbaImage>);
/// (Foto, Änderungszeit) → Foto in der Galerie-Einzelansicht (verkleinert)
type BigCache = Option<((PathBuf, Option<SystemTime>), Option<image::RgbaImage>)>;

struct State {
    fonts: Fonts,
    cfg: Cfg,
    lcfg: Cfg,
    cfg_mtime: Option<SystemTime>,
    lcfg_mtime: Option<SystemTime>,
    photo: Option<PathBuf>,
    lines: Vec<Line>,
    ocr_text: String,
    result: String,
    status: String,
    last_ai: String,
    busy: Option<u64>,
    auto_task: String,
    live_shown: bool,
    live_busy: bool,
    live_mtime: Option<SystemTime>,
    live_text: String,
    live_result: Option<(String, String, String)>,
    live_lines: Vec<Line>,
    choosing: Option<Choice>,
    hits: panel::Hits,
    panel_size: (u32, u32),
    last_view: Option<View>,
    photo_cache: Option<PhotoCache>,
    sheet_open: bool,
    /// Hauptseite im Panel: Übersetzung / Galerie (◀ ▶ am Rand)
    page: Page,
    gal_page: usize,
    /// Galerie: Foto in der Einzelansicht
    gal_open: Option<PathBuf>,
    /// 🗑 einmal angetippt → „Wirklich löschen?“
    gal_confirm: bool,
    /// Galerie-Bilder aus allen Ordnern, neueste zuerst – Klicks beziehen sich darauf
    gal_list: Vec<paths::GalleryPhoto>,
    /// wann die Ordner zuletzt durchsucht wurden (höchstens alle 2 s)
    gal_scan: Option<Instant>,
    /// Raster-Seiten (Monats-Trenner + Zeilen), passend zu gal_list
    gal_pages: Vec<Vec<GRow>>,
    /// Rückmeldung in der Einzelansicht („✔ Link kopiert“)
    gal_toast: String,
    /// ↗ Teilen / ⓘ Info offen
    gal_sub: Option<Sub>,
    uploading: HashSet<PathBuf>,
    /// in der VR-Galerie gewähltes Foto (gilt, bis ein neues Foto gemacht wird)
    chosen: Option<PathBuf>,
    newest_mtime: Option<SystemTime>,
    thumbs: HashMap<(PathBuf, Option<SystemTime>), Option<image::RgbaImage>>,
    big_cache: BigCache,
    result_page: usize,
    pages: usize,
    paged_result: String,
    slide: Vec<crate::render::Canvas>,
    slide_next: Instant,
    pose_mtime: Option<SystemTime>,
    next_id: u64,
    jobs: Sender<Job>,
    msgs: Sender<Msg>,
}

impl State {
    /// Auftrag an den Arbeiter – ist der weg (sollte nie passieren), einen neuen starten
    fn send(&mut self, job: Job) {
        if let Err(std::sync::mpsc::SendError(job)) = self.jobs.send(job) {
            log::line("Arbeiter neu gestartet");
            let (tx, rx) = channel();
            let out = self.msgs.clone();
            std::thread::spawn(move || worker(rx, out));
            self.jobs = tx;
            let _ = self.jobs.send(job);
        }
    }

    fn lang(&self) -> String {
        let l = self.cfg.s("language");
        if l.is_empty() { "de".into() } else { l }
    }

    fn t(&self, key: &str, args: &[(&str, &str)]) -> String {
        tr(&self.lang(), key, args)
    }

    fn method_name(&self, m: &str) -> String {
        self.t(&format!("tr_m_{m}"), &[])
    }

    fn reload(&mut self, force: bool) -> bool {
        let (m, lm) = (file_mtime(&settings::ui_file()), file_mtime(&settings::layer_file()));
        let changed = force || m != self.cfg_mtime || lm != self.lcfg_mtime;
        if force || m != self.cfg_mtime {
            self.cfg = settings::load_ui();
            self.cfg_mtime = m;
        }
        if force || lm != self.lcfg_mtime {
            self.lcfg = settings::load_layer();
            self.lcfg_mtime = lm;
        }
        changed
    }

    fn save_cfg(&mut self, keys: &[&str]) {
        let changes: Vec<(&str, Value)> = keys.iter().map(|k| (*k, self.cfg.0.get(*k).cloned().unwrap_or(Value::Null))).collect();
        if let Err(e) = settings::update_file(&settings::ui_file(), &changes) {
            log::line(&format!("ui.json: {e}"));
        }
        self.cfg_mtime = file_mtime(&settings::ui_file());
    }

    fn photo_cfg(&mut self, photo: &Path) -> Cfg {
        let name = photo.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        let (c, changed) = trn::photo_task_cfg(&mut self.cfg, &name);
        if changed {
            self.save_cfg(&["tr_auto_once", "tr_auto_once_photo", "tr_auto_once_next"]);
        }
        c
    }

    fn start_photo(&mut self, force: bool, translate: bool) {
        let Some(path) = self.photo.clone() else { return };
        let cfg = self.photo_cfg(&path);
        self.next_id += 1;
        self.busy = Some(self.next_id);
        self.result.clear();
        self.lines = trn::cached_lines(&path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default());
        self.status = if translate { format!("⏳  {}", self.t("translating", &[])) } else { String::new() };
        self.send(Job::Photo { id: self.next_id, path, cfg, translate, force });
    }

    /// Neuestes Foto geändert? → anzeigen + (bei tr_auto) übersetzen.
    /// Ein in der VR-Galerie gewähltes Foto bleibt, bis ein neues gemacht wird.
    fn check_photo(&mut self) {
        let newest = paths::newest_photo();
        let newest_m = newest.as_deref().and_then(file_mtime);
        if newest_m > self.newest_mtime {
            self.chosen = None; // neues Foto → wieder das neueste zeigen
        }
        self.newest_mtime = newest_m;
        if self.chosen.as_ref().is_some_and(|c| !c.is_file()) {
            self.chosen = None; // gelöscht
        }
        let Some(target) = self.chosen.clone().or(newest) else { return };
        if Some(&target) == self.photo.as_ref() || !paths::photo_ready(&target) {
            return;
        }
        self.photo = Some(target);
        self.auto_task.clear();
        let auto = self.cfg.b("tr_auto");
        self.start_photo(false, auto);
    }

    fn check_live(&mut self) {
        let live = paths::live_file();
        let mtime = file_mtime(&live);
        if self.live_shown && !self.live_busy {
            let interval = self.lcfg.f("live_interval_s", 3.0).max(1.0);
            let age = mtime.and_then(|m| m.elapsed().ok()).map(|d| d.as_secs_f64()).unwrap_or(f64::MAX);
            if mtime.is_none() || age > (3.0 * interval).max(STALE_MIN_S) {
                // Lens beendet → wieder das normale Foto
                self.live_shown = false;
                self.live_text.clear();
                self.live_result = None;
                self.live_lines.clear();
                self.status.clear();
                if self.photo.is_some() {
                    self.start_photo(false, false);
                }
                return;
            }
        }
        if self.live_busy || self.busy.is_some() {
            return;
        }
        let Some(m) = mtime else { return };
        if self.live_mtime.is_some_and(|old| m <= old) {
            return;
        }
        self.live_mtime = Some(m);
        self.live_shown = true;
        self.live_busy = true;
        self.next_id += 1;
        let cfg = trn::task_cfg(&self.cfg);
        self.send(Job::Live {
            id: self.next_id,
            path: live,
            cfg,
            last_text: self.live_text.clone(),
            last: self.live_result.clone(),
        });
    }

    fn short(&self, s: &str) -> String {
        let s = s.split(" (").next().unwrap_or(s);
        ["KI: ", "AI: ", "IA : "].iter().find_map(|p| s.strip_prefix(p)).unwrap_or(s).to_string()
    }

    /// „Letzte KI: Claude Code (sonnet) · ❓ Frage beantworten“
    fn set_last_ai(&mut self, method: &str, task: &str) {
        if method.is_empty() {
            return;
        }
        let mut text = self.short(&self.method_name(method));
        let model = llm::model_of(method, &self.cfg);
        if !model.is_empty() {
            text.push_str(&format!(" ({model})"));
        }
        if !task.is_empty() && task != llm::MODE_TRANSLATE {
            text.push_str(&format!("  ·  {}", self.short(&self.t(&format!("tr_mode_{task}"), &[]))));
        }
        self.last_ai = text;
    }

    fn planned(&self) -> Vec<String> {
        let mut p = vec![self.cfg.s("tr_method")];
        p.extend(llm::TASK_KEYS.iter().map(|(m, _)| trn::task_method(&self.cfg, m)));
        p
    }

    fn on_msg(&mut self, msg: Msg) {
        match msg {
            Msg::Progress { id, step, arg } => {
                if Some(id) != self.busy && !self.live_busy {
                    return;
                }
                let text = match step.as_str() {
                    "ocr" => self.t("tr_step_ocr", &[]),
                    "service" => self.t("tr_step_service", &[("name", &self.method_name(&arg))]),
                    "classify" => self.t("tr_step_classify", &[("name", &self.method_name(&arg))]),
                    "auto" => {
                        self.auto_task = arg.clone();
                        format!("🤖 → {}", self.t(&format!("tr_mode_{arg}"), &[]))
                    }
                    _ => return,
                };
                if !self.live_shown {
                    self.status = format!("⏳  {text}");
                }
            }
            Msg::Photo { id, path, res } => {
                if Some(id) != self.busy {
                    return;
                }
                self.busy = None;
                if Some(&path) != self.photo.as_ref() {
                    return;
                }
                match res {
                    Err(e) => self.status = format!("{}: {e}", self.t("tr_failed", &[])),
                    Ok(r) => {
                        self.lines = r.lines.clone();
                        self.ocr_text = r.ocr.clone();
                        self.result = r.translated.clone();
                        self.status = if r.ocr.is_empty() && r.translated.is_empty() && r.cached {
                            String::new()
                        } else if r.ocr.is_empty() && r.translated.is_empty() {
                            self.t("no_text", &[])
                        } else {
                            String::new()
                        };
                        if !r.translated.is_empty() {
                            self.set_last_ai(&r.method, &r.task);
                            let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                            trn::add_history(&self.cfg, &name, &r.ocr, &r.translated, &r.method);
                            let main = self.cfg.s("tr_method");
                            if trn::route_mode(&self.cfg) == trn::ROUTE_AUTO && !self.auto_task.is_empty() {
                                self.status = format!(
                                    "🤖 → {} · {}",
                                    self.t(&format!("tr_mode_{}", self.auto_task), &[]),
                                    self.method_name(&r.method)
                                );
                            } else if r.method != main && !r.method.is_empty() {
                                self.status = format!("{} · {}", self.t(&format!("tr_mode_{}", r.task), &[]), self.method_name(&r.method));
                            }
                            if !r.method.is_empty() && !self.planned().contains(&r.method) {
                                self.status = self.t(
                                    "tr_fallback_once",
                                    &[("failed", &self.method_name(&main)), ("used", &self.method_name(&r.method)), ("error", &r.errors.join("; "))],
                                );
                            }
                        }
                    }
                }
                self.auto_task.clear();
            }
            Msg::Upload { path, res } => {
                self.uploading.remove(&path);
                let toast = match res {
                    Ok((view, _)) => {
                        actions::copy_text(&view);
                        self.t("vr_link_copied", &[])
                    }
                    Err(e) => format!("{}: {e}", self.t("vr_upload_failed", &[])),
                };
                if self.gal_open.as_ref() == Some(&path) {
                    self.gal_toast = toast;
                }
            }
            Msg::Live { size, lines, text, res } => {
                self.live_busy = false;
                if !self.live_shown {
                    return;
                }
                let now = chrono::Local::now().format("%H:%M:%S").to_string();
                let lens = self.t("live_status", &[]);
                match res {
                    Err(e) => self.status = format!("🔁  {}: {e}", self.t("tr_failed", &[])),
                    Ok(None) => {
                        self.live_lines = lines;
                        self.result.clear();
                        self.status = format!("🔁  {lens} · {now} · {}", self.t("no_text", &[]));
                    }
                    Ok(Some((translated, method, task))) => {
                        if Some((translated.clone(), method.clone(), task.clone())) != self.live_result || text != self.live_text {
                            self.set_last_ai(&method, &task);
                        }
                        self.live_text = text;
                        self.live_result = Some((translated.clone(), method, task));
                        self.result = translated.clone();
                        self.status = format!("🔁  {lens} · {now}");
                        if self.lcfg.b("overlay") && size.0 > 0 {
                            overlay::write_live(&mut self.fonts, size, &lines, &translated);
                        }
                        self.live_lines = lines;
                    }
                }
                self.auto_task.clear();
            }
        }
    }

    fn mode_items(&self) -> panel::Items {
        let auto = trn::route_mode(&self.cfg) == trn::ROUTE_AUTO;
        let mut items = Vec::new();
        if auto {
            let once = self.cfg.s("tr_auto_once");
            items.push((String::new(), self.t("tr_mode_auto", &[]), once.is_empty()));
            for m in llm::MODES {
                items.push((m.to_string(), format!("{}  · 1×", self.t(&format!("tr_mode_{m}"), &[])), once == m));
            }
        } else {
            let cur = trn::task_cfg(&self.cfg).s("tr_llm_mode");
            for m in llm::MODES {
                items.push((m.to_string(), self.t(&format!("tr_mode_{m}"), &[]), cur == m));
            }
        }
        items
    }

    fn mode_label(&self) -> Option<String> {
        if !trn::has_tasks(&self.cfg) {
            return None;
        }
        self.mode_items().into_iter().find(|i| i.2).map(|i| i.1)
    }

    /// Dienste fürs Menü: eingerichtete, bei ⭐ Favoriten nur diese (+ der gewählte)
    fn menu_methods(&self) -> Vec<String> {
        let cur = self.cfg.s("tr_method");
        let methods: Vec<String> =
            METHODS.iter().filter(|m| **m == cur || trn::is_configured(m, &self.cfg)).map(|m| m.to_string()).collect();
        let favs: Vec<String> = self.cfg.0.get("tr_favorites").and_then(|v| serde_json::from_value(v.clone()).ok()).unwrap_or_default();
        if !methods.iter().any(|m| favs.contains(m)) {
            return methods;
        }
        methods.into_iter().filter(|m| favs.contains(m) || *m == cur).collect()
    }

    fn choice_items(&self, c: Choice) -> (String, panel::Items) {
        let lang = self.lang();
        match c {
            Choice::Method => {
                // gegliedert wie in der App: ── Übersetzung ── / ── KI-Übersetzung ──
                let cur = self.cfg.s("tr_method");
                let methods = self.menu_methods();
                let mut items = Vec::new();
                for (title, ai) in [("tr_group_plain", false), ("tr_group_ai", true)] {
                    let group: Vec<&String> = methods.iter().filter(|m| llm::is_llm(m) == ai).collect();
                    if group.is_empty() {
                        continue;
                    }
                    items.push((panel::HEADER.to_string(), self.t(title, &[]), false));
                    items.extend(group.into_iter().map(|m| (m.clone(), self.method_name(m), *m == cur)));
                }
                (self.t("tr_service", &[]), items)
            }
            Choice::Source | Choice::Target => {
                let (key, title, src) = if c == Choice::Source { ("tr_source", "tr_source", true) } else { ("tr_target", "tr_target", false) };
                let cur = self.cfg.s(key);
                let items = crate::i18n::languages()
                    .into_iter()
                    .enumerate()
                    .filter(|(i, _)| src || *i > 0)
                    .map(|(_, (code, de, en))| {
                        let chosen = code == cur;
                        (code, if lang == "de" { de } else { en }, chosen)
                    })
                    .collect();
                (self.t(title, &[]), items)
            }
            Choice::Mode => (self.t("tr_task", &[]), self.mode_items()),
        }
    }

    fn view(&self) -> View {
        let lang = self.lang();
        let (photo, lines) = if self.live_shown {
            (Some(paths::live_file()), self.live_lines.clone())
        } else {
            (self.photo.clone(), self.lines.clone())
        };
        let prefix = if self.live_shown && !self.status.starts_with('🔁') {
            format!("🔁 {} · ", self.t("live_title", &[]))
        } else {
            String::new()
        };
        View {
            lang: lang.clone(),
            method_label: self.method_name(&self.cfg.s("tr_method")),
            source_label: language_name(&lang, &self.cfg.s("tr_source"), true),
            target_label: language_name(&lang, &self.cfg.s("tr_target"), false),
            mode_label: self.mode_label(),
            last_ai: if self.last_ai.is_empty() { "–".into() } else { self.last_ai.clone() },
            edit: self.lcfg.b("panel_edit"),
            opacity: self.lcfg.f("panel_opacity", 100.0).round() as i32,
            photo_mtime: photo.as_ref().and_then(|p| file_mtime(p)),
            photo,
            lines,
            result: self.result.clone(),
            status: format!("{prefix}{}", self.status),
            choosing: self.choosing.map(|c| {
                let (title, items) = self.choice_items(c);
                (c, title, items)
            }),
            route: (self.choosing == Some(Choice::Method) && llm::is_llm(&self.cfg.s("tr_method")))
                .then(|| trn::route_mode(&self.cfg).to_string()),
            sheet: self.sheet_open.then(|| panel::Sheet {
                width_cm: panel::width_cm(),
                anchor: self.lcfg.s("panel_anchor"),
                detect: self.lcfg.s("detect_mode"),
                shutter: self.lcfg.s("shutter"),
                mode_button: self.lcfg.s("mode_button"),
                button: self.lcfg.b("panel_button"),
                open_on_shot: self.lcfg.b("panel_open_on_shot"),
                button_cm: panel::button_cm(),
                color: self.lcfg.s("panel_button_color"),
                page_name: self.t(if self.page == Page::Gallery { "nav_gallery" } else { "vr_page_translate" }, &[]),
            }),
            result_page: self.result_page,
            fixed_height: panel::fixed_height(),
            page: self.page,
            gallery: (self.page == Page::Gallery).then(|| self.gallery_view()),
        }
    }

    /// Position eines Fotos in der Galerie-Liste
    fn gal_index(&self, p: &Path) -> Option<usize> {
        self.gal_list.iter().position(|x| x.path == p)
    }

    /// Ordner neu durchsuchen (höchstens alle 2 s, sofort mit `fresh`) + Raster-Seiten bauen
    fn scan_gallery(&mut self, fresh: bool) {
        if !fresh && self.gal_scan.is_some_and(|t| t.elapsed() < Duration::from_secs(2)) {
            return;
        }
        self.gal_scan = Some(Instant::now());
        self.gal_list = paths::gallery_photos(&self.cfg);
        let months: Vec<(i32, u32)> = self.gal_list.iter().map(|p| p.month).collect();
        let lang = self.lang();
        let titles = |y: i32, m: u32| format!("{y} {}", tr(&lang, &format!("month_{m}"), &[]));
        self.gal_pages = panel::gallery_pages(&months, titles, panel::grid_room(panel::fixed_height()));
        self.gal_page = self.gal_page.min(self.gal_pages.len().saturating_sub(1));
        if self.gal_open.as_ref().is_some_and(|p| self.gal_index(p).is_none()) {
            self.gal_open = None; // inzwischen gelöscht → zurück ins Raster
            self.gal_sub = None;
        }
    }

    /// Raster-Seite, auf der dieses Foto steht
    fn page_of(&self, index: usize) -> usize {
        self.gal_pages
            .iter()
            .position(|pg| pg.iter().any(|r| matches!(r, GRow::Tiles(t) if t.contains(&index))))
            .unwrap_or(self.gal_page)
    }

    /// Galerie: Zeilen dieser Raster-Seite + ggf. das große Foto
    fn gallery_view(&self) -> GalleryView {
        let total = self.gal_list.len();
        let pages = self.gal_pages.len().max(1);
        let page = self.gal_page.min(pages - 1);
        let rows = self.gal_pages.get(page).cloned().unwrap_or_default();
        let tiles = rows
            .iter()
            .flat_map(|r| match r {
                GRow::Tiles(t) => t.clone(),
                GRow::Month(_) => Vec::new(),
            })
            .filter_map(|i| self.gal_list.get(i).map(|p| Tile { index: i, path: p.path.clone(), mtime: Some(p.mtime) }))
            .collect();
        let open = self.gal_open.as_ref().and_then(|p| {
            let index = self.gal_index(p)?;
            let (y, m) = self.gal_list[index].month;
            Some(OpenPhoto {
                index,
                path: p.clone(),
                mtime: Some(self.gal_list[index].mtime),
                confirm: self.gal_confirm,
                month: format!("{y} {}", self.t(&format!("month_{m}"), &[])),
                toast: self.gal_toast.clone(),
                uploading: self.uploading.contains(p),
                uploaded: actions::saved_links(p).is_some(),
                sub: self.gal_sub.clone(),
            })
        });
        GalleryView { total, page, pages, rows, tiles, open }
    }

    /// ⓘ Info-Zeilen: Ordner, Datum, Größe, Typ, Link
    fn info_rows(&self, p: &Path) -> Vec<(String, String)> {
        let when = file_mtime(p)
            .map(|m| chrono::DateTime::<chrono::Local>::from(m).format("%d.%m.%Y  %H:%M").to_string())
            .unwrap_or_default();
        let (w, h) = image::image_dimensions(p).unwrap_or((0, 0));
        let mb = std::fs::metadata(p).map(|m| m.len() as f64 / 1024.0 / 1024.0).unwrap_or(0.0);
        let icons = [("text", "📝"), ("qr", "🔳"), ("image", "🖼")];
        let kind: Vec<String> = actions::photo_tags(p)
            .iter()
            .map(|t| format!("{} {}", icons.iter().find(|i| i.0 == t).map(|i| i.1).unwrap_or(""), self.t(&format!("tag_{t}"), &[])))
            .collect();
        vec![
            (self.t("vr_info_folder", &[]), p.parent().map(|d| d.display().to_string()).unwrap_or_default()),
            (self.t("vr_info_date", &[]), when),
            (self.t("vr_info_size", &[]), format!("{w} × {h} px   ·   {mb:.1} MB")),
            (self.t("vr_info_type", &[]), if kind.is_empty() { "–".into() } else { kind.join("  ") }),
            (self.t("vr_info_link", &[]), actions::saved_links(p).map(|l| l.0).unwrap_or_else(|| "–".into())),
        ]
    }

    /// ◀ ▶: andere Seite – mit ihrer eigenen Größe in VR
    fn switch_page(&mut self, new: Page) {
        let old = self.page;
        self.page = new;
        self.gal_open = None;
        self.gal_confirm = false;
        self.gal_sub = None;
        self.gal_toast.clear();
        panel::switch_page_size(old, new);
        if new == Page::Gallery {
            self.scan_gallery(true);
        }
    }

    /// Kacheln / großes Foto verkleinern – nur was noch fehlt (teuer, wird gemerkt)
    fn prepare_gallery_images(&mut self, v: &View) {
        let Some(g) = &v.gallery else { return };
        let (tw, th) = panel::tile_size();
        if self.thumbs.len() > 80 {
            self.thumbs.clear();
        }
        for t in &g.tiles {
            self.thumbs.entry((t.path.clone(), t.mtime)).or_insert_with(|| panel::thumb(&t.path, tw - 4, th - 4));
        }
        if let Some(o) = &g.open {
            let key = (o.path.clone(), o.mtime);
            if self.big_cache.as_ref().map(|c| &c.0) != Some(&key) {
                let (w, h) = panel::single_size();
                self.big_cache = Some((key, panel::fit_photo(&o.path, w, h)));
            }
        }
    }

    fn redraw(&mut self, force: bool) {
        if !self.lcfg.b("panel") {
            let _ = std::fs::remove_file(paths::panel_file());
            self.last_view = None;
            return;
        }
        if !self.slide.is_empty() {
            return; // ⚙ klappt gerade auf/zu
        }
        if self.result != self.paged_result {
            self.paged_result = self.result.clone(); // neue Übersetzung → erste Seite
            self.result_page = 0;
        }
        if self.page == Page::Gallery {
            self.scan_gallery(false);
        }
        let v = self.view();
        let pose = file_mtime(&paths::panel_pose_file());
        if !force && self.last_view.as_ref() == Some(&v) && pose == self.pose_mtime {
            return;
        }
        self.pose_mtime = pose;
        // verkleinertes Foto mit Nummern nur neu machen, wenn sich Foto/Zeilen geändert haben
        let key = v.photo.as_ref().map(|p| (p.clone(), v.photo_mtime, v.lines.clone()));
        if self.photo_cache.as_ref().map(|c| &c.0) != key.as_ref() {
            let img = v.photo.as_ref().and_then(|p| panel::photo_with_numbers(&mut self.fonts, p, &v.lines, panel::content_w()));
            self.photo_cache = key.map(|k| (k, img));
        }
        if let Some(canvas) = self.render_view(&v) {
            if let Err(e) = canvas.save(&paths::panel_file(), &[]) {
                log::line(&format!("Panel: {e}"));
            }
        }
        self.last_view = Some(v);
    }

    fn render_view(&mut self, v: &View) -> Option<crate::render::Canvas> {
        self.prepare_gallery_images(v);
        let pics = Pics {
            photo: self.photo_cache.as_ref().and_then(|c| c.1.as_ref()),
            thumbs: v
                .gallery
                .iter()
                .flat_map(|g| g.tiles.iter())
                .map(|t| self.thumbs.get(&(t.path.clone(), t.mtime)).and_then(|i| i.as_ref()))
                .collect(),
            big: v
                .gallery
                .as_ref()
                .and_then(|g| g.open.as_ref())
                .and_then(|o| self.big_cache.as_ref().filter(|c| c.0 == (o.path.clone(), o.mtime)))
                .and_then(|c| c.1.as_ref()),
        };
        let (canvas, hits, pages) = panel::render(&mut self.fonts, v, &pics)?;
        self.panel_size = (canvas.pix.width(), canvas.pix.height());
        self.hits = hits;
        self.pages = pages;
        if self.result_page >= pages {
            self.result_page = pages.saturating_sub(1);
        }
        Some(canvas)
    }

    /// ⚙ Einstellungen gleiten wie beim Handy von oben herein (bzw. wieder hoch)
    fn toggle_sheet(&mut self) {
        let opening = !self.sheet_open;
        let v = self.view();
        let Some(before) = self.render_view(&v) else { return };
        self.sheet_open = opening;
        self.choosing = None;
        let v = self.view();
        let Some(after) = self.render_view(&v) else { return };
        let (sheet, base) = if opening { (&after, &before) } else { (&before, &after) };
        let (w, h) = (after.pix.width(), after.pix.height());
        let mut frames = Vec::new();
        for k in 1..SLIDE_STEPS {
            let t = k as f32 / SLIDE_STEPS as f32;
            let shown = if opening { t } else { 1.0 - t };
            let Some(mut frame) = crate::render::Canvas::new(w, h) else { continue };
            frame.pix.fill(crate::render::rgba(panel::BG, 255));
            frame.draw(base, 0, 0);
            frame.draw(sheet, 0, (-(1.0 - shown) * sheet.pix.height() as f32).round() as i32);
            frames.push(frame);
        }
        frames.push(after);
        self.slide = frames;
        self.slide_next = Instant::now();
        self.last_view = Some(v);
        self.next_slide();
    }

    fn next_slide(&mut self) {
        if self.slide.is_empty() {
            return;
        }
        let frame = self.slide.remove(0);
        let _ = frame.save(&paths::panel_file(), &[]);
        self.slide_next = Instant::now();
    }

    fn click(&mut self, u: f32, v: f32) {
        if !self.slide.is_empty() {
            return; // ⚙ klappt gerade auf/zu
        }
        let Some((action, frac)) = panel::hit(&self.hits, self.panel_size, u, v) else {
            log::line(&format!("Klick {u:.3} {v:.3} trifft nichts ({} Flächen, {:?})", self.hits.len(), self.panel_size));
            return;
        };
        let layer = |changes: &[(&str, Value)]| {
            let _ = settings::update_file(&settings::layer_file(), changes);
        };
        match action {
            Action::Sheet => {
                self.toggle_sheet();
                return;
            }
            Action::Move => layer(&[("panel_edit", Value::Bool(!self.lcfg.b("panel_edit")))]),
            Action::Reset => {
                // Knopf zurück an den Standard-Platz, Panel wieder darüber (legt der Layer neu an)
                let _ = std::fs::remove_file(paths::panel_pose_file());
                let _ = std::fs::remove_file(paths::button_pose_file());
            }
            Action::Toggle(key) => layer(&[(key, Value::Bool(!self.lcfg.b(key)))]),
            Action::Bar(panel::Bar::Button) => {
                let (lo, hi) = panel::BUTTON_CM;
                panel::set_button_cm(lo + (frac * (hi - lo) as f32).round() as i32);
            }
            Action::Bar(panel::Bar::Size) => {
                let (lo, hi) = panel::SIZE_CM;
                panel::set_width_cm(lo + (frac * (hi - lo) as f32).round() as i32);
            }
            Action::Bar(panel::Bar::Opacity) => {
                let pct = ((30.0 + frac * 70.0) / 10.0).round() as i64 * 10;
                layer(&[("panel_opacity", Value::from(pct.clamp(30, 100)))]);
            }
            Action::Anchor(a) => {
                if self.lcfg.s("panel_anchor") != a {
                    layer(&[("panel_anchor", Value::from(a))]);
                    // anderer Anker → Position passt nicht mehr: neu vor dem Kopf
                    let _ = std::fs::remove_file(paths::panel_pose_file());
                }
            }
            Action::Layer(key, value) => {
                // Auslöser und Typ-Taste nie gleich → die andere ausweichen lassen (wie layer_config.update)
                let mut changes = vec![(key, Value::from(value.clone()))];
                let other = match key {
                    "shutter" => Some("mode_button"),
                    "mode_button" => Some("shutter"),
                    _ => None,
                };
                if let Some(other) = other.filter(|o| self.lcfg.s(o) == value) {
                    let free = ["left", "right", "both"].into_iter().find(|c| *c != value).unwrap_or("left");
                    changes.push((other, Value::from(free)));
                }
                layer(&changes);
            }
            Action::Route(r) => {
                // wie translation.set_route: → ✋ Manuell fängt mit „Übersetzen“ an
                let was_auto = trn::route_mode(&self.cfg) == trn::ROUTE_AUTO;
                self.cfg.set("tr_route", r.as_str());
                if was_auto && trn::route_mode(&self.cfg) == trn::ROUTE_MANUAL {
                    self.cfg.set("tr_llm_mode", llm::MODE_TRANSLATE);
                }
                self.save_cfg(&["tr_route", "tr_llm_mode"]);
                if !self.live_shown {
                    self.auto_task.clear();
                    self.start_photo(false, true);
                }
            }
            Action::Page(step) => {
                self.result_page = (self.result_page as i64 + step as i64).clamp(0, self.pages.saturating_sub(1) as i64) as usize;
            }
            Action::Nav(step) => self.switch_page(self.page.step(step)),
            Action::GalPage(step) => {
                let pages = self.gal_pages.len().max(1) as i64;
                self.gal_page = (self.gal_page as i64 + step as i64).clamp(0, pages - 1) as usize;
            }
            Action::GalOpen(i) => {
                self.gal_open = self.gal_list.get(i).map(|p| p.path.clone());
                self.gal_confirm = false;
                self.gal_sub = None;
                self.gal_toast.clear();
            }
            Action::GalBack => {
                if let Some(i) = self.gal_open.as_ref().and_then(|p| self.gal_index(p)) {
                    self.gal_page = self.page_of(i); // Raster dort, wo das Foto steht
                }
                self.gal_open = None;
                self.gal_confirm = false;
                self.gal_sub = None;
                self.gal_toast.clear();
            }
            Action::GalStep(step) => {
                if let Some(i) = self.gal_open.as_ref().and_then(|p| self.gal_index(p)) {
                    let n = i as i64 + step as i64;
                    if let Some(p) = usize::try_from(n).ok().and_then(|n| self.gal_list.get(n)) {
                        self.gal_open = Some(p.path.clone());
                        self.gal_confirm = false;
                        self.gal_toast.clear();
                    }
                }
            }
            Action::GalTranslate => {
                if let Some(p) = self.gal_open.take() {
                    self.chosen = Some(p.clone());
                    self.photo = Some(p);
                    self.switch_page(Page::Translate);
                    if !self.live_shown {
                        self.auto_task.clear();
                        self.start_photo(false, true);
                    }
                }
            }
            Action::GalCopy => {
                if let Some(p) = self.gal_open.clone() {
                    let ok = actions::copy_image(&p);
                    self.gal_toast = if ok { self.t("vr_copied_image", &[]) } else { "✘ wl-copy / xclip?".into() };
                }
            }
            Action::GalUpload => {
                if let Some(p) = self.gal_open.clone() {
                    if let Some((view, _)) = actions::saved_links(&p) {
                        actions::copy_text(&view); // schon hochgeladen → nur Link kopieren
                        self.gal_toast = self.t("vr_link_copied", &[]);
                    } else if self.uploading.insert(p.clone()) {
                        self.gal_toast = self.t("vr_uploading", &[]);
                        let out = self.msgs.clone();
                        std::thread::spawn(move || {
                            let res = actions::upload(&p);
                            let _ = out.send(Msg::Upload { path: p, res });
                        });
                    }
                }
            }
            Action::GalShare => self.gal_sub = Some(Sub::Share(actions::share_targets())),
            Action::GalInfo => {
                if let Some(p) = self.gal_open.clone() {
                    self.gal_sub = Some(Sub::Info(self.info_rows(&p)));
                }
            }
            Action::SubBack => self.gal_sub = None,
            Action::ShareTo(key) => {
                if let Some(p) = self.gal_open.clone() {
                    self.gal_toast = match actions::share(&key, &p) {
                        Ok("paste") => self.t("vr_shared_paste", &[]),
                        Ok(_) => self.t("vr_shared", &[]),
                        Err(e) => format!("{}: {e}", self.t("share_failed", &[])),
                    };
                }
                self.gal_sub = None;
            }
            Action::GalDelete => {
                if let Some(p) = self.gal_open.clone() {
                    if !self.gal_confirm {
                        self.gal_confirm = true; // nochmal tippen = wirklich löschen
                    } else {
                        self.gal_confirm = false;
                        if paths::trash(&p) {
                            let i = self.gal_index(&p).unwrap_or(0);
                            self.gal_list.retain(|x| x.path != p);
                            self.scan_gallery(true);
                            // das nächste Foto zeigen – war es das letzte, zurück ins Raster
                            self.gal_open = self.gal_list.get(i.min(self.gal_list.len().saturating_sub(1))).map(|x| x.path.clone());
                            self.gal_toast.clear();
                            if self.chosen.as_ref() == Some(&p) {
                                self.chosen = None;
                            }
                        } else {
                            self.gal_toast = self.t("delete_failed", &[]);
                            log::line(&format!("Papierkorb: {} konnte nicht verschoben werden", p.display()));
                        }
                    }
                }
            }
            Action::Redo => {
                if !self.live_shown && self.busy.is_none() {
                    self.start_photo(true, true);
                }
            }
            Action::Choose(c) => self.choosing = Some(c),
            Action::Back => self.choosing = None,
            Action::Pick(_, value) if value == panel::HEADER => return,
            Action::Pick(c, value) => {
                self.choosing = None;
                self.pick(c, &value);
            }
        }
        self.reload(false);
        self.redraw(true);
    }

    fn pick(&mut self, c: Choice, value: &str) {
        match c {
            Choice::Method => {
                // wie translation.set_main: springt der Modus auf ✋ Manuell → Aufgabe „Übersetzen“
                let was_auto = trn::route_mode(&self.cfg) == trn::ROUTE_AUTO;
                self.cfg.set("tr_method", value);
                if was_auto && trn::route_mode(&self.cfg) == trn::ROUTE_MANUAL {
                    self.cfg.set("tr_llm_mode", llm::MODE_TRANSLATE);
                }
                self.save_cfg(&["tr_method", "tr_llm_mode"]);
            }
            Choice::Source => {
                self.cfg.set("tr_source", value);
                self.save_cfg(&["tr_source"]);
            }
            Choice::Target => {
                self.cfg.set("tr_target", value);
                self.save_cfg(&["tr_target"]);
            }
            Choice::Mode => {
                if trn::route_mode(&self.cfg) == trn::ROUTE_AUTO {
                    let name = self.photo.as_ref().and_then(|p| p.file_name()).map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
                    self.cfg.set("tr_auto_once", value);
                    self.cfg.set("tr_auto_once_photo", if value.is_empty() { String::new() } else { name });
                    self.cfg.set("tr_auto_once_next", "");
                    self.save_cfg(&["tr_auto_once", "tr_auto_once_photo", "tr_auto_once_next"]);
                } else {
                    self.cfg.set("tr_llm_mode", value);
                    self.save_cfg(&["tr_llm_mode"]);
                }
            }
        }
        // neu übersetzen (Cache wird benutzt, falls schon mal gemacht)
        if !self.live_shown {
            self.auto_task.clear();
            self.start_photo(false, true);
        } else {
            self.live_text.clear();
            self.live_result = None;
        }
    }
}

/// Hauptschleife. `stay` = nicht von selbst beenden (Test / von Hand gestartet)
pub fn run(stay: bool) {
    let Some(control) = control_socket() else { return };
    // erst jetzt: eine zweite Instanz (Port belegt) leert das Log der laufenden nicht
    log::start();
    log::line(&format!("viewshot-daemon {} gestartet", env!("CARGO_PKG_VERSION")));
    let (job_tx, job_rx) = channel();
    let (msg_tx, msg_rx) = channel();
    let out = msg_tx.clone();
    std::thread::spawn(move || worker(job_rx, out));
    let mut st = State {
        fonts: Fonts::new(),
        cfg: settings::load_ui(),
        lcfg: settings::load_layer(),
        cfg_mtime: file_mtime(&settings::ui_file()),
        lcfg_mtime: file_mtime(&settings::layer_file()),
        photo: None,
        lines: Vec::new(),
        ocr_text: String::new(),
        result: String::new(),
        status: String::new(),
        last_ai: String::new(),
        busy: None,
        auto_task: String::new(),
        live_shown: false,
        live_busy: false,
        live_mtime: file_mtime(&paths::live_file()), // altes Live-Bild nicht zeigen
        live_text: String::new(),
        live_result: None,
        live_lines: Vec::new(),
        choosing: None,
        hits: Vec::new(),
        panel_size: (1, 1),
        last_view: None,
        photo_cache: None,
        sheet_open: false,
        page: panel::current_page(),
        gal_page: 0,
        gal_open: None,
        gal_confirm: false,
        gal_list: Vec::new(),
        gal_scan: None,
        gal_pages: Vec::new(),
        gal_toast: String::new(),
        gal_sub: None,
        uploading: HashSet::new(),
        chosen: None,
        newest_mtime: None,
        thumbs: HashMap::new(),
        big_cache: None,
        result_page: 0,
        pages: 1,
        paged_result: String::new(),
        slide: Vec::new(),
        slide_next: Instant::now(),
        pose_mtime: None,
        next_id: 0,
        jobs: job_tx,
        msgs: msg_tx,
    };
    let mut panel_sock: Option<(u16, UdpSocket)> = None;
    let mut paused: Option<bool> = None;
    let mut last_hello = Instant::now();
    let mut bye = false;
    let mut last_check = Instant::now() - CHECK;
    let mut buf = [0u8; 512];
    loop {
        // Nachrichten vom Layer: hello <App> / bye / stop
        while let Ok((n, _)) = control.recv_from(&mut buf) {
            let msg = String::from_utf8_lossy(&buf[..n]).trim().to_string();
            if msg.starts_with("hello") {
                // "hello\n<App>\n<Foto-Ordner>" (alt: "hello <App>")
                let parts: Vec<&str> = msg.lines().collect();
                if let Some(dir) = parts.get(2).filter(|d| d.starts_with('/')) {
                    if paths::photo_dir() != Path::new(dir) {
                        log::line(&format!("Foto-Ordner laut Layer: {dir}"));
                        paths::set_photo_dir(PathBuf::from(dir));
                    }
                }
                if bye || last_hello.elapsed() > Duration::from_secs(30) {
                    log::line(&format!("Layer meldet sich: {}", parts.get(1).copied().unwrap_or(&msg)));
                }
                last_hello = Instant::now();
                bye = false;
            } else if msg == "bye" {
                log::line("Layer: Spiel beendet");
                bye = true;
                last_hello = Instant::now();
            } else if msg == "stop" {
                log::line("Beenden auf Wunsch");
                return;
            }
        }
        if !stay && (last_hello.elapsed() > IDLE_EXIT || (bye && last_hello.elapsed() > BYE_EXIT)) {
            log::line("Kein VR-Spiel mehr – Dienst beendet sich");
            return;
        }

        if last_check.elapsed() >= CHECK {
            last_check = Instant::now();
            let app = app_running();
            if paused != Some(app) {
                log::line(if app { "Desktop-App ist offen – sie übernimmt" } else { "Dienst übernimmt (App ist zu)" });
                paused = Some(app);
                panel_sock = None; // Port freigeben (die App braucht ihn)
                if !app {
                    st.reload(true);
                    st.photo = None; // neuestes Foto neu anzeigen
                    st.last_view = None;
                }
            }
            if app {
                std::thread::sleep(TICK);
                continue;
            }
            let changed = st.reload(false);
            let port = st.lcfg.f("panel_port", 47931.0) as u16;
            if st.lcfg.b("panel") && panel_sock.as_ref().is_none_or(|(p, _)| *p != port) {
                panel_sock = UdpSocket::bind(("127.0.0.1", port)).ok().and_then(|s| s.set_nonblocking(true).ok().map(|_| (port, s)));
            }
            st.check_photo();
            st.check_live();
            st.redraw(changed);
        }
        if paused == Some(true) {
            std::thread::sleep(TICK);
            continue;
        }
        if !st.slide.is_empty() && st.slide_next.elapsed() >= SLIDE_MS {
            st.next_slide();
        }
        while let Ok(msg) = msg_rx.try_recv() {
            st.on_msg(msg);
            st.redraw(false);
        }
        if let Some((_, sock)) = &panel_sock {
            let mut clicks = Vec::new();
            while let Ok((n, _)) = sock.recv_from(&mut buf) {
                let parts: Vec<String> = String::from_utf8_lossy(&buf[..n]).split_whitespace().map(String::from).collect();
                if parts.len() == 3 && parts[0] == "click" {
                    if let (Ok(u), Ok(v)) = (parts[1].parse::<f32>(), parts[2].parse::<f32>()) {
                        clicks.push((u, v));
                    }
                }
            }
            for (u, v) in clicks {
                st.click(u, v);
            }
        }
        std::thread::sleep(TICK);
    }
}
