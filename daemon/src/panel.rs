//! 🪟 VR-Panel ohne App – sieht aus wie ui/vr_panel.py (gleiche Maße, Farben, Texte).
//! Wird als Bild gezeichnet (<Foto-Ordner>/panel/panel.png); Klicks kommen vom Layer
//! als „click u v“ und werden hier den Knöpfen zugeordnet.
//!
//! Seiten: Übersetzung (lang → ▼ / ▲ blättern) · 🖼 Galerie (Raster über die ganze Fläche,
//! Monats-Trenner, Antippen = Foto groß mit 📋 Kopieren · ☁ Hochladen + Link · ↗ Teilen ·
//! 🌐 Übersetzen · ⓘ Info · 🗑 Löschen) · Auswahl-Liste (Dienst + Modus 🤖/✋, Von, Nach,
//! Aufgabe) · ⚙ Einstellungen (klappt von oben herunter): Größe, Deckkraft, Hängt an,
//! ✥ Verschieben, ⟲ Position, Erkennung & Tasten. Ganz unten: ◀ links, ▶ rechts = Seite
//! wechseln (jede Seite hat ihre eigene Größe in VR, panel_sizes.json).

use crate::i18n::tr;
use crate::ocr::Line;
use crate::render::{line_height, measure, rgba, wrap_lines, Canvas, Fonts, Style};
use std::path::PathBuf;

pub const WIDTH: f32 = 720.0;
const PHOTO_MAX_H: f32 = 360.0;
const RESULT_MAX_H: f32 = 300.0;
const MX: f32 = 18.0;
const MY: f32 = 16.0;
const GAP: f32 = 10.0;
const BTN_H: f32 = 48.0;
const TIP_W: f32 = 64.0;
const ITEM_H: f32 = 54.0;
const BAR_H: f32 = 48.0;
const BAR_PAD: f32 = 20.0;
pub const SIZE_CM: (i32, i32) = (15, 80);
/// 🔘 Knopf-Durchmesser in VR (wie BUTTON_CM in vr_panel.py)
pub const BUTTON_CM: (i32, i32) = (2, 20);
/// 🔘 Knopf-Farben zum Antippen (wie BUTTON_COLORS in vr_panel.py)
pub const BUTTON_COLORS: [&str; 7] = ["#5b8dc9", "#9b6bd6", "#4caf7a", "#e0913a", "#d05a5a", "#6b7280", "#e5e9ef"];
/// Zeile ganz unten: ◀ links, ▶ rechts (Seite wechseln) – wie NAV_H in vr_panel.py
const NAV_H: f32 = 52.0;
const NAV_W: f32 = 230.0;
pub const GRID_COLS: usize = 4;
const GRID_GAP: f32 = 8.0;
const THUMB_RATIO: f32 = 0.75;
const MONTH_H: f32 = 34.0;
/// Galerie ohne von Hand gezogene Höhe: so hoch wird das Panel
pub const GALLERY_H: f32 = 760.0;
const SINGLE_MAX_H: f32 = 360.0;
/// Breite in VR (m) je Seite, wenn noch keine gemerkt ist (Galerie größer)
pub const PAGE_SIZE_DEFAULT: [(&str, f64); 2] = [("translate", 0.32), ("gallery", 0.48)];
const NUMBERS: &str = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";

const TEXT: u32 = 0xd7dbe2;
const DIM: u32 = 0x7a8290;
const SECTION: u32 = 0xaeb4bf;
const BTN_BG: u32 = 0x232833;
const BTN_BORDER: u32 = 0x333947;
const BTN_TEXT: u32 = 0xe5e9ef;
const BLUE: u32 = 0x5b8dc9;
pub const BG: u32 = 0x161a22;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Choice {
    Method,
    Source,
    Target,
    Mode,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Bar {
    Size,
    Opacity,
    /// 🔘 Knopf-Größe
    Button,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Action {
    /// ⚙ Einstellungen auf-/zuklappen
    Sheet,
    Reset,
    Choose(Choice),
    Redo,
    Back,
    Pick(Choice, String),
    /// Schieber: Wert aus der Klick-Position (0..1)
    Bar(Bar),
    Anchor(String),
    /// ✥ Verschieben (Grip) an/aus
    Move,
    /// layer.json-Wert (detect_mode / shutter / mode_button / panel_button_color)
    Layer(&'static str, String),
    /// layer.json an/aus (panel_button / panel_open_on_shot)
    Toggle(&'static str),
    Route(String),
    Page(i32),
    /// ◀ ▶ ganz unten: Seite wechseln (Übersetzung ↔ Galerie)
    Nav(i32),
    /// Galerie: Raster-Seite blättern
    GalPage(i32),
    /// Galerie: Foto (Nummer in der Liste) groß zeigen
    GalOpen(usize),
    GalBack,
    /// Einzelansicht: voriges / nächstes Foto
    GalStep(i32),
    /// 🌐 dieses Foto übersetzen
    GalTranslate,
    /// 🗑 erst „Wirklich löschen?“, dann in den Papierkorb
    GalDelete,
    /// 📋 Bild in die Zwischenablage
    GalCopy,
    /// ☁ Hochladen + Link kopieren (schon hochgeladen → nur Link kopieren)
    GalUpload,
    /// ↗ Teilen: Programme zur Auswahl
    GalShare,
    /// ⓘ Info
    GalInfo,
    /// ↗ an dieses Programm (Schlüssel wie in core/share.py)
    ShareTo(String),
    /// aus Teilen / Info zurück zum Foto
    SubBack,
}

/// Hauptseiten (◀ ▶ unten)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Page {
    #[default]
    Translate,
    Gallery,
}

pub const PAGES: [Page; 2] = [Page::Translate, Page::Gallery];

impl Page {
    /// Nächste Seite (step = ±1, im Kreis)
    pub fn step(self, step: i32) -> Page {
        let i = PAGES.iter().position(|p| *p == self).unwrap_or(0) as i32;
        PAGES[(i + step).rem_euclid(PAGES.len() as i32) as usize]
    }

    /// Name in panel_sizes.json ("translate" / "gallery")
    pub fn key(self) -> &'static str {
        match self {
            Page::Translate => "translate",
            Page::Gallery => "gallery",
        }
    }

    pub fn from_key(key: &str) -> Page {
        PAGES.into_iter().find(|p| p.key() == key).unwrap_or_default()
    }

    fn title_key(self) -> &'static str {
        match self {
            Page::Translate => "vr_page_translate",
            Page::Gallery => "nav_gallery",
        }
    }
}

/// Eine Kachel im Galerie-Raster
#[derive(Clone, Debug, PartialEq)]
pub struct Tile {
    /// Nummer in der Foto-Liste (neueste = 0)
    pub index: usize,
    pub path: PathBuf,
    pub mtime: Option<std::time::SystemTime>,
}

/// Zeile im Galerie-Raster: Monats-Trenner oder Kacheln (Nummern in der Foto-Liste)
#[derive(Clone, Debug, PartialEq)]
pub enum GRow {
    Month(String),
    Tiles(Vec<usize>),
}

/// Unter-Ansicht des großen Fotos
#[derive(Clone, Debug, PartialEq)]
pub enum Sub {
    /// ↗ Teilen: (Schlüssel, Name) der installierten Programme
    Share(Vec<(String, String)>),
    /// ⓘ Info: (Bezeichnung, Wert)
    Info(Vec<(String, String)>),
}

/// Foto in der Einzelansicht
#[derive(Clone, Debug, PartialEq)]
pub struct OpenPhoto {
    pub index: usize,
    pub path: PathBuf,
    pub mtime: Option<std::time::SystemTime>,
    /// 🗑 einmal angetippt
    pub confirm: bool,
    /// „2026 Oktober“
    pub month: String,
    /// Rückmeldung („✔ Link kopiert“)
    pub toast: String,
    /// ☁ lädt gerade hoch
    pub uploading: bool,
    /// schon hochgeladen → Knopf „🔗 Link kopieren“
    pub uploaded: bool,
    pub sub: Option<Sub>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct GalleryView {
    /// Fotos insgesamt
    pub total: usize,
    /// Raster-Seite (0, 1, …) und Anzahl Seiten
    pub page: usize,
    pub pages: usize,
    /// Zeilen dieser Seite
    pub rows: Vec<GRow>,
    /// Kacheln dieser Seite (Reihenfolge wie in `rows`) – passend zu `Pics::thumbs`
    pub tiles: Vec<Tile>,
    pub open: Option<OpenPhoto>,
}

/// Fertig verkleinerte Bilder fürs Zeichnen (Foto mit Nummern, Kacheln, großes Foto)
#[derive(Default)]
pub struct Pics<'a> {
    pub photo: Option<&'a image::RgbaImage>,
    /// zu `GalleryView::tiles` passend
    pub thumbs: Vec<Option<&'a image::RgbaImage>>,
    pub big: Option<&'a image::RgbaImage>,
}

/// Einträge einer Auswahl-Liste: (Wert, Text, gewählt). Wert HEADER = Überschrift (nicht wählbar)
pub type Items = Vec<(String, String, bool)>;
/// Wert einer Überschrift-Zeile in Auswahl-Listen („── KI-Übersetzung ──“)
pub const HEADER: &str = "\u{1}header";
/// Klick-Flächen: ([x, y, w, h], Knopf)
pub type Hits = Vec<([f32; 4], Action)>;

/// ⚙ Einstellungen (Werte aus layer.json / panel_pose.json)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Sheet {
    pub width_cm: Option<i32>,
    pub anchor: String,
    pub detect: String,
    pub shutter: String,
    pub mode_button: String,
    /// 🔘 Knopf an, nach Foto öffnen, Größe (cm, None = noch nie in VR), Farbe
    pub button: bool,
    pub open_on_shot: bool,
    pub button_cm: Option<i32>,
    pub color: String,
    /// Größe gilt für diese Seite („Größe · Galerie“)
    pub page_name: String,
}

/// Alles, was man im Panel sieht
#[derive(Clone, Debug, Default, PartialEq)]
pub struct View {
    pub lang: String,
    pub method_label: String,
    pub source_label: String,
    pub target_label: String,
    pub mode_label: Option<String>,
    pub last_ai: String,
    pub edit: bool,
    pub opacity: i32,
    pub photo: Option<PathBuf>,
    pub photo_mtime: Option<std::time::SystemTime>,
    pub lines: Vec<Line>,
    pub result: String,
    pub result_page: usize,
    pub status: String,
    /// Auswahl-Liste offen: (was, Titel, [(Wert, Text, gewählt)])
    pub choosing: Option<(Choice, String, Items)>,
    /// Modus 🤖/✋ in der Dienst-Auswahl (nur mit KI als Main): aktueller Modus
    pub route: Option<String>,
    /// ⚙ Einstellungen offen
    pub sheet: Option<Sheet>,
    pub fixed_height: Option<f32>,
    /// Hauptseite: Übersetzung / Galerie
    pub page: Page,
    pub gallery: Option<GalleryView>,
}

pub fn number(i: usize) -> String {
    NUMBERS.chars().nth(i).map(String::from).unwrap_or_else(|| format!("({})", i + 1))
}

/// Übersetzung passend zu den Nummern im Foto (wie vr_panel.numbered)
pub fn numbered(lines: &[Line], translated: &str) -> String {
    if translated.is_empty() {
        return String::new();
    }
    match crate::overlay::pair_lines(lines, translated) {
        Some(pairs) => pairs.iter().enumerate().map(|(i, (_, t))| format!("{}  {t}", number(i))).collect::<Vec<_>>().join("\n"),
        None => {
            let re = regex::Regex::new(r"(?m)^(\s*➜\s*)(\d{1,2})[).:]\s*").unwrap();
            re.replace_all(translated.trim(), |c: &regex::Captures| {
                let n: usize = c[2].parse().unwrap_or(1);
                format!("{}{} ", &c[1], number(n.saturating_sub(1)))
            })
            .to_string()
        }
    }
}

struct Layout<'a> {
    f: &'a mut Fonts,
    c: Option<&'a mut Canvas>,
    hits: Vec<([f32; 4], Action)>,
    pages: usize,
    /// linker Rand des Inhalts (mit ◀ ▶ am Rand breiter)
    mx: f32,
}

impl Layout<'_> {
    /// Ausgegrauter Knopf (z. B. ‹ beim ersten Foto) – sichtbar, aber ohne Klick-Fläche
    fn dead_button(&mut self, text: &str, x: f32, y: f32, w: f32) {
        if let Some(c) = self.c.as_deref_mut() {
            c.rounded(x + 0.5, y + 0.5, w - 1.0, BTN_H - 1.0, 8.0, Some(rgba(0x1b1f28, 255)), Some((rgba(0x262b35, 255), 1.0)));
            let st = Style::new(20.0, true, 0x3a4050);
            let (tw, th) = measure(self.f, text, None, st);
            c.text(self.f, text, x + ((w - tw) / 2.0).max(8.0), y + (BTN_H - th) / 2.0, Some(w - 16.0), st);
        }
    }

    fn button(&mut self, text: &str, x: f32, y: f32, w: f32, primary: bool, action: Action) {
        if let Some(c) = self.c.as_deref_mut() {
            let (bg, border, fg) = if primary { (BLUE, BLUE, 0xffffff) } else { (BTN_BG, BTN_BORDER, BTN_TEXT) };
            c.rounded(x + 0.5, y + 0.5, w - 1.0, BTN_H - 1.0, 8.0, Some(rgba(bg, 255)), Some((rgba(border, 255), 1.0)));
            // zu lang für den Knopf → etwas kleiner statt umbrechen
            let mut st = Style::new(20.0, true, fg);
            while st.size > 14.0 && measure(self.f, text, None, st).0 > w - 16.0 {
                st = Style::new(st.size - 1.0, true, fg);
            }
            let (tw, th) = measure(self.f, text, None, st);
            c.text(self.f, text, x + ((w - tw) / 2.0).max(8.0), y + (BTN_H - th) / 2.0, Some(w - 16.0), st);
        }
        self.hits.push(([x, y, w, BTN_H], action));
    }

    fn btn_width(&mut self, text: &str) -> f32 {
        measure(self.f, text, None, Style::new(20.0, true, BTN_TEXT)).0 + 32.0
    }

    fn label(&mut self, text: &str, x: f32, y: f32, w: f32, st: Style) -> f32 {
        if text.is_empty() {
            return 0.0;
        }
        match self.c.as_deref_mut() {
            Some(c) => c.text(self.f, text, x, y, Some(w), st),
            None => measure(self.f, text, Some(w), st).1,
        }
    }

    /// Nebeneinander liegende Knöpfe, der gewählte ist blau. Gibt die Unterkante zurück.
    fn choices(&mut self, y: f32, items: &[(String, String)], chosen: &str, make: impl Fn(&str) -> Action) -> f32 {
        let inner = WIDTH - 2.0 * self.mx;
        let gap = 6.0;
        let w = (inner - gap * (items.len() as f32 - 1.0)) / items.len() as f32;
        for (i, (value, text)) in items.iter().enumerate() {
            self.button(text, self.mx + i as f32 * (w + gap), y, w, value == chosen, make(value));
        }
        y + BTN_H
    }

    /// Schieber (Klick irgendwo auf die Leiste = dieser Wert)
    fn bar(&mut self, y: f32, frac: f32, enabled: bool, which: Bar) -> f32 {
        let mx = self.mx;
        let inner = WIDTH - 2.0 * mx;
        if let Some(c) = self.c.as_deref_mut() {
            let (x, w) = (mx + BAR_PAD, inner - 2.0 * BAR_PAD);
            let cy = y + BAR_H / 2.0;
            c.rounded(x, cy - 5.0, w, 10.0, 5.0, Some(rgba(0x2c313c, 255)), None);
            if enabled {
                c.rounded(x, cy - 5.0, (w * frac).max(10.0), 10.0, 5.0, Some(rgba(BLUE, 255)), None);
                c.circle(x + w * frac, cy, 14.0, rgba(0xe8ecf2, 255));
            }
        }
        if enabled {
            self.hits.push(([mx, y, inner, BAR_H], Action::Bar(which)));
        }
        y + BAR_H
    }
}

/// Foto (verkleinert) mit blauen Nummern ①②③ auf den Zeilen – teuer, der Dienst merkt es sich
pub fn photo_with_numbers(f: &mut Fonts, photo: &std::path::Path, lines: &[Line], width: f32) -> Option<image::RgbaImage> {
    let img = image::open(photo).ok()?;
    let scale = (width / img.width() as f32).min(PHOTO_MAX_H / img.height() as f32);
    let (w, h) = ((img.width() as f32 * scale).round().max(1.0) as u32, (img.height() as f32 * scale).round().max(1.0) as u32);
    Some(img.resize_exact(w, h, image::imageops::FilterType::Triangle).to_rgba8()).map(|mut small| {
        let boxes: Vec<[i64; 4]> = lines.iter().filter_map(|l| l.r#box).collect();
        if boxes.is_empty() {
            return small;
        }
        // Nummern auf ein eigenes Bild zeichnen und darüberlegen
        let Some(mut c) = Canvas::new(w, h) else { return small };
        c.image(&small, 0, 0);
        let size = (h as f32 / 10.0).clamp(18.0, 30.0);
        for (i, b) in boxes.iter().enumerate() {
            let (x0, y0, x1, y1) = (b[0] as f32 * scale, b[1] as f32 * scale, b[2] as f32 * scale, b[3] as f32 * scale);
            c.rect_outline(x0, y0, x1 - x0, y1 - y0, tiny_skia::Color::from_rgba8(70, 150, 255, 200), 1.0);
            let cx = (x0 - size * 0.6).max(size / 2.0);
            let cy = (y0 + y1) / 2.0;
            c.circle(cx, cy, size / 2.0, tiny_skia::Color::from_rgba8(70, 150, 255, 255));
            let st = Style::new((size * 0.62).round(), true, 0xffffff);
            let label = (i + 1).to_string();
            let (tw, th) = measure(f, &label, None, st);
            c.text(f, &label, cx - tw / 2.0, cy - th / 2.0, None, st);
        }
        for (i, px) in c.pix.pixels().iter().enumerate() {
            let d = px.demultiply();
            let (x, y) = (i as u32 % w, i as u32 / w);
            small.put_pixel(x, y, image::Rgba([d.red(), d.green(), d.blue(), d.alpha()]));
        }
        small
    })
}

/// Panel zeichnen. Gibt Bild, Klick-Flächen und Anzahl der Übersetzungs-Seiten zurück.
pub fn render(f: &mut Fonts, v: &View, pics: &Pics) -> Option<(Canvas, Hits, usize)> {
    // 1. Durchgang: Höhe messen, 2.: zeichnen
    let nav = shows_nav(v);
    let height = {
        let mut l = Layout { f, c: None, hits: Vec::new(), pages: 1, mx: MX };
        content(&mut l, v, pics) + if nav { GAP + NAV_H } else { 0.0 }
    };
    let gallery_grid = nav && v.page == Page::Gallery;
    let auto_h = if gallery_grid { GALLERY_H } else { (height + MY).max(200.0) };
    let h = v.fixed_height.unwrap_or(auto_h).round();
    let mut canvas = Canvas::new(WIDTH as u32, h as u32)?;
    canvas.rounded(1.0, 1.0, WIDTH - 2.0, h - 2.0, 16.0, Some(rgba(BG, 255)), Some((rgba(0x2b3240, 255), 2.0)));
    let (hits, pages) = {
        let mut l = Layout { f, c: Some(&mut canvas), hits: Vec::new(), pages: 1, mx: MX };
        content(&mut l, v, pics);
        if nav {
            nav_row(&mut l, v, h - MY - NAV_H);
        }
        (l.hits, l.pages)
    };
    canvas.fade(v.opacity.clamp(30, 100) as f32 / 100.0);
    Some((canvas, hits, pages))
}

/// Inhalt – gibt die Unterkante zurück
fn content(l: &mut Layout, v: &View, pics: &Pics) -> f32 {
    let lang = v.lang.as_str();
    let inner = WIDTH - 2.0 * MX;
    let mut y = MY;
    let title = Style::new(24.0, true, TEXT);
    l.mx = MX;
    if let Some(sheet) = &v.sheet {
        return sheet_content(l, v, sheet);
    }
    if let Some((which, title_text, items)) = &v.choosing {
        let back = format!("←  {}", tr(lang, "back", &[]));
        let bw = l.btn_width(&back);
        l.button(&back, MX, y, bw, false, Action::Back);
        let th = measure(l.f, title_text, None, title).1;
        l.label(title_text, MX + bw + 12.0, y + (BTN_H - th) / 2.0, inner - bw - 12.0, title);
        y += BTN_H + GAP;
        if *which == Choice::Method {
            if let Some(route) = &v.route {
                let items = [("auto".to_string(), tr(lang, "tr_route_auto", &[])), ("manual".to_string(), tr(lang, "tr_route_manual", &[]))];
                y = l.choices(y, &items, route, |r| Action::Route(r.to_string())) + GAP;
            }
        }
        let st = Style::new(22.0, false, TEXT);
        for (value, text, chosen) in items.iter() {
            if value == HEADER {
                // Überschrift: grau, schmaler, nicht anklickbar
                let hs = Style::new(17.0, false, SECTION);
                let hh = 40.0;
                let label = format!("──  {text}  ──");
                let th = measure(l.f, &label, None, hs).1;
                l.label(&label, MX + 10.0, y + (hh - th) / 2.0, inner - 20.0, hs);
                y += hh;
                continue;
            }
            let shown = format!("{}{text}", if *chosen { "✔  " } else { "     " });
            if let Some(c) = l.c.as_deref_mut() {
                if *chosen {
                    c.rounded(MX, y, inner, ITEM_H, 6.0, Some(rgba(0x2a2f3a, 255)), None);
                }
                let th = measure(l.f, &shown, None, st).1;
                c.text(l.f, &shown, MX + 10.0, y + (ITEM_H - th) / 2.0, Some(inner - 20.0), st);
            }
            l.hits.push(([MX, y, inner, ITEM_H], Action::Pick(*which, value.clone())));
            y += ITEM_H;
        }
        return y;
    }
    // ein Foto groß (+ Teilen / Info)
    if v.page == Page::Gallery && v.gallery.as_ref().is_some_and(|g| g.open.is_some()) {
        return single_content(l, v, pics);
    }
    // Hauptseiten – ⚙ bleibt oben, ◀ ▶ zeichnet render() ganz unten
    match v.page {
        Page::Translate => translate_content(l, v, pics.photo),
        Page::Gallery => gallery_content(l, v, pics),
    }
}

/// ◀ ▶-Zeile unten nur auf den Hauptseiten (nicht in ⚙, Auswahl-Liste, Foto groß)
fn shows_nav(v: &View) -> bool {
    v.sheet.is_none() && v.choosing.is_none() && !v.gallery.as_ref().is_some_and(|g| g.open.is_some())
}

/// Ganz unten: [◀ Galerie]   ● ○   [Galerie ▶]
fn nav_row(l: &mut Layout, v: &View, y: f32) {
    let lang = v.lang.as_str();
    let (prev, next) = (v.page.step(-1), v.page.step(1));
    for (text, x, step) in [
        (format!("◀  {}", tr(lang, prev.title_key(), &[])), MX, -1),
        (format!("{}  ▶", tr(lang, next.title_key(), &[])), WIDTH - MX - NAV_W, 1),
    ] {
        if let Some(c) = l.c.as_deref_mut() {
            c.rounded(x + 0.5, y + 0.5, NAV_W - 1.0, NAV_H - 1.0, 12.0, Some(rgba(BTN_BG, 255)), Some((rgba(0x3a4252, 255), 1.0)));
            let st = Style::new(21.0, true, BTN_TEXT);
            let (tw, th) = measure(l.f, &text, None, st);
            c.text(l.f, &text, x + (NAV_W - tw) / 2.0, y + (NAV_H - th) / 2.0, None, st);
        }
        l.hits.push(([x, y, NAV_W, NAV_H], Action::Nav(step)));
    }
    if let Some(c) = l.c.as_deref_mut() {
        // ● ○ – welche Seite gerade offen ist
        let n = PAGES.len() as f32;
        let x0 = WIDTH / 2.0 - (n - 1.0) * 16.0;
        for (i, p) in PAGES.iter().enumerate() {
            let cx = x0 + i as f32 * 32.0;
            let cy = y + NAV_H / 2.0;
            c.circle(cx, cy, 7.0, rgba(BLUE, 255));
            if *p != v.page {
                c.circle(cx, cy, 5.0, rgba(BG, 255));
            }
        }
    }
}

/// 🌐 Übersetzungs-Seite – gibt die Unterkante zurück
fn translate_content(l: &mut Layout, v: &View, photo: Option<&image::RgbaImage>) -> f32 {
    let (mx, lang) = (l.mx, v.lang.as_str());
    let inner = WIDTH - 2.0 * mx;
    let mut y = MY;
    let title = Style::new(24.0, true, TEXT);

    // Kopf: 🌐 ViewShot  [⚙]
    l.button("⚙", mx + inner - TIP_W, y, TIP_W, false, Action::Sheet);
    let th = measure(l.f, "🌐  ViewShot", None, title).1;
    l.label("🌐  ViewShot", mx, y + (BTN_H - th) / 2.0, inner - TIP_W - 8.0, title);
    y += BTN_H + GAP;

    // [Dienst ▸] [↻]
    let rw = l.btn_width("↻");
    l.button(&format!("{}  ▸", v.method_label), mx, y, inner - rw - 8.0, false, Action::Choose(Choice::Method));
    l.button("↻", mx + inner - rw, y, rw, false, Action::Redo);
    y += BTN_H + GAP;

    // [Von ▸] → [Nach ▸]
    let arrow = Style::new(20.0, false, TEXT);
    let aw = measure(l.f, "→", None, arrow).0 + 16.0;
    let half = (inner - aw) / 2.0;
    l.button(&format!("{}  ▸", v.source_label), mx, y, half, false, Action::Choose(Choice::Source));
    l.label("→", mx + half + 8.0, y + 12.0, aw, arrow);
    l.button(&format!("{}  ▸", v.target_label), mx + half + aw, y, half, false, Action::Choose(Choice::Target));
    y += BTN_H + GAP;

    if let Some(mode) = &v.mode_label {
        l.button(&format!("{mode}  ▸"), mx, y, inner, false, Action::Choose(Choice::Mode));
        y += BTN_H + GAP;
    }
    let dim = Style::new(16.0, false, DIM);
    let last = format!("{}:  {}", tr(lang, "tr_last_ai", &[]), v.last_ai);
    y += l.label(&last, mx, y, inner, dim) + GAP;
    if v.edit {
        y += l.label(&format!("✥  {}", tr(lang, "panel_edit_help", &[])), mx, y, inner, dim) + GAP;
    }

    if let Some(img) = photo {
        if let Some(c) = l.c.as_deref_mut() {
            c.image(img, (mx + (inner - img.width() as f32) / 2.0).round() as i32, y as i32);
        }
        y += img.height() as f32 + GAP;
    }
    let result = numbered(&v.lines, &v.result);
    let result = if result.is_empty() && v.status.starts_with('⏳') { "…".to_string() } else { result };
    if !result.is_empty() {
        // lange Übersetzung → Seiten (▼ / ▲)
        let st = Style::new(22.0, false, TEXT);
        let lh = line_height(st);
        let status_h = if v.status.is_empty() { 0.0 } else { measure(l.f, &v.status, Some(inner), dim).1 + GAP };
        let max_h = match v.fixed_height {
            Some(fh) => (fh - MY - y - status_h - BTN_H - GAP - (NAV_H + GAP)).max(lh * 2.0),
            None => RESULT_MAX_H,
        };
        let lines = wrap_lines(l.f, &result, inner, st);
        let pages = paginate(&lines, (max_h / lh).floor().max(1.0) as usize);
        l.pages = pages.len();
        let page = v.result_page.min(pages.len() - 1);
        y += l.label(&pages[page], mx, y, inner, st) + GAP;
        if pages.len() > 1 {
            let bw = (inner - 90.0 - 16.0) / 2.0;
            if page > 0 {
                l.button("▲", mx, y, bw, false, Action::Page(-1));
            } else {
                l.dead_button("▲", mx, y, bw);
            }
            let info = format!("{} / {}", page + 1, pages.len());
            let (iw, ih) = measure(l.f, &info, None, dim);
            l.label(&info, mx + bw + 8.0 + (90.0 - iw) / 2.0, y + (BTN_H - ih) / 2.0, 90.0, dim);
            if page + 1 < pages.len() {
                l.button("▼", mx + inner - bw, y, bw, false, Action::Page(1));
            } else {
                l.dead_button("▼", mx + inner - bw, y, bw);
            }
            y += BTN_H + GAP;
        }
    }
    let sh = l.label(&v.status, mx, y, inner, dim);
    if sh > 0.0 {
        y += sh;
    }
    y
}

/// Kopfzeile: Titel … [extra] [⚙] – gibt die x-Position links von ⚙ zurück
fn head_row(l: &mut Layout, title: &str, y: f32) -> f32 {
    let inner = WIDTH - 2.0 * MX;
    let st = Style::new(24.0, true, TEXT);
    l.button("⚙", MX + inner - TIP_W, y, TIP_W, false, Action::Sheet);
    let th = measure(l.f, title, None, st).1;
    l.label(title, MX, y + (BTN_H - th) / 2.0, inner - TIP_W - 8.0, st);
    MX + inner - TIP_W - 8.0
}

/// Monats-Trenner „──── 2026 Oktober ────“
fn month_row(l: &mut Layout, text: &str, y: f32) {
    let inner = WIDTH - 2.0 * MX;
    let st = Style::new(18.0, true, 0xc7cdd6);
    let (tw, th) = measure(l.f, text, None, st);
    if let Some(c) = l.c.as_deref_mut() {
        let tx = MX + (inner - tw) / 2.0;
        let cy = y + MONTH_H / 2.0;
        c.rounded(MX, cy - 1.0, (tx - MX - 12.0).max(0.0), 2.0, 1.0, Some(rgba(0x333947, 255)), None);
        c.rounded(tx + tw + 12.0, cy - 1.0, (MX + inner - tx - tw - 12.0).max(0.0), 2.0, 1.0, Some(rgba(0x333947, 255)), None);
        c.text(l.f, text, tx, y + (MONTH_H - th) / 2.0, None, st);
    }
}

/// 🖼 Galerie-Seite: Raster mit Monats-Trennern über die ganze Fläche – gibt die Unterkante zurück
fn gallery_content(l: &mut Layout, v: &View, pics: &Pics) -> f32 {
    let lang = v.lang.as_str();
    let inner = WIDTH - 2.0 * MX;
    let mut y = MY;
    let left = head_row(l, &format!("🖼  {}", tr(lang, "nav_gallery", &[])), y);
    let Some(g) = &v.gallery else { return y + BTN_H + GAP };
    // viele Fotos: [▲] 1 / 3 [▼] oben neben ⚙ – unten bleibt frei für ◀ ▶
    if g.pages > 1 {
        let dim = Style::new(16.0, false, DIM);
        let info = format!("{} / {}", g.page + 1, g.pages);
        let iw = 70.0;
        let down_x = left - TIP_W;
        let info_x = down_x - 8.0 - iw;
        let up_x = info_x - 8.0 - TIP_W;
        if g.page > 0 {
            l.button("▲", up_x, y, TIP_W, false, Action::GalPage(-1));
        } else {
            l.dead_button("▲", up_x, y, TIP_W);
        }
        let (tw, th) = measure(l.f, &info, None, dim);
        l.label(&info, info_x + (iw - tw) / 2.0, y + (BTN_H - th) / 2.0, iw, dim);
        if g.page + 1 < g.pages {
            l.button("▼", down_x, y, TIP_W, false, Action::GalPage(1));
        } else {
            l.dead_button("▼", down_x, y, TIP_W);
        }
    }
    y += BTN_H + GAP;
    if g.total == 0 {
        return y + l.label(&tr(lang, "no_photo", &[]), MX, y, inner, Style::new(16.0, false, DIM));
    }
    let (cw, ch) = tile_size();
    let (cw, ch) = (cw as f32, ch as f32);
    let mut n = 0;
    for row in &g.rows {
        match row {
            GRow::Month(text) => {
                month_row(l, text, y);
                y += MONTH_H + GRID_GAP;
            }
            GRow::Tiles(indices) => {
                for (c, index) in indices.iter().enumerate() {
                    let x = MX + c as f32 * (cw + GRID_GAP);
                    if let Some(canvas) = l.c.as_deref_mut() {
                        canvas.rounded(x + 1.0, y + 1.0, cw - 2.0, ch - 2.0, 8.0, Some(rgba(0x14161c, 255)), Some((rgba(0x2b3240, 255), 2.0)));
                        if let Some(Some(img)) = pics.thumbs.get(n) {
                            canvas.image(img, (x + 2.0) as i32, (y + 2.0) as i32);
                        }
                    }
                    l.hits.push(([x, y, cw, ch], Action::GalOpen(*index)));
                    n += 1;
                }
                y += ch + GRID_GAP;
            }
        }
    }
    y
}

/// Ein Foto groß – mit allen Aktionen wie in der Desktop-Galerie; gibt die Unterkante zurück
fn single_content(l: &mut Layout, v: &View, pics: &Pics) -> f32 {
    let lang = v.lang.as_str();
    let t = |k: &str| tr(lang, k, &[]);
    let inner = WIDTH - 2.0 * MX;
    let mut y = MY;
    let (Some(g), true) = (&v.gallery, v.page == Page::Gallery) else { return y };
    let Some(open) = &g.open else { return y };
    let title = Style::new(24.0, true, TEXT);
    let gap = 8.0;

    // ↗ Teilen / ⓘ Info
    if let Some(sub) = &open.sub {
        let back = format!("←  {}", t("back"));
        let bw = l.btn_width(&back);
        l.button(&back, MX, y, bw, false, Action::SubBack);
        let head = match sub {
            Sub::Share(_) => format!("↗  {}", t("share")),
            Sub::Info(_) => format!("ⓘ  {}", t("info")),
        };
        let th = measure(l.f, &head, None, title).1;
        l.label(&head, MX + bw + 12.0, y + (BTN_H - th) / 2.0, inner - bw - 12.0, title);
        y += BTN_H + GAP;
        match sub {
            Sub::Share(targets) => {
                if targets.is_empty() {
                    y += l.label(&t("vr_share_none"), MX, y, inner, Style::new(16.0, false, DIM)) + GAP;
                }
                for (key, name) in targets {
                    l.button(name, MX, y, inner, false, Action::ShareTo(key.clone()));
                    y += BTN_H + gap;
                }
            }
            Sub::Info(rows) => {
                let ks = Style::new(17.0, false, SECTION);
                let vs = Style::new(19.0, false, TEXT);
                let kw = rows.iter().map(|(k, _)| measure(l.f, k, None, ks).0).fold(0.0, f32::max) + 14.0;
                for (k, val) in rows {
                    l.label(k, MX, y + 2.0, kw, ks);
                    let h = l.label(val, MX + kw, y, inner - kw, vs).max(24.0);
                    y += h + gap;
                }
            }
        }
        return y;
    }

    let stem = open.path.file_stem().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let name = stem.strip_prefix("ViewShot_").unwrap_or(&stem).to_string();
    head_row(l, &name, y);
    y += BTN_H + GAP;
    if let Some(img) = pics.big {
        if let Some(c) = l.c.as_deref_mut() {
            c.image(img, (MX + (inner - img.width() as f32) / 2.0).round() as i32, y as i32);
        }
        y += img.height() as f32 + GAP;
    }
    let dim = Style::new(16.0, false, DIM);
    let info = format!("{} / {}   ·   {}", open.index + 1, g.total, open.month);
    let (iw, ih) = measure(l.f, &info, None, dim);
    l.label(&info, MX + (inner - iw) / 2.0, y, iw + 4.0, dim);
    y += ih + GAP;
    if !open.toast.is_empty() {
        let st = Style::new(18.0, true, 0x6fae72);
        let (tw, _) = measure(l.f, &open.toast, None, st);
        let w = tw.min(inner);
        y += l.label(&open.toast, MX + (inner - w) / 2.0, y, inner, st) + GAP;
    }

    let third = (inner - 2.0 * gap) / 3.0;
    let col = |i: usize| MX + i as f32 * (third + gap);
    // [‹]  [← Zurück]  [›]
    if open.index > 0 {
        l.button("‹", col(0), y, third, false, Action::GalStep(-1));
    } else {
        l.dead_button("‹", col(0), y, third);
    }
    l.button(&format!("←  {}", t("back")), col(1), y, third, false, Action::GalBack);
    if open.index + 1 < g.total {
        l.button("›", col(2), y, third, false, Action::GalStep(1));
    } else {
        l.dead_button("›", col(2), y, third);
    }
    y += BTN_H + gap;
    // [📋 Kopieren] [☁ Hochladen + Link] [↗ Teilen]
    l.button(&format!("📋  {}", t("copy")), col(0), y, third, false, Action::GalCopy);
    if open.uploading {
        l.dead_button(&format!("⏳  {}", t("uploading")), col(1), y, third);
    } else if open.uploaded {
        l.button(&format!("🔗  {}", t("copy_link")), col(1), y, third, false, Action::GalUpload);
    } else {
        l.button(&format!("☁  {}", t("upload_copy_link")), col(1), y, third, false, Action::GalUpload);
    }
    l.button(&format!("↗  {}", t("share")), col(2), y, third, false, Action::GalShare);
    y += BTN_H + gap;
    // [🌐 Übersetzen] [ⓘ Info] [🗑 Löschen]
    l.button(&format!("🌐  {}", t("translate_btn")), col(0), y, third, false, Action::GalTranslate);
    l.button(&format!("ⓘ  {}", t("info")), col(1), y, third, false, Action::GalInfo);
    let del = format!("🗑  {}", t(if open.confirm { "vr_delete_sure" } else { "delete" }));
    l.button(&del, col(2), y, third, open.confirm, Action::GalDelete);
    y + BTN_H
}

/// Breite des Inhalts
pub fn content_w() -> f32 {
    WIDTH - 2.0 * MX
}

/// Größe einer Kachel im Galerie-Raster (außen, mit Rand) – wie VRPanel.tile_size
pub fn tile_size() -> (u32, u32) {
    let w = ((content_w() - (GRID_COLS as f32 - 1.0) * GRID_GAP) / GRID_COLS as f32).floor();
    (w as u32, (w * THUMB_RATIO).round() as u32)
}

/// Platz für das Raster: Panel-Höhe minus Rand, Kopf und ◀ ▶-Zeile (wie VRPanel.grid_height)
pub fn grid_room(fixed_height: Option<f32>) -> f32 {
    let ch = tile_size().1 as f32;
    (fixed_height.unwrap_or(GALLERY_H) - 2.0 * MY - (BTN_H + GAP) - (NAV_H + GAP)).max(MONTH_H + ch)
}

/// Fotos (Monat je Foto, neueste zuerst) → Raster-Seiten wie VRPanel.gallery_pages:
/// Zeilen mit bis zu GRID_COLS Fotos desselben Monats, ein Trenner je Monat; geht ein
/// Monat auf der nächsten Seite weiter, steht sein Trenner dort nochmal oben.
pub fn gallery_pages(months: &[(i32, u32)], titles: impl Fn(i32, u32) -> String, room: f32) -> Vec<Vec<GRow>> {
    let ch = tile_size().1 as f32;
    let mut rows: Vec<((i32, u32), Vec<usize>)> = Vec::new();
    for (i, ym) in months.iter().enumerate() {
        match rows.last_mut() {
            Some((m, cur)) if m == ym && cur.len() < GRID_COLS => cur.push(i),
            _ => rows.push((*ym, vec![i])),
        }
    }
    let mut pages: Vec<Vec<GRow>> = Vec::new();
    let mut page: Vec<GRow> = Vec::new();
    let (mut used, mut last): (f32, Option<(i32, u32)>) = (0.0, None);
    for (ym, row) in rows {
        let mut need = ch + if Some(ym) != last || page.is_empty() { MONTH_H + GRID_GAP } else { 0.0 };
        if !page.is_empty() && used + need > room {
            pages.push(std::mem::take(&mut page));
            used = 0.0;
            last = None;
            need = ch + MONTH_H + GRID_GAP;
        }
        if Some(ym) != last {
            page.push(GRow::Month(titles(ym.0, ym.1)));
        }
        page.push(GRow::Tiles(row));
        used += need + GRID_GAP;
        last = Some(ym);
    }
    if !page.is_empty() {
        pages.push(page);
    }
    if pages.is_empty() {
        pages.push(Vec::new());
    }
    pages
}

/// Größe, in die das Foto in der Einzelansicht passt (volle Breite)
pub fn single_size() -> (u32, u32) {
    (content_w() as u32, SINGLE_MAX_H as u32)
}

/// Vorschaubild w × h: Mitte ausgeschnitten, damit alle Kacheln gleich groß sind
pub fn thumb(path: &std::path::Path, w: u32, h: u32) -> Option<image::RgbaImage> {
    let img = image::open(path).ok()?;
    Some(img.resize_to_fill(w, h, image::imageops::FilterType::Triangle).to_rgba8())
}

/// Foto so verkleinert/vergrößert, dass es in w × h passt (Seitenverhältnis bleibt)
pub fn fit_photo(path: &std::path::Path, w: u32, h: u32) -> Option<image::RgbaImage> {
    Some(fit_image(image::open(path).ok()?, w, h))
}

/// Bild so verkleinert/vergrößert, dass es in w × h passt (🎞 GIF: jedes Einzelbild)
pub fn fit_image(img: image::DynamicImage, w: u32, h: u32) -> image::RgbaImage {
    let scale = (w as f32 / img.width() as f32).min(h as f32 / img.height() as f32);
    let (nw, nh) = ((img.width() as f32 * scale).round().max(1.0) as u32, (img.height() as f32 * scale).round().max(1.0) as u32);
    img.resize_exact(nw, nh, image::imageops::FilterType::Triangle).to_rgba8()
}

/// 🔘 Ist das Panel in VR aufgeklappt? (panel_state.json schreibt der Layer; fehlt = ja)
pub fn is_open() -> bool {
    std::fs::read_to_string(crate::paths::config_dir().join("panel_state.json"))
        .ok()
        .and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok())
        .and_then(|v| v["open"].as_bool())
        .unwrap_or(true)
}

/// 🎞 GIF Bild für Bild lesen (nur das aktuelle Bild liegt im Speicher)
pub type GifFrames = image::Frames<'static>;

pub fn gif_frames(path: &std::path::Path) -> Option<GifFrames> {
    use image::AnimationDecoder;
    let file = std::io::BufReader::new(std::fs::File::open(path).ok()?);
    Some(image::codecs::gif::GifDecoder::new(file).ok()?.into_frames())
}

/// panel_sizes.json: Größe je Seite + aktuelle Seite (gleiche Datei wie vr_panel.switch_page_size)
pub fn sizes_file() -> PathBuf {
    crate::paths::config_dir().join("panel_sizes.json")
}

/// Welche Seite zuletzt offen war (App und Dienst machen dort weiter)
pub fn current_page() -> Page {
    std::fs::read_to_string(sizes_file())
        .ok()
        .and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok())
        .and_then(|v| v["page"].as_str().map(Page::from_key))
        .unwrap_or_default()
}

/// Seite wechseln: Größe der alten Seite merken, die der neuen in panel_pose.json schreiben
/// (der Layer liest sie sofort). Gibt es panel_pose.json noch nicht, wird nur die Seite gemerkt.
pub fn switch_page_size(old: Page, new: Page) {
    use serde_json::{json, Value};
    let file = sizes_file();
    let mut sizes = std::fs::read_to_string(&file)
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}));
    sizes["page"] = json!(new.key());
    let pose_file = crate::paths::panel_pose_file();
    let pose = std::fs::read_to_string(&pose_file).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok());
    if let (Some(mut pose), true) = (pose, old != new) {
        if let Some(width) = pose["width"].as_f64() {
            sizes[old.key()] = json!({"width": width, "height": pose.get("height").cloned().unwrap_or(Value::Null)});
            let default = PAGE_SIZE_DEFAULT.iter().find(|(k, _)| *k == new.key()).map(|d| d.1).unwrap_or(0.32);
            let target_w = sizes[new.key()]["width"].as_f64().unwrap_or(default);
            let (lo, hi) = (SIZE_CM.0 as f64 / 100.0, SIZE_CM.1 as f64 / 100.0);
            pose["width"] = json!(target_w.clamp(lo, hi));
            match sizes[new.key()]["height"].as_f64() {
                Some(h) => pose["height"] = json!(h),
                None => {
                    if let Some(map) = pose.as_object_mut() {
                        map.remove("height"); // Höhe automatisch (so hoch wie der Inhalt)
                    }
                }
            }
            let _ = crate::settings::write_json(&pose_file, &pose, 2);
        }
    }
    let _ = crate::settings::write_json(&file, &sizes, 2);
}

/// ⚙ Einstellungen
fn sheet_content(l: &mut Layout, v: &View, s: &Sheet) -> f32 {
    let lang = v.lang.as_str();
    let inner = WIDTH - 2.0 * MX;
    let t = |k: &str| tr(lang, k, &[]);
    let mut y = MY;
    let title = Style::new(24.0, true, TEXT);
    let section = Style::new(17.0, false, SECTION);
    l.button("▲", MX + inner - TIP_W, y, TIP_W, false, Action::Sheet);
    let head = format!("⚙  {}", t("panel_settings"));
    let th = measure(l.f, &head, None, title).1;
    l.label(&head, MX, y + (BTN_H - th) / 2.0, inner - TIP_W - 8.0, title);
    y += BTN_H + 8.0;

    let size = match s.width_cm {
        Some(cm) => format!("{} · {}:  {cm} cm", t("panel_size"), s.page_name),
        None => format!("{} {}", t("panel_size"), t("panel_size_later")),
    };
    y += l.label(&size, MX, y, inner, section) + 4.0;
    let cm = s.width_cm.unwrap_or(32);
    let frac = (cm - SIZE_CM.0) as f32 / (SIZE_CM.1 - SIZE_CM.0) as f32;
    y = l.bar(y, frac.clamp(0.0, 1.0), s.width_cm.is_some(), Bar::Size) + 8.0;
    y += l.label(&format!("{}:  {} %", t("panel_opacity"), v.opacity), MX, y, inner, section) + 4.0;
    y = l.bar(y, ((v.opacity - 30) as f32 / 70.0).clamp(0.0, 1.0), true, Bar::Opacity) + 8.0;

    y += l.label(&t("panel_anchor"), MX, y, inner, section) + 4.0;
    let anchors: Vec<(String, String)> =
        ["left", "right", "head", "world"].iter().map(|a| (a.to_string(), t(&format!("panel_anchor_short_{a}")))).collect();
    y = l.choices(y, &anchors, &s.anchor, |a| Action::Anchor(a.to_string())) + 8.0;
    let move_text = format!("{}  {}", if v.edit { "✔" } else { "✥" }, t("panel_move"));
    let reset_text = format!("⟲  {}", t("panel_reset"));
    let half = (inner - 8.0) / 2.0;
    l.button(&move_text, MX, y, half, v.edit, Action::Move);
    l.button(&reset_text, MX + half + 8.0, y, half, false, Action::Reset);
    y += BTN_H + 8.0;

    // 🔘 Knopf: an/aus, nach Foto öffnen, Größe, Farbe
    y += l.label(&t("panel_button"), MX, y, inner, section) + 4.0;
    let on = format!("{}  {}", if s.button { "✔" } else { "✕" }, t("panel_button_short"));
    let auto = format!("{}  {}", if s.open_on_shot { "✔" } else { "✕" }, t("panel_open_on_shot_short"));
    l.button(&on, MX, y, half, s.button, Action::Toggle("panel_button"));
    l.button(&auto, MX + half + 8.0, y, half, s.open_on_shot, Action::Toggle("panel_open_on_shot"));
    y += BTN_H + 8.0;
    let bsize = match s.button_cm {
        Some(cm) => format!("{}:  {cm} cm", t("panel_button_size")),
        None => format!("{}  {}", t("panel_button_size"), t("panel_size_later")),
    };
    y += l.label(&bsize, MX, y, inner, section) + 4.0;
    let cm = s.button_cm.unwrap_or(3);
    let frac = (cm - BUTTON_CM.0) as f32 / (BUTTON_CM.1 - BUTTON_CM.0) as f32;
    y = l.bar(y, frac.clamp(0.0, 1.0), s.button_cm.is_some(), Bar::Button) + 8.0;
    let gap = 6.0;
    let sw = (inner - gap * (BUTTON_COLORS.len() as f32 - 1.0)) / BUTTON_COLORS.len() as f32;
    for (i, color) in BUTTON_COLORS.iter().enumerate() {
        let x = MX + i as f32 * (sw + gap);
        let hex = u32::from_str_radix(color.trim_start_matches('#'), 16).unwrap_or(BLUE);
        let chosen = s.color.eq_ignore_ascii_case(color);
        if let Some(c) = l.c.as_deref_mut() {
            let border = if chosen { 0xffffff } else { 0x2b3240 };
            c.rounded(x + 1.5, y + 1.5, sw - 3.0, BTN_H - 3.0, 10.0, Some(rgba(hex, 255)), Some((rgba(border, 255), 3.0)));
        }
        if chosen {
            let st = Style::new(22.0, true, 0x10131a);
            let (tw, th) = measure(l.f, "✔", None, st);
            l.label("✔", x + (sw - tw) / 2.0, y + (BTN_H - th) / 2.0, sw, st);
        }
        l.hits.push(([x, y, sw, BTN_H], Action::Layer("panel_button_color", color.to_string())));
    }
    y += BTN_H + 8.0;

    y += l.label(&t("buttons_title"), MX, y, inner, section) + 4.0;
    let detect = [("auto".to_string(), t("detect_short_auto")), ("manual".to_string(), t("detect_short_manual"))];
    y = l.choices(y, &detect, &s.detect, |d| Action::Layer("detect_mode", d.to_string())) + 8.0;
    let combos: Vec<(String, String)> =
        ["left", "right", "both"].iter().map(|c| (c.to_string(), t(&format!("combo_short_{c}")))).collect();
    y += l.label(&t("shutter"), MX, y, inner, section) + 4.0;
    y = l.choices(y, &combos, &s.shutter, |c| Action::Layer("shutter", c.to_string())) + 8.0;
    y += l.label(&t("mode_button"), MX, y, inner, section) + 4.0;
    l.choices(y, &combos, &s.mode_button, |c| Action::Layer("mode_button", c.to_string()))
}

/// Zeilen → Seiten (leere Zeilen am Seitenanfang fallen weg) – wie vr_panel.paginate
pub fn paginate(lines: &[String], per_page: usize) -> Vec<String> {
    let per_page = per_page.max(1);
    let mut pages: Vec<String> = Vec::new();
    let mut cur: Vec<&str> = Vec::new();
    for line in lines {
        if cur.is_empty() && line.trim().is_empty() && !pages.is_empty() {
            continue;
        }
        cur.push(line);
        if cur.len() >= per_page {
            pages.push(cur.join("\n"));
            cur.clear();
        }
    }
    if !cur.is_empty() || pages.is_empty() {
        pages.push(cur.join("\n"));
    }
    pages
}

/// Klick (u, v in 0..1) → Knopf + Position im Knopf (0..1, für Schieber)
pub fn hit(hits: &Hits, size: (u32, u32), u: f32, v: f32) -> Option<(Action, f32)> {
    let (x, y) = (u * size.0 as f32, v * size.1 as f32);
    hits.iter()
        .find(|(r, _)| x >= r[0] && x <= r[0] + r[2] && y >= r[1] && y <= r[1] + r[3])
        .map(|(r, a)| (a.clone(), ((x - r[0] - BAR_PAD) / (r[2] - 2.0 * BAR_PAD)).clamp(0.0, 1.0)))
}

/// Größe ändern: Breite in panel_pose.json (+ von Hand gezogene Höhe im selben Verhältnis).
/// false = Datei gibt es noch nicht (Panel war noch nie in VR zu sehen).
pub fn set_width_cm(cm: i32) -> bool {
    let file = crate::paths::panel_pose_file();
    let Some(mut v) = std::fs::read_to_string(&file).ok().and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok()) else {
        return false;
    };
    let Some(old) = v["width"].as_f64().filter(|w| *w > 0.0) else { return false };
    let new = cm.clamp(SIZE_CM.0, SIZE_CM.1) as f64 / 100.0;
    v["width"] = serde_json::Value::from(new);
    if let Some(h) = v["height"].as_f64() {
        v["height"] = serde_json::Value::from(h * new / old);
    }
    crate::settings::write_json(&file, &v, 2).is_ok()
}

/// 🔘 Knopf-Größe (cm) aus button_pose.json – None = Knopf war noch nie in VR zu sehen
pub fn button_cm() -> Option<i32> {
    let text = std::fs::read_to_string(crate::paths::button_pose_file()).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    Some((v["width"].as_f64()? * 100.0).round() as i32)
}

pub fn set_button_cm(cm: i32) -> bool {
    let file = crate::paths::button_pose_file();
    let Some(mut v) = std::fs::read_to_string(&file).ok().and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok()) else {
        return false;
    };
    v["width"] = serde_json::Value::from(cm.clamp(BUTTON_CM.0, BUTTON_CM.1) as f64 / 100.0);
    crate::settings::write_json(&file, &v, 2).is_ok()
}

pub fn width_cm() -> Option<i32> {
    let text = std::fs::read_to_string(crate::paths::panel_pose_file()).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    Some((v["width"].as_f64()? * 100.0).round() as i32)
}

/// Von Hand gezogene Höhe (panel_pose.json) → Pixel-Höhe
pub fn fixed_height() -> Option<f32> {
    let text = std::fs::read_to_string(crate::paths::panel_pose_file()).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    let width = v["width"].as_f64()?;
    let height = v["height"].as_f64()?;
    if width <= 0.0 || height <= 0.0 {
        return None;
    }
    Some((WIDTH as f64 * height / width).round().max(160.0) as f32)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_like_the_app() {
        let l = |t: &str| Line { text: t.into(), r#box: Some([0, 0, 5, 5]) };
        assert_eq!(numbered(&[l("Dog"), l("Eagle")], "Hund\nAdler"), "①  Hund\n②  Adler");
        assert_eq!(numbered(&[l("Q"), l("A"), l("B")], "➜ 2) A (x)\nweil"), "➜ ② A (x)\nweil");
        assert_eq!(number(25), "(26)");
    }

    #[test]
    fn pages_like_the_app() {
        let lines: Vec<String> = ["a", "b", "", "c", "d"].iter().map(|s| s.to_string()).collect();
        assert_eq!(paginate(&lines, 2), vec!["a\nb", "c\nd"]);
        assert_eq!(paginate(&[], 3), vec![""]);
    }

    fn view() -> View {
        View {
            lang: "de".into(),
            method_label: "Lingva".into(),
            source_label: "Auto".into(),
            target_label: "Deutsch".into(),
            mode_label: Some("🤖 Auto".into()),
            opacity: 100,
            result: (0..30).map(|i| format!("Zeile {i} mit etwas längerem Text, der umbrochen werden muss")).collect::<Vec<_>>().join("\n"),
            status: "Claude Code (sonnet) · ❓ Frage beantworten".into(),
            last_ai: "Claude Code (sonnet)".into(),
            photo: std::env::var_os("PANEL_PHOTO").map(PathBuf::from),
            ..View::default()
        }
    }

    #[test]
    fn renders_pages_and_hits() {
        let mut f = Fonts::new();
        let v = view();
        let (c, hits, pages) = render(&mut f, &v, &Pics::default()).unwrap();
        assert!(pages > 1, "langer Text → mehrere Seiten");
        let size = (c.pix.width(), c.pix.height());
        let y = (MY + BTN_H + GAP + BTN_H / 2.0) / size.1 as f32;
        assert_eq!(hit(&hits, size, 0.2, y).map(|h| h.0), Some(Action::Choose(Choice::Method)));
        let y = (MY + BTN_H / 2.0) / size.1 as f32;
        assert_eq!(hit(&hits, size, 0.95, y).map(|h| h.0), Some(Action::Sheet));
        assert!(hits.iter().any(|h| h.1 == Action::Page(1)) && !hits.iter().any(|h| h.1 == Action::Page(-1)));
        assert!(hits.iter().any(|h| h.1 == Action::Nav(-1)) && hits.iter().any(|h| h.1 == Action::Nav(1)));
        if let Some(out) = std::env::var_os("PANEL_OUT") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // ⚙ offen: Schieber liefert die Position
        let v = View { sheet: Some(Sheet {
                width_cm: Some(32),
                anchor: "left".into(),
                detect: "auto".into(),
                shutter: "right".into(),
                mode_button: "left".into(),
                button: true,
                open_on_shot: true,
                button_cm: Some(5),
                color: "#4caf7a".into(),
                page_name: "Übersetzung".into(),
            }), ..view() };
        let (c, hits, _) = render(&mut f, &v, &Pics::default()).unwrap();
        let (r, _) = hits.iter().find(|h| h.1 == Action::Bar(Bar::Size)).unwrap();
        let size = (c.pix.width(), c.pix.height());
        let u = (r[0] + BAR_PAD + 0.75 * (r[2] - 2.0 * BAR_PAD)) / size.0 as f32;
        let (a, frac) = hit(&hits, size, u, (r[1] + 10.0) / size.1 as f32).unwrap();
        assert_eq!(a, Action::Bar(Bar::Size));
        assert!((frac - 0.75).abs() < 0.01);
        if let Some(out) = std::env::var_os("PANEL_OUT2") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
    }

    #[test]
    fn tiles_fit_and_pages_switch() {
        let (w, h) = tile_size();
        assert!(w as f32 * GRID_COLS as f32 + GRID_GAP * (GRID_COLS as f32 - 1.0) <= content_w() + 0.5);
        assert_eq!(h, (w as f32 * THUMB_RATIO).round() as u32);
        assert_eq!(Page::Translate.step(1), Page::Gallery);
        assert_eq!(Page::Gallery.step(-1), Page::Translate);
        assert_eq!(Page::from_key("gallery"), Page::Gallery);
        assert_eq!(Page::from_key("?"), Page::Translate);
        // gleicher Platz fürs Raster wie in vr_panel.py (GALLERY_H − Rand − Kopf − ◀ ▶)
        assert_eq!(grid_room(None), 608.0);
    }

    fn sample_months() -> Vec<(i32, u32)> {
        std::iter::repeat_n((2026, 10), 6).chain(std::iter::repeat_n((2026, 6), 15)).collect()
    }

    #[test]
    fn gallery_pages_like_the_app() {
        // 6 Fotos Oktober + 15 Fotos Juni → wie VRPanel.gallery_pages: [6 Zeilen, 3 Zeilen]
        let pages = gallery_pages(&sample_months(), |y, m| format!("{y}-{m}"), grid_room(None));
        assert_eq!(pages.iter().map(Vec::len).collect::<Vec<_>>(), [6, 3]);
        assert_eq!(pages[0][0], GRow::Month("2026-10".into()));
        assert_eq!(pages[0][1], GRow::Tiles(vec![0, 1, 2, 3]));
        assert_eq!(pages[0][2], GRow::Tiles(vec![4, 5]));
        assert_eq!(pages[0][3], GRow::Month("2026-6".into()));
        // Juni geht auf Seite 2 weiter → Trenner dort nochmal oben
        assert_eq!(pages[1][0], GRow::Month("2026-6".into()));
        assert!(gallery_pages(&[], |_, _| String::new(), 600.0)[0].is_empty());
    }

    #[test]
    fn gallery_nav_and_single_view() {
        let mut f = Fonts::new();
        let pages = gallery_pages(&sample_months(), |y, m| format!("{y} {m}"), grid_room(None));
        let tile_of = |i: usize| Tile { index: i, path: PathBuf::from(format!("/x/ViewShot_{i}.png")), mtime: None };
        let tiles: Vec<Tile> =
            pages[0].iter().flat_map(|r| if let GRow::Tiles(t) = r { t.clone() } else { vec![] }).map(tile_of).collect();
        let g = GalleryView { total: 21, page: 0, pages: 2, rows: pages[0].clone(), tiles: tiles.clone(), open: None };
        let (tw, th) = tile_size();
        let thumb_img = image::RgbaImage::from_pixel(tw - 4, th - 4, image::Rgba([200, 80, 160, 255]));
        let pics = Pics { thumbs: vec![Some(&thumb_img); tiles.len()], ..Pics::default() };
        let v = View { page: Page::Gallery, gallery: Some(g.clone()), ..view() };
        let (c, hits, _) = render(&mut f, &v, &pics).unwrap();
        let size = (c.pix.width(), c.pix.height());
        assert_eq!(size.1 as f32, GALLERY_H, "Galerie nutzt die ganze Fläche");
        // ◀ ▶ ganz unten, ⚙ oben, 14 Kacheln (6 Okt + 8 Juni), nur ▼ (erste Seite)
        let (r, _) = hits.iter().find(|h| h.1 == Action::Nav(-1)).unwrap();
        assert!(r[1] + r[3] > size.1 as f32 - MY - 1.0 && r[0] < WIDTH / 2.0);
        let (r, _) = hits.iter().find(|h| h.1 == Action::Nav(1)).unwrap();
        assert!(r[0] > WIDTH / 2.0);
        assert!(hits.iter().any(|h| h.1 == Action::Sheet));
        assert_eq!(hits.iter().filter(|h| matches!(h.1, Action::GalOpen(_))).count(), 14);
        assert!(hits.iter().any(|h| h.1 == Action::GalPage(1)) && !hits.iter().any(|h| h.1 == Action::GalPage(-1)));
        let (r, _) = hits.iter().find(|h| h.1 == Action::GalOpen(4)).unwrap();
        let (u, w) = ((r[0] + r[2] / 2.0) / size.0 as f32, (r[1] + r[3] / 2.0) / size.1 as f32);
        assert_eq!(hit(&hits, size, u, w).map(|h| h.0), Some(Action::GalOpen(4)));
        if let Some(out) = std::env::var_os("PANEL_OUT3") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // Übersetzungs-Seite hat die ◀ ▶-Zeile auch
        let (_, hits, _) = render(&mut f, &view(), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::Nav(1)));
        // Einzelansicht: keine ◀ ▶, dafür alle Aktionen
        let open = OpenPhoto {
            index: 3,
            path: PathBuf::from("/x/ViewShot_3.png"),
            mtime: None,
            confirm: false,
            month: "2026 Oktober".into(),
            toast: "✔ Link kopiert".into(),
            uploading: false,
            uploaded: false,
            sub: None,
        };
        let with = |o: OpenPhoto| View { gallery: Some(GalleryView { open: Some(o), ..g.clone() }), ..v.clone() };
        let big = image::RgbaImage::from_pixel(600, 338, image::Rgba([40, 120, 200, 255]));
        let (c, hits, _) = render(&mut f, &with(open.clone()), &Pics { big: Some(&big), ..Pics::default() }).unwrap();
        assert!(!hits.iter().any(|h| matches!(h.1, Action::Nav(_))));
        for a in [
            Action::GalBack,
            Action::GalStep(-1),
            Action::GalStep(1),
            Action::GalCopy,
            Action::GalUpload,
            Action::GalShare,
            Action::GalTranslate,
            Action::GalInfo,
            Action::GalDelete,
            Action::Sheet,
        ] {
            assert!(hits.iter().any(|h| h.1 == a), "{a:?} fehlt");
        }
        if let Some(out) = std::env::var_os("PANEL_OUT4") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // erstes / letztes Foto: ‹ / › ausgegraut (ohne Klick-Fläche)
        let (_, hits, _) = render(&mut f, &with(OpenPhoto { index: 0, ..open.clone() }), &Pics::default()).unwrap();
        assert!(!hits.iter().any(|h| h.1 == Action::GalStep(-1)) && hits.iter().any(|h| h.1 == Action::GalStep(1)));
        let (_, hits, _) = render(&mut f, &with(OpenPhoto { index: 20, ..open.clone() }), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::GalStep(-1)) && !hits.iter().any(|h| h.1 == Action::GalStep(1)));
        // lädt hoch → Knopf ohne Klick-Fläche
        let (_, hits, _) = render(&mut f, &with(OpenPhoto { uploading: true, ..open.clone() }), &Pics::default()).unwrap();
        assert!(!hits.iter().any(|h| h.1 == Action::GalUpload));
        // ↗ Teilen: Programme als Knöpfe + Zurück
        let shared = OpenPhoto { sub: Some(Sub::Share(vec![("discord".into(), "Discord".into())])), ..open.clone() };
        let (c, hits, _) = render(&mut f, &with(shared), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::ShareTo("discord".into())) && hits.iter().any(|h| h.1 == Action::SubBack));
        if let Some(out) = std::env::var_os("PANEL_OUT5") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // ⓘ Info
        let info = OpenPhoto { sub: Some(Sub::Info(vec![("Ordner".into(), "/x".into()), ("Link".into(), "–".into())])), ..open.clone() };
        let (c, hits, _) = render(&mut f, &with(info), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::SubBack));
        if let Some(out) = std::env::var_os("PANEL_OUT6") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // „Wirklich löschen?“ ist blau hervorgehoben (anderes Bild als vorher)
        let (c1, _, _) = render(&mut f, &with(open.clone()), &Pics::default()).unwrap();
        let (c2, _, _) = render(&mut f, &with(OpenPhoto { confirm: true, ..open }), &Pics::default()).unwrap();
        assert_ne!(c1.pix.data(), c2.pix.data());
        // leere Galerie: Kopf + Hinweis, ◀ ▶ bleiben
        let (_, hits, _) = render(&mut f, &View { gallery: Some(GalleryView::default()), ..v }, &Pics::default()).unwrap();
        assert!(!hits.iter().any(|h| matches!(h.1, Action::GalOpen(_))) && hits.iter().any(|h| h.1 == Action::Nav(1)));
    }

    #[test]
    fn page_sizes_switch_and_remember() {
        let dir = std::env::temp_dir().join(format!("viewshot-sizes-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("linuxvr-viewshot")).unwrap();
        std::env::set_var("XDG_CONFIG_HOME", &dir);
        let pose = crate::paths::panel_pose_file();
        std::fs::write(&pose, r#"{"anchor":"left","width":0.32,"height":0.2}"#).unwrap();
        switch_page_size(Page::Translate, Page::Gallery);
        let p: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&pose).unwrap()).unwrap();
        assert_eq!(p["width"], 0.48);
        assert!(p.get("height").is_none(), "Galerie: Höhe automatisch");
        assert_eq!(current_page(), Page::Gallery);
        switch_page_size(Page::Gallery, Page::Translate);
        let p: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&pose).unwrap()).unwrap();
        assert_eq!((p["width"].as_f64(), p["height"].as_f64()), (Some(0.32), Some(0.2)), "alte Größe zurück");
        assert_eq!(p["anchor"], "left", "Rest der Pose bleibt");
        std::env::remove_var("XDG_CONFIG_HOME");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
