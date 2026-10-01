//! 🪟 Übersetzungs-Panel in VR: ein Fenster, das an der linken/rechten Hand,
//! am Kopf oder in der Welt hängt (Optionen → Shot).
//!
//! Das BILD malt die App (panel/panel.png). Der Layer zeigt es an, zeichnet den
//! Laser und schickt Klicks per UDP an die App (die klickt dann in ihr Qt-Fenster).
//!
//! Bearbeiten-Modus (in der App bzw. im Panel per Laser einschalten):
//!   Grip, während der Laser aufs Panel zeigt → Panel hängt an der Hand und
//!   lässt sich verschieben/drehen · Laser auf Ecke → Ecke leuchtet → Trigger
//!   halten und ziehen: unten rechts = Breite, oben links = Höhe.
//! Grip/Trigger gehen trotzdem auch ans Spiel (bewusst – kein Sperren).
//!
//! Position: panel_pose.json im Config-Ordner = Versatz zum Anker + Breite.
//! Fehlt die Datei (neu oder „Position zurücksetzen“ in der App), erscheint das
//! Panel über dem Knopf (ohne Knopf: 55 cm vor dem Kopf).
//!
//! 🔘 Knopf (wie bei WayVR): hängt am selben Anker (Standard: Handgelenk innen) und
//! klappt das Panel auf/zu (Laser + Trigger). Eigene Position/Drehung/Größe in
//! button_pose.json – im Bearbeiten-Modus: Grip = verschieben/drehen, Laser auf die
//! untere rechte Ecke (leuchtet) + Trigger = Größe. Farbe aus layer.json.
//! Auf/zu steht in panel_state.json; nach einem Foto geht es von selbst auf
//! („Beim Übersetzen öffnen“, layer.json panel_open_on_shot).

use openxr_sys as xr;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime};

// ─────────────────────── Posen-Rechnung ───────────────────────

pub const IDENTITY: xr::Posef = xr::Posef {
    orientation: xr::Quaternionf { x: 0.0, y: 0.0, z: 0.0, w: 1.0 },
    position: xr::Vector3f { x: 0.0, y: 0.0, z: 0.0 },
};

pub fn v(x: f32, y: f32, z: f32) -> xr::Vector3f {
    xr::Vector3f { x, y, z }
}
fn add(a: xr::Vector3f, b: xr::Vector3f) -> xr::Vector3f {
    v(a.x + b.x, a.y + b.y, a.z + b.z)
}
fn sub(a: xr::Vector3f, b: xr::Vector3f) -> xr::Vector3f {
    v(a.x - b.x, a.y - b.y, a.z - b.z)
}
fn scale(a: xr::Vector3f, s: f32) -> xr::Vector3f {
    v(a.x * s, a.y * s, a.z * s)
}
fn dot(a: xr::Vector3f, b: xr::Vector3f) -> f32 {
    a.x * b.x + a.y * b.y + a.z * b.z
}
fn cross(a: xr::Vector3f, b: xr::Vector3f) -> xr::Vector3f {
    v(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
}
fn normalize(a: xr::Vector3f) -> xr::Vector3f {
    let l = dot(a, a).sqrt();
    if l < 1e-6 {
        a
    } else {
        scale(a, 1.0 / l)
    }
}

fn qmul(a: xr::Quaternionf, b: xr::Quaternionf) -> xr::Quaternionf {
    xr::Quaternionf {
        w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
        x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    }
}
fn conj(q: xr::Quaternionf) -> xr::Quaternionf {
    xr::Quaternionf { x: -q.x, y: -q.y, z: -q.z, w: q.w }
}
/// Vektor mit Quaternion drehen (lokal → Welt)
pub fn rotate(q: xr::Quaternionf, p: xr::Vector3f) -> xr::Vector3f {
    let u = v(q.x, q.y, q.z);
    let t = scale(cross(u, p), 2.0);
    add(add(p, scale(t, q.w)), cross(u, t))
}

/// a ∘ b: Pose b, die relativ zu a angegeben ist → Welt
pub fn mul(a: &xr::Posef, b: &xr::Posef) -> xr::Posef {
    xr::Posef { orientation: qmul(a.orientation, b.orientation), position: add(a.position, rotate(a.orientation, b.position)) }
}
pub fn inverse(a: &xr::Posef) -> xr::Posef {
    let q = conj(a.orientation);
    xr::Posef { orientation: q, position: scale(rotate(q, a.position), -1.0) }
}

/// Drehung aus drei senkrechten Achsen (Spalten der Drehmatrix: x, y, z)
fn quat_from_axes(x: xr::Vector3f, y: xr::Vector3f, z: xr::Vector3f) -> xr::Quaternionf {
    // m[Zeile][Spalte]
    let (m00, m01, m02) = (x.x, y.x, z.x);
    let (m10, m11, m12) = (x.y, y.y, z.y);
    let (m20, m21, m22) = (x.z, y.z, z.z);
    let tr = m00 + m11 + m22;
    let (qx, qy, qz, qw) = if tr > 0.0 {
        let s = (tr + 1.0).sqrt() * 2.0;
        ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    } else if m00 > m11 && m00 > m22 {
        let s = (1.0 + m00 - m11 - m22).sqrt() * 2.0;
        (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    } else if m11 > m22 {
        let s = (1.0 + m11 - m00 - m22).sqrt() * 2.0;
        ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    } else {
        let s = (1.0 + m22 - m00 - m11).sqrt() * 2.0;
        ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    };
    xr::Quaternionf { x: qx, y: qy, z: qz, w: qw }
}

/// Pose an `pos`, deren Vorderseite (+Z, so zeigt ein Quad sein Bild) zu `target` schaut,
/// oben bleibt oben (Welt-Y).
pub fn facing(pos: xr::Vector3f, target: xr::Vector3f) -> xr::Posef {
    let z = normalize(sub(target, pos));
    let mut x = cross(v(0.0, 1.0, 0.0), z);
    if dot(x, x) < 1e-6 {
        x = v(1.0, 0.0, 0.0); // genau senkrecht nach oben/unten
    }
    let x = normalize(x);
    let y = cross(z, x);
    xr::Posef { orientation: quat_from_axes(x, y, z), position: pos }
}

/// Dünnes Quad von `from` nach `to` (Laserstrahl), Vorderseite möglichst zum Kopf.
pub fn beam(from: xr::Vector3f, to: xr::Vector3f, head: xr::Vector3f) -> (xr::Posef, f32) {
    let d = sub(to, from);
    let len = dot(d, d).sqrt();
    let x = normalize(d);
    let mid = add(from, scale(d, 0.5));
    let z0 = normalize(sub(head, mid));
    let mut z = sub(z0, scale(x, dot(z0, x)));
    if dot(z, z) < 1e-6 {
        z = cross(x, v(0.0, 1.0, 0.0));
    }
    let z = normalize(z);
    let y = cross(z, x);
    (xr::Posef { orientation: quat_from_axes(x, y, z), position: mid }, len)
}

// ─────────────────────── Treffer ───────────────────────

/// Wo trifft der Strahl (Zeige-Pose, -Z = vorne) das Panel?
/// Some((u, v, Entfernung, Punkt)) mit u/v = 0..1 (links oben = 0,0)
pub fn hit(panel: &xr::Posef, w: f32, h: f32, aim: &xr::Posef) -> Option<(f32, f32, f32, xr::Vector3f)> {
    let origin = aim.position;
    let dir = rotate(aim.orientation, v(0.0, 0.0, -1.0));
    let inv = inverse(panel);
    let o = add(inv.position, rotate(inv.orientation, origin)); // in Panel-Koordinaten
    let d = rotate(inv.orientation, dir);
    if d.z.abs() < 1e-5 {
        return None; // parallel
    }
    let t = -o.z / d.z;
    if !(0.0..=10.0).contains(&t) {
        return None; // hinter dem Controller / zu weit
    }
    let (x, y) = (o.x + d.x * t, o.y + d.y * t);
    if x.abs() > w / 2.0 || y.abs() > h / 2.0 {
        return None;
    }
    Some((x / w + 0.5, 0.5 - y / h, t, add(origin, scale(dir, t))))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Corner {
    /// Höhe ändern
    TopLeft,
    /// Breite ändern
    BottomRight,
}

/// Ecke fürs Größe-Ändern (je 14 % der Breite / Höhe): oben links = Höhe, unten rechts = Breite
pub fn corner(u: f32, v: f32) -> Option<Corner> {
    if u < 0.14 && v < 0.14 {
        Some(Corner::TopLeft)
    } else if u > 0.86 && v > 0.86 {
        Some(Corner::BottomRight)
    } else {
        None
    }
}

// ─────────────────────── Position speichern ───────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum Anchor {
    #[default]
    Left,
    Right,
    Head,
    World,
}

pub const MIN_WIDTH: f32 = 0.12;
pub const MIN_HEIGHT: f32 = 0.08;
pub const MAX_WIDTH: f32 = 1.5;
pub const DEFAULT_WIDTH: f32 = 0.32;
/// 🔘 Knopf: Durchmesser (m)
pub const BUTTON_MIN: f32 = 0.02;
pub const BUTTON_MAX: f32 = 0.20;
pub const BUTTON_DEFAULT: f32 = 0.03;

#[derive(Clone, Copy, Debug, PartialEq, Deserialize, Serialize)]
pub struct Placement {
    pub anchor: Anchor,
    /// Versatz zum Anker: Position [x, y, z], Drehung [x, y, z, w]
    pub position: [f32; 3],
    pub orientation: [f32; 4],
    pub width: f32,
    /// Höhe von Hand gezogen (Ecke oben links) – None = automatisch (passend zum Bild)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub height: Option<f32>,
}

impl Placement {
    pub fn offset(&self) -> xr::Posef {
        let [x, y, z] = self.position;
        let [qx, qy, qz, qw] = self.orientation;
        xr::Posef { position: v(x, y, z), orientation: xr::Quaternionf { x: qx, y: qy, z: qz, w: qw } }
    }
    pub fn from_offset(anchor: Anchor, off: &xr::Posef, width: f32, height: Option<f32>) -> Self {
        let (p, q) = (off.position, off.orientation);
        Placement {
            anchor,
            position: [p.x, p.y, p.z],
            orientation: [q.x, q.y, q.z, q.w],
            width: width.clamp(MIN_WIDTH, MAX_WIDTH),
            height: height.map(|h| h.clamp(MIN_HEIGHT, MAX_WIDTH)),
        }
    }
    /// 🔘 Knopf: rund/quadratisch, nur Durchmesser
    pub fn button(anchor: Anchor, off: &xr::Posef, size: f32) -> Self {
        Placement { width: size.clamp(BUTTON_MIN, BUTTON_MAX), height: None, ..Self::from_offset(anchor, off, MIN_WIDTH, None) }
    }
}

pub fn pose_file() -> Option<PathBuf> {
    crate::config::path().map(|p| p.with_file_name("panel_pose.json"))
}

/// 🔘 Position/Größe des Knopfs (eigene Datei – Panel und Knopf lassen sich einzeln verschieben)
pub fn button_file() -> Option<PathBuf> {
    crate::config::path().map(|p| p.with_file_name("button_pose.json"))
}

/// Auf/zu des Panels (überlebt den Neustart des Spiels)
pub fn state_file() -> Option<PathBuf> {
    crate::config::path().map(|p| p.with_file_name("panel_state.json"))
}

pub fn image_file() -> PathBuf {
    crate::save::output_dir().join("panel").join("panel.png")
}

struct Store {
    placement: Option<Placement>,
    modified: Option<SystemTime>,
    checked: Option<Instant>,
}
static STORE: Mutex<Store> = Mutex::new(Store { placement: None, modified: None, checked: None });
static BUTTON_STORE: Mutex<Store> = Mutex::new(Store { placement: None, modified: None, checked: None });

/// So oft schauen, ob die App die Datei geändert hat (z. B. Seite gewechselt → andere Größe).
/// Nur ein stat() – billig; kurz, damit der Größenwechsel sofort zum neuen Bild passt.
const RELOAD: Duration = Duration::from_millis(80);

fn load(store: &Mutex<Store>, path: Option<PathBuf>) -> Option<Placement> {
    let mut st = store.lock().unwrap_or_else(|e| e.into_inner());
    if st.checked.is_none_or(|t| t.elapsed() >= RELOAD) {
        st.checked = Some(Instant::now());
        let modified = path.as_ref().and_then(|p| std::fs::metadata(p).and_then(|m| m.modified()).ok());
        if modified != st.modified {
            st.modified = modified;
            st.placement = path.and_then(|p| std::fs::read_to_string(p).ok()).and_then(|t| serde_json::from_str(&t).ok());
        }
    }
    st.placement
}

fn store(store: &Mutex<Store>, path: Option<PathBuf>, p: Placement, write: bool) {
    let mut st = store.lock().unwrap_or_else(|e| e.into_inner());
    st.placement = Some(p);
    if write {
        if let Some(path) = path {
            let tmp = path.with_extension("tmp");
            if let Ok(text) = serde_json::to_string_pretty(&p) {
                if std::fs::write(&tmp, text).is_ok() && std::fs::rename(&tmp, &path).is_ok() {
                    st.modified = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
                }
            }
        }
    }
}

/// Gespeicherte Position (liest die Datei neu, wenn die App sie geändert/gelöscht hat).
pub fn placement() -> Option<Placement> {
    load(&STORE, pose_file())
}

/// Neue Position merken (sofort) und speichern (Datei).
pub fn set_placement(p: Placement, write: bool) {
    store(&STORE, pose_file(), p, write)
}

/// 🔘 Gespeicherte Position/Größe des Knopfs
pub fn button_placement() -> Option<Placement> {
    load(&BUTTON_STORE, button_file())
}

pub fn set_button_placement(p: Placement, write: bool) {
    store(&BUTTON_STORE, button_file(), p, write)
}

static OPEN: Mutex<Option<bool>> = Mutex::new(None);

/// Panel aufgeklappt? (Standard: ja)
pub fn is_open() -> bool {
    let mut open = OPEN.lock().unwrap_or_else(|e| e.into_inner());
    *open.get_or_insert_with(|| {
        state_file()
            .and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok())
            .and_then(|v| v["open"].as_bool())
            .unwrap_or(true)
    })
}

/// Auf-/zuklappen (🔘 Knopf, nach einem Foto) – wird gemerkt
pub fn set_open(value: bool) {
    *OPEN.lock().unwrap_or_else(|e| e.into_inner()) = Some(value);
    if let Some(path) = state_file() {
        let _ = std::fs::write(path, format!("{{\"open\": {value}}}\n"));
    }
}

/// 🔘 Standard-Platz des Knopfs (Versatz zum Anker): oben auf der Hand (Hand-Anker),
/// unten links im Blick (Kopf) bzw. dort vor dem Kopf (Welt). `anchor_pose`/`head` in Welt-Koordinaten.
pub fn default_button(anchor: Anchor, anchor_pose: &xr::Posef, head: &xr::Posef) -> xr::Posef {
    // Grip-Pose: −Z = nach vorne, +Z = Richtung Handgelenk, +X = rechts, +Y = oben.
    // Linke Hand: so, wie Yakuda ihn in VR hingeschoben hat (oben auf der Hand, nicht darunter).
    // Rechte Hand: dasselbe gespiegelt (x → −x; Drehung (x, y, z, w) → (x, −y, −z, w)).
    let (p, q) = (BUTTON_LEFT_POS, BUTTON_LEFT_ROT);
    let rot = |q: [f32; 4]| xr::Quaternionf { x: q[0], y: q[1], z: q[2], w: q[3] };
    match anchor {
        Anchor::Left => xr::Posef { position: v(p[0], p[1], p[2]), orientation: rot(q) },
        Anchor::Right => xr::Posef { position: v(-p[0], p[1], p[2]), orientation: rot([q[0], -q[1], -q[2], q[3]]) },
        Anchor::Head => xr::Posef { position: v(-0.20, -0.18, -0.45), orientation: IDENTITY.orientation },
        Anchor::World => {
            let at = |x: f32, y: f32, z: f32| add(head.position, rotate(head.orientation, v(x, y, z)));
            let world = facing(at(-0.20, -0.18, -0.50), head.position);
            mul(&inverse(anchor_pose), &world)
        }
    }
}

/// 🔘 Standard an der linken Hand (Versatz zur Grip-Pose) – in VR ausprobiert
const BUTTON_LEFT_POS: [f32; 3] = [-0.081_937_37, -0.028_864_98, 0.059_111_297];
const BUTTON_LEFT_ROT: [f32; 4] = [0.426_948_73, 0.704_818_84, -0.344_486_77, -0.449_749_4];

/// Standard-Platz des Panels: über dem Knopf (in Knopf-Richtung „oben“), gleich gedreht.
/// `button` = Versatz des Knopfs zum Anker, `panel_h` = erwartete Panel-Höhe.
pub fn default_above(button: &Placement, panel_h: f32) -> xr::Posef {
    let up = button.width / 2.0 + 0.03 + panel_h / 2.0;
    mul(&button.offset(), &xr::Posef { position: v(0.0, up, 0.0), ..IDENTITY })
}

/// „#5b8dc9“ → (r, g, b) – kaputt/leer → Blau
pub fn parse_color(text: &str) -> [u8; 3] {
    let hex = text.trim().trim_start_matches('#');
    let part = |i: usize| hex.get(i..i + 2).and_then(|h| u8::from_str_radix(h, 16).ok());
    match (hex.len(), part(0), part(2), part(4)) {
        (6, Some(r), Some(g), Some(b)) => [r, g, b],
        _ => [0x5b, 0x8d, 0xc9],
    }
}

/// Pixel des Knopfs (size × size, RGBA bzw. BGRA): runde Scheibe in der Farbe mit
/// Fenster-Symbol; `open` = heller Ring außen (Panel ist offen).
pub fn button_pixels(size: u32, color: [u8; 3], open: bool, bgr: bool) -> Vec<u8> {
    let s = size as f32;
    let (c, r) = (s / 2.0, s / 2.0 - 1.0);
    let ring = s * 0.07;
    let mut out = Vec::with_capacity((size * size * 4) as usize);
    // Fenster-Symbol: Rahmen + Titelleiste + zwei Zeilen (in Anteilen der Größe)
    let (x0, x1, y0, y1) = (0.30 * s, 0.70 * s, 0.32 * s, 0.68 * s);
    let line = (s * 0.045).max(1.5);
    for y in 0..size {
        for x in 0..size {
            let (px, py) = (x as f32 + 0.5, y as f32 + 0.5);
            let d = ((px - c).powi(2) + (py - c).powi(2)).sqrt();
            let alpha = (r - d + 0.5).clamp(0.0, 1.0); // weicher Rand
            let mut col = [color[0] as f32, color[1] as f32, color[2] as f32];
            // dunklerer Rand (geschlossen) bzw. weißer Ring (offen)
            if d > r - ring {
                col = if open { [255.0, 255.0, 255.0] } else { col.map(|v| v * 0.6) };
            }
            let inside = px >= x0 && px <= x1 && py >= y0 && py <= y1;
            let border = inside && (px < x0 + line || px > x1 - line || py < y0 + line || py > y1 - line);
            let title = inside && py < y0 + 0.22 * (y1 - y0);
            let text = inside
                && px > x0 + 0.18 * (x1 - x0)
                && px < x1 - 0.18 * (x1 - x0)
                && [0.52, 0.74].iter().any(|f| (py - (y0 + f * (y1 - y0))).abs() < line / 2.0);
            if border || title || text {
                col = [255.0, 255.0, 255.0];
            }
            let [r8, g8, b8] = col.map(|v| v.round().clamp(0.0, 255.0) as u8);
            let a8 = (alpha * 255.0).round() as u8;
            if bgr {
                out.extend([b8, g8, r8, a8]);
            } else {
                out.extend([r8, g8, b8, a8]);
            }
        }
    }
    out
}

/// Standard: 55 cm vor dem Kopf, zum Kopf gedreht.
pub fn default_world(head: &xr::Posef) -> xr::Posef {
    let fwd = rotate(head.orientation, v(0.0, 0.0, -1.0));
    let pos = add(head.position, scale(fwd, 0.55));
    facing(pos, head.position)
}

// ─────────────────────── Bedienung ───────────────────────

/// Eingaben einer Hand in diesem Frame
#[derive(Clone, Copy, Debug)]
pub struct HandInput {
    pub aim: Option<xr::Posef>,
    pub trigger: f32,
    pub grip: f32,
}

#[derive(Default, Debug)]
pub struct Output {
    pub clicks: Vec<(f32, f32)>,
    /// Laser: (Hand, Startpunkt, Trefferpunkt)
    pub laser: Option<(usize, xr::Vector3f, xr::Vector3f)>,
    pub corner: Option<Corner>,
    /// Panel wurde verschoben/vergrößert (neue Welt-Pose, Breite, Höhe von Hand oder None)
    pub moved: Option<(xr::Posef, f32, Option<f32>)>,
    /// Loslassen → jetzt speichern
    pub save: bool,
}

pub struct Interaction {
    trigger: [bool; 2],
    grip: [bool; 2],
    /// Greifen: (Hand, Panel relativ zur Hand)
    grab: Option<(usize, xr::Posef)>,
    /// Größe ändern mit dieser Hand an dieser Ecke
    resize: Option<(usize, Corner)>,
    /// 🔘 Knopf: quadratisch (nur ein Maß), größere Ecke, eigene Grenzen
    square: bool,
    limits: (f32, f32),
}

impl Default for Interaction {
    fn default() -> Self {
        Self::panel()
    }
}

const PRESS: f32 = 0.75;
const RELEASE: f32 = 0.35;

impl Interaction {
    pub fn panel() -> Self {
        Interaction { trigger: [false; 2], grip: [false; 2], grab: None, resize: None, square: false, limits: (MIN_WIDTH, MAX_WIDTH) }
    }

    /// 🔘 Knopf: Ecke unten rechts = Größe (beide Maße gleich)
    pub fn button() -> Self {
        Interaction { square: true, limits: (BUTTON_MIN, BUTTON_MAX), ..Self::panel() }
    }

    /// Wird gerade verschoben oder vergrößert? (dann gehört die Hand diesem Teil)
    pub fn busy(&self) -> bool {
        self.grab.is_some() || self.resize.is_some()
    }

    /// Ein Frame: Treffer suchen, Klicks / Greifen / Größe auswerten.
    /// `height` = aktuelle Höhe (von Hand gezogen oder automatisch), `fixed` = von Hand gezogen?
    pub fn update(
        &mut self,
        hands: [HandInput; 2],
        panel: &xr::Posef,
        (width, h): (f32, f32),
        fixed: Option<f32>,
        edit: bool,
    ) -> Output {
        let mut out = Output::default();
        // gedrückt / losgelassen (mit Abstand dazwischen, damit nichts flattert)
        let mut pressed = [false; 2];
        let mut grabbed = [false; 2];
        for i in 0..2 {
            let t = hands[i].trigger;
            let was = self.trigger[i];
            self.trigger[i] = if was { t > RELEASE } else { t > PRESS };
            pressed[i] = self.trigger[i] && !was;
            let g = hands[i].grip;
            let was = self.grip[i];
            self.grip[i] = if was { g > RELEASE } else { g > PRESS };
            grabbed[i] = self.grip[i] && !was;
        }

        // Laufendes Greifen: Panel folgt der Hand
        if let Some((i, rel)) = self.grab {
            match hands[i].aim {
                Some(aim) if self.grip[i] && edit => {
                    out.moved = Some((mul(&aim, &rel), width, fixed));
                    out.laser = None;
                    return out;
                }
                _ => {
                    self.grab = None;
                    out.save = true;
                }
            }
        }
        // Laufende Größenänderung: 2 × Abstand des Laserpunkts zur Mitte
        // (unten rechts = Breite, oben links = Höhe)
        if let Some((i, c)) = self.resize {
            if self.trigger[i] && edit {
                if let Some(aim) = hands[i].aim {
                    if let Some((w, hh)) = resize_extent(panel, &aim) {
                        let (lo, hi) = self.limits;
                        out.moved = Some(match c {
                            Corner::BottomRight if self.square => (*panel, w.max(hh).clamp(lo, hi), None),
                            Corner::BottomRight => (*panel, w.clamp(lo, hi), fixed),
                            Corner::TopLeft => (*panel, width, Some(hh.clamp(MIN_HEIGHT, MAX_WIDTH))),
                        });
                        out.corner = Some(c);
                    }
                    let end = add(aim.position, scale(rotate(aim.orientation, v(0.0, 0.0, -1.0)), 0.3));
                    out.laser = Some((i, aim.position, end));
                }
                return out;
            }
            self.resize = None;
            out.save = true;
        }

        // Treffer: rechte Hand zuerst
        for i in [1, 0] {
            let Some(aim) = hands[i].aim else { continue };
            let Some((u, vv, _dist, point)) = hit(panel, width, h, &aim) else { continue };
            out.laser = Some((i, aim.position, point));
            if edit {
                // Knopf ist klein → größere Ecke, nur unten rechts
                out.corner = if self.square { (u > 0.6 && vv > 0.6).then_some(Corner::BottomRight) } else { corner(u, vv) };
                if grabbed[i] {
                    self.grab = Some((i, mul(&inverse(&aim), panel)));
                    return out;
                }
                if let (true, Some(c)) = (pressed[i], out.corner) {
                    self.resize = Some((i, c));
                    return out;
                }
            }
            if pressed[i] {
                out.clicks.push((u, vv));
            }
            break;
        }
        out
    }
}

/// Neue (Breite, Höhe) beim Ziehen an einer Ecke (unendliche Panel-Ebene, damit man
/// auch über den Rand hinaus ziehen kann).
fn resize_extent(panel: &xr::Posef, aim: &xr::Posef) -> Option<(f32, f32)> {
    let inv = inverse(panel);
    let o = add(inv.position, rotate(inv.orientation, aim.position));
    let d = rotate(inv.orientation, rotate(aim.orientation, v(0.0, 0.0, -1.0)));
    if d.z.abs() < 1e-5 {
        return None;
    }
    let t = -o.z / d.z;
    if t <= 0.0 {
        return None;
    }
    Some((2.0 * (o.x + d.x * t).abs(), 2.0 * (o.y + d.y * t).abs()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn near(a: f32, b: f32) -> bool {
        (a - b).abs() < 1e-4
    }
    fn near_v(a: xr::Vector3f, b: xr::Vector3f) -> bool {
        near(a.x, b.x) && near(a.y, b.y) && near(a.z, b.z)
    }
    /// Zeige-Pose an `pos`, die in Richtung `dir` zeigt (-Z = vorne)
    fn aim_at(pos: xr::Vector3f, target: xr::Vector3f) -> xr::Posef {
        let mut p = facing(pos, target);
        // facing: +Z zeigt zum Ziel → umdrehen, damit -Z zum Ziel zeigt
        p.orientation = qmul(p.orientation, xr::Quaternionf { x: 0.0, y: 1.0, z: 0.0, w: 0.0 });
        p
    }
    /// Panel 1 m vor dem Ursprung (Blick nach -Z), zum Ursprung gedreht
    fn panel() -> xr::Posef {
        facing(v(0.0, 0.0, -1.0), v(0.0, 0.0, 0.0))
    }
    fn hand(aim: Option<xr::Posef>, trigger: f32, grip: f32) -> HandInput {
        HandInput { aim, trigger, grip }
    }

    #[test]
    fn pose_math_roundtrip() {
        let a = facing(v(1.0, 2.0, 3.0), v(0.0, 0.0, 0.0));
        let b = facing(v(-0.5, 0.2, 0.1), v(2.0, 1.0, -1.0));
        let rel = mul(&inverse(&a), &b);
        let back = mul(&a, &rel);
        assert!(near_v(back.position, b.position));
        assert!(near_v(rotate(back.orientation, v(0.0, 0.0, 1.0)), rotate(b.orientation, v(0.0, 0.0, 1.0))));
    }

    #[test]
    fn facing_points_front_to_target_and_keeps_up() {
        let p = facing(v(0.0, 0.0, -1.0), v(0.0, 0.0, 0.0));
        assert!(near_v(rotate(p.orientation, v(0.0, 0.0, 1.0)), v(0.0, 0.0, 1.0)));
        assert!(near_v(rotate(p.orientation, v(0.0, 1.0, 0.0)), v(0.0, 1.0, 0.0)));
        let p = facing(v(1.0, 0.0, 0.0), v(0.0, 0.0, 0.0)); // rechts vom Kopf
        assert!(near_v(rotate(p.orientation, v(0.0, 0.0, 1.0)), v(-1.0, 0.0, 0.0)));
    }

    #[test]
    fn default_is_in_front_of_head() {
        let p = default_world(&IDENTITY);
        assert!(near_v(p.position, v(0.0, 0.0, -0.55)));
    }

    #[test]
    fn ray_hits_panel_uv() {
        let (w, h) = (0.4, 0.3);
        let aim = aim_at(v(0.0, 0.0, 0.0), v(0.0, 0.0, -1.0));
        let (u, vv, t, _) = hit(&panel(), w, h, &aim).unwrap();
        assert!(near(u, 0.5) && near(vv, 0.5) && near(t, 1.0));
        // oben rechts: x = +0.1, y = +0.1 → u = 0.75, v = 0.1667
        let aim = aim_at(v(0.0, 0.0, 0.0), v(0.1, 0.1, -1.0));
        let (u, vv, _, _) = hit(&panel(), w, h, &aim).unwrap();
        assert!(near(u, 0.75) && (vv - (0.5 - 0.1 / 0.3)).abs() < 1e-3, "{u} {vv}");
        // daneben / nach hinten
        assert!(hit(&panel(), w, h, &aim_at(v(0.0, 0.0, 0.0), v(1.0, 0.0, -1.0))).is_none());
        assert!(hit(&panel(), w, h, &aim_at(v(0.0, 0.0, 0.0), v(0.0, 0.0, 1.0))).is_none());
    }

    #[test]
    fn corners_only_at_the_bottom() {
        assert_eq!(corner(0.05, 0.05), Some(Corner::TopLeft));
        assert_eq!(corner(0.95, 0.95), Some(Corner::BottomRight));
        assert_eq!(corner(0.05, 0.95), None);
        assert_eq!(corner(0.5, 0.95), None);
    }

    #[test]
    fn trigger_clicks_once_where_the_laser_points() {
        let mut it = Interaction::default();
        let aim = Some(aim_at(v(0.0, 0.0, 0.0), v(0.0, 0.0, -1.0)));
        let out = it.update([hand(None, 0.0, 0.0), hand(aim, 0.0, 0.0)], &panel(), (0.4, 0.3), None, false);
        assert!(out.clicks.is_empty() && out.laser.is_some());
        let out = it.update([hand(None, 0.0, 0.0), hand(aim, 1.0, 0.0)], &panel(), (0.4, 0.3), None, false);
        assert_eq!(out.clicks.len(), 1);
        assert!(near(out.clicks[0].0, 0.5));
        let out = it.update([hand(None, 0.0, 0.0), hand(aim, 1.0, 0.0)], &panel(), (0.4, 0.3), None, false);
        assert!(out.clicks.is_empty()); // gehalten = kein zweiter Klick
    }

    #[test]
    fn grip_moves_panel_only_in_edit_mode() {
        let mut it = Interaction::default();
        let start = aim_at(v(0.0, 0.0, 0.0), v(0.0, 0.0, -1.0));
        // ohne Bearbeiten: Grip tut nichts
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(start), 0.0, 1.0)], &panel(), (0.4, 0.3), None, false);
        assert!(out.moved.is_none());
        let mut it = Interaction::default();
        it.update([hand(None, 0.0, 0.0), hand(Some(start), 0.0, 1.0)], &panel(), (0.4, 0.3), None, true);
        // Hand 20 cm nach rechts → Panel auch
        let mut moved = start;
        moved.position.x += 0.2;
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(moved), 0.0, 1.0)], &panel(), (0.4, 0.3), None, true);
        let (p, w, h) = out.moved.unwrap();
        assert!(near_v(p.position, v(0.2, 0.0, -1.0)) && near(w, 0.4) && h.is_none());
        // loslassen → speichern
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(moved), 0.0, 0.0)], &panel(), (0.4, 0.3), None, true);
        assert!(out.save && out.moved.is_none());
    }

    #[test]
    fn corner_drag_resizes() {
        let size = (0.4, 0.3);
        // unten rechts (x = +0.18, y = -0.14) → Breite
        let mut it = Interaction::default();
        let aim = aim_at(v(0.0, 0.0, 0.0), v(0.18, -0.14, -1.0));
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(aim), 0.0, 0.0)], &panel(), size, None, true);
        assert_eq!(out.corner, Some(Corner::BottomRight));
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(aim), 1.0, 0.0)], &panel(), size, None, true);
        assert!(out.clicks.is_empty()); // Ecke = Größe, kein Klick
        let wide = aim_at(v(0.0, 0.0, 0.0), v(0.3, -0.14, -1.0));
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(wide), 1.0, 0.0)], &panel(), size, None, true);
        let (_, w, h) = out.moved.unwrap();
        assert!(near(w, 0.6) && h.is_none()); // Höhe bleibt automatisch
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(wide), 0.0, 0.0)], &panel(), (0.6, 0.45), None, true);
        assert!(out.save);

        // oben links (x = -0.18, y = +0.14) → Höhe, Breite bleibt
        let mut it = Interaction::default();
        let aim = aim_at(v(0.0, 0.0, 0.0), v(-0.18, 0.14, -1.0));
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(aim), 0.0, 0.0)], &panel(), size, None, true);
        assert_eq!(out.corner, Some(Corner::TopLeft));
        it.update([hand(None, 0.0, 0.0), hand(Some(aim), 1.0, 0.0)], &panel(), size, None, true);
        let tall = aim_at(v(0.0, 0.0, 0.0), v(-0.18, 0.35, -1.0));
        let out = it.update([hand(None, 0.0, 0.0), hand(Some(tall), 1.0, 0.0)], &panel(), size, None, true);
        let (_, w, h) = out.moved.unwrap();
        assert!(near(w, 0.4) && near(h.unwrap(), 0.7));
    }

    #[test]
    fn beam_spans_from_to() {
        let (p, len) = beam(v(0.0, 0.0, 0.0), v(0.0, 0.0, -2.0), v(0.0, 0.3, 0.2));
        assert!(near(len, 2.0) && near_v(p.position, v(0.0, 0.0, -1.0)));
        assert!(near_v(rotate(p.orientation, v(1.0, 0.0, 0.0)), v(0.0, 0.0, -1.0)));
    }

    #[test]
    fn placement_roundtrip_json() {
        let off = facing(v(0.1, 0.2, -0.3), v(0.0, 0.0, 0.0));
        let p = Placement::from_offset(Anchor::Head, &off, 5.0, None);
        assert_eq!(p.width, MAX_WIDTH);
        let json = serde_json::to_string(&p).unwrap();
        assert!(json.contains("\"anchor\":\"head\"") && !json.contains("height"));
        let fixed = Placement::from_offset(Anchor::Head, &off, 0.4, Some(0.3));
        let back: Placement = serde_json::from_str(&serde_json::to_string(&fixed).unwrap()).unwrap();
        assert_eq!(back.height, Some(0.3));
        let back: Placement = serde_json::from_str(&json).unwrap();
        assert!(near_v(back.offset().position, off.position));
    }

    #[test]
    fn button_click_and_square_resize() {
        let mut it = Interaction::button();
        let size = 0.05;
        // Knopf 1 m vor dem Ursprung; Laser in die Mitte → Klick (zum Auf/Zu)
        let mid = Some(aim_at(v(0.0, 0.0, 0.0), v(0.0, 0.0, -1.0)));
        it.update([hand(None, 0.0, 0.0), hand(mid, 0.0, 0.0)], &panel(), (size, size), None, true);
        let out = it.update([hand(None, 0.0, 0.0), hand(mid, 1.0, 0.0)], &panel(), (size, size), None, true);
        assert_eq!(out.clicks.len(), 1, "Mitte = Klick, auch im Bearbeiten-Modus");
        it.update([hand(None, 0.0, 0.0), hand(mid, 0.0, 0.0)], &panel(), (size, size), None, true);
        // untere rechte Ecke (große Zone beim Knopf) → Trigger = Größe, quadratisch
        let corner_aim = Some(aim_at(v(0.0, 0.0, 0.0), v(0.018, -0.018, -1.0)));
        let out = it.update([hand(None, 0.0, 0.0), hand(corner_aim, 0.0, 0.0)], &panel(), (size, size), None, true);
        assert_eq!(out.corner, Some(Corner::BottomRight));
        let out = it.update([hand(None, 0.0, 0.0), hand(corner_aim, 1.0, 0.0)], &panel(), (size, size), None, true);
        assert!(out.clicks.is_empty() && it.busy());
        // weiter nach außen ziehen (x 0.05, y −0.03) → Größe = 2 × max = 0.10, ohne Höhe
        let far = Some(aim_at(v(0.0, 0.0, 0.0), v(0.05, -0.03, -1.0)));
        let out = it.update([hand(None, 0.0, 0.0), hand(far, 1.0, 0.0)], &panel(), (size, size), None, true);
        let (_, w, h) = out.moved.unwrap();
        assert!(near(w, 0.10) && h.is_none(), "{w}");
        // riesig → auf BUTTON_MAX begrenzt
        let huge = Some(aim_at(v(0.0, 0.0, 0.0), v(0.9, -0.9, -1.0)));
        let (_, w, _) = it.update([hand(None, 0.0, 0.0), hand(huge, 1.0, 0.0)], &panel(), (size, size), None, true).moved.unwrap();
        assert!(near(w, BUTTON_MAX));
        let out = it.update([hand(None, 0.0, 0.0), hand(huge, 0.0, 0.0)], &panel(), (size, size), None, true);
        assert!(out.save && !it.busy());
    }

    #[test]
    fn button_defaults_and_panel_above() {
        // linke Hand: Yakudas Position; rechte Hand = gespiegelt (Normale auch gespiegelt)
        let l = default_button(Anchor::Left, &IDENTITY, &IDENTITY);
        let r = default_button(Anchor::Right, &IDENTITY, &IDENTITY);
        assert!(near_v(l.position, v(-0.081_937_37, -0.028_864_98, 0.059_111_297)));
        assert!(near_v(r.position, v(0.081_937_37, -0.028_864_98, 0.059_111_297)));
        let (nl, nr) = (rotate(l.orientation, v(0.0, 0.0, 1.0)), rotate(r.orientation, v(0.0, 0.0, 1.0)));
        assert!(near_v(nr, v(-nl.x, nl.y, nl.z)), "Spiegelbild");
        // Spiegeln ändert die Bild-Richtung nicht (rechte Hand → Drehung, keine Spiegelung)
        let ql = l.orientation;
        assert!(near(ql.x * ql.x + ql.y * ql.y + ql.z * ql.z + ql.w * ql.w, 1.0));
        // Kopf: unten links vor dem Kopf
        let off = default_button(Anchor::Head, &IDENTITY, &IDENTITY);
        assert!(off.position.x < 0.0 && off.position.y < 0.0 && off.position.z < 0.0);
        // Welt: vor dem Kopf, zum Kopf gedreht
        let off = default_button(Anchor::World, &IDENTITY, &IDENTITY);
        assert!(off.position.z < -0.4 && near_v(rotate(off.orientation, v(0.0, 0.0, 1.0)), normalize(scale(off.position, -1.0))));
        // Panel über dem Knopf: in Knopf-„oben“ um halbe Knopf- + halbe Panel-Höhe + 3 cm
        let b = Placement::button(Anchor::Head, &xr::Posef { position: v(0.0, -0.2, -0.5), ..IDENTITY }, 0.04);
        let p = default_above(&b, 0.2);
        assert!(near_v(p.position, v(0.0, -0.2 + 0.02 + 0.03 + 0.1, -0.5)));
        assert!(near(b.width, 0.04) && Placement::button(Anchor::Head, &IDENTITY, 9.0).width == BUTTON_MAX);
    }

    #[test]
    fn button_color_and_pixels() {
        assert_eq!(parse_color("#ff8000"), [255, 128, 0]);
        assert_eq!(parse_color("4caf7a"), [0x4c, 0xaf, 0x7a]);
        assert_eq!(parse_color("kaputt"), [0x5b, 0x8d, 0xc9]);
        let px = button_pixels(64, [10, 20, 30], false, false);
        assert_eq!(px.len(), 64 * 64 * 4);
        let at = |px: &[u8], x: usize, y: usize| px[(y * 64 + x) * 4..(y * 64 + x) * 4 + 4].to_vec();
        assert_eq!(at(&px, 0, 0)[3], 0, "Ecke durchsichtig (rund)");
        assert_eq!(at(&px, 8, 32), vec![10, 20, 30, 255], "Fläche in der Farbe");
        assert_eq!(at(&px, 32, 21)[..3], [255, 255, 255], "weißes Fenster-Symbol");
        let open = button_pixels(64, [10, 20, 30], true, false);
        assert_eq!(at(&open, 32, 1)[..3], [255, 255, 255], "offen = weißer Ring");
        let bgr = button_pixels(64, [10, 20, 30], false, true);
        assert_eq!(at(&bgr, 8, 32), vec![30, 20, 10, 255]);
        // zum Anschauen: BUTTON_OUT=/tmp/knopf.png cargo test
        if let Some(out) = std::env::var_os("BUTTON_OUT") {
            let mut both = button_pixels(128, [0x5b, 0x8d, 0xc9], false, false);
            both.extend(button_pixels(128, [0x5b, 0x8d, 0xc9], true, false));
            let file = std::fs::File::create(out).unwrap();
            let mut enc = png::Encoder::new(file, 128, 256);
            enc.set_color(png::ColorType::Rgba);
            enc.write_header().unwrap().write_image_data(&both).unwrap();
        }
    }
}
