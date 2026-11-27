//! 🪟 VR-Panel ohne App – sieht aus wie ui/vr_panel.py (gleiche Maße, Farben, Texte).
//! Wird als Bild gezeichnet (<Foto-Ordner>/panel/panel.png); Klicks kommen vom Layer
//! als „click u v“ und werden hier den Knöpfen zugeordnet.
//!
//! Seiten: Übersetzung (lang → ▼ / ▲ blättern) · 🖼 Galerie (Raster über die ganze Fläche,
//! Monats-Trenner, Antippen = Foto groß mit 📋 Kopieren · ☁ Hochladen + Link · ↗ Teilen ·
//! 🌐 Übersetzen · ⓘ Info · 🗑 Löschen) · Auswahl-Liste (Dienst + Modus 🤖/✋, Von, Nach,
//! Aufgabe) · ⚙ Einstellungen (eigene Seite): links Kategorien (📸 Shot / 🥽 VR), rechts das
//! Untermenü – was drinsteht, kommt aus UI/core/vr_settings.py (über contract.json, „vr_settings“).
//! 🌐 Übersetzung: Dienst/Sprachen/Aufgabe im Seitenpanel rechts (einklappbar).
//! Ganz unten: Tabs = Seite wechseln (jede Seite hat ihre eigene Größe in VR, panel_sizes.json).

use crate::i18n::tr;
use crate::ocr::Line;
use crate::render::{line_height, measure, rgba, wrap_lines, Canvas, Fonts, Style};
use std::path::PathBuf;

/// Pixel-Breite des Panel-Bilds (alle Seiten: Seitenpanel / Kategorien rechts bzw. links)
pub const WIDE: f32 = 1000.0;
/// 🌐 Seitenpanel rechts: offen / eingeklappt (nur „Einstellungen“ senkrecht)
const SIDE_W: f32 = 300.0;
const STRIP_W: f32 = 64.0;
/// Abstand zwischen zwei Spalten / Innenrand einer Karte
const COL_GAP: f32 = 14.0;
const CARD_PAD: f32 = 14.0;
/// ⚙ Kategorien-Liste links
const CAT_W: f32 = 360.0;
const PHOTO_MAX_H: f32 = 360.0;
const RESULT_MAX_H: f32 = 300.0;
const MX: f32 = 18.0;
const MY: f32 = 16.0;
const GAP: f32 = 10.0;
const BTN_H: f32 = 48.0;
const TIP_W: f32 = 64.0;
/// 🟠 Layer veraltet (wie WARN_COLOR in widgets.py)
const WARN: u32 = 0xe8a33d;
/// 🎞 GIF / 🎬 VID-Knopf oben
const REC_W: f32 = 120.0;
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
/// 🖼 Spalten im Raster zur Auswahl (Standard 4)
pub const GALLERY_COLS: [usize; 3] = [3, 4, 5];
pub const GRID_COLS: usize = 4;
const GRID_GAP: f32 = 8.0;
const THUMB_RATIO: f32 = 0.75;
const MONTH_H: f32 = 34.0;
/// Galerie ohne von Hand gezogene Höhe: so hoch wird das Panel
pub const GALLERY_H: f32 = 760.0;
/// ⚙ Einstellungen: Gruppen-Kopf (▸ / ▾)
const GROUP_H: f32 = 52.0;
const SINGLE_MAX_H: f32 = 360.0;
/// Breite in VR (m) je Seite, wenn noch keine gemerkt ist (Galerie größer)
pub const PAGE_SIZE_DEFAULT: [(&str, f64); 3] = [("translate", 0.44), ("gallery", 0.62), ("settings", 0.56)];
const NUMBERS: &str = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";

const TEXT: u32 = 0xe8ecf4;
const DIM: u32 = 0x9aa6ba;
const SECTION: u32 = 0xaeb4bf;
const BTN_BG: u32 = 0x121a28;
const BTN_BORDER: u32 = 0x24324a;
const BTN_TEXT: u32 = 0xe8ecf4;
/// Akzent: Linie unter Knöpfen, Schieber, Rand oben
const BLUE: u32 = 0x3d7fd9;
/// Überschriften + gewählter Rand
const HEAD: u32 = 0x5b9bff;
/// gewählter Knopf / gewählte Kategorie
const PICKED_BG: u32 = 0x1f3a66;
const CAT_BG: u32 = 0x16233a;
/// Karte (Seitenpanel, Untermenü) und Panel-Rand
const CARD_BG: u32 = 0x0f141d;
const FRAME: u32 = 0x1d2a40;
pub const BG: u32 = 0x07090d;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Choice {
    Method,
    Source,
    Target,
    Mode,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Action {
    /// ⚙ oben: zur Einstellungs-Seite
    Settings,
    /// 🟠 i: Hinweis „Layer veraltet“ auf-/zuklappen
    OldNote,
    Reset,
    Choose(Choice),
    Redo,
    Back,
    Pick(Choice, String),
    /// Schieber: Wert aus der Klick-Position (0..1) – layer.json-Schlüssel,
    /// "@size" = 🪟 Größe der gewählten Seite, "@button_cm" = 🔘 Knopf-Größe
    Slider(String),
    Anchor(String),
    /// ✥ Verschieben (Grip) an/aus
    Move,
    /// layer.json-Wert (detect_mode / shutter / aspect / panel_button_color …)
    Layer(String, String),
    /// layer.json an/aus (panel_button / gif_hold / rec_video …)
    Toggle(String),
    /// ⚙ Kategorie links antippen → Untermenü rechts
    Group(String),
    /// ⚙ Überschrift 📸 Shot / 🥽 VR antippen → ihre Kategorien ein-/ausklappen
    FoldTab(String),
    /// 🪟 Größe: für welche Seite
    SizePage(String),
    /// 🚫 Liste: (Schlüssel, Eintrag) entfernen
    ListRemove(String, String),
    Route(String),
    Page(i32),
    /// Tab-Leiste ganz unten: zu dieser Seite
    Goto(Page),
    /// Galerie: Raster-Seite blättern
    GalPage(i32),
    /// Galerie-Filter: "" = alle, "text" / "qr" / "image" / "gif_vid"
    GalFilter(String),
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
    Settings,
}

pub const PAGES: [Page; 3] = [Page::Translate, Page::Gallery, Page::Settings];

impl Page {
    /// Name in panel_sizes.json ("translate" / "gallery")
    pub fn key(self) -> &'static str {
        match self {
            Page::Translate => "translate",
            Page::Gallery => "gallery",
            Page::Settings => "settings",
        }
    }

    pub fn from_key(key: &str) -> Page {
        PAGES.into_iter().find(|p| p.key() == key).unwrap_or_default()
    }

    fn icon(self) -> &'static str {
        match self {
            Page::Translate => "🌐",
            Page::Gallery => "🖼",
            Page::Settings => "⚙",
        }
    }

    fn title_key(self) -> &'static str {
        match self {
            Page::Translate => "vr_page_translate",
            Page::Gallery => "nav_gallery",
            Page::Settings => "panel_settings",
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
    /// Filter: "" = alle, "text" / "qr" / "image" / "gif_vid"
    pub filter: String,
    /// Spalten im Raster (layer.json „gallery_cols“: 3 / 4 / 5)
    pub cols: usize,
    /// Seitenpanel rechts eingeklappt (layer.json „gallery_side_closed“)
    pub side_closed: bool,
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

/// ⚙ Einstellungs-Seite (Werte aus layer.json / panel_pose.json / panel_sizes.json)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SettingsView {
    /// Tab "shot" / "vr"
    pub tab: String,
    /// gewählte Kategorie (rechts offen)
    pub open: Option<String>,
    /// eingeklappte Überschriften links ("shot" / "vr")
    pub folded: Vec<String>,
    /// layer.json (mit Standardwerten)
    pub layer: serde_json::Map<String, serde_json::Value>,
    /// 🪟 Größe: gewählte Seite + ihre Breite (cm, None = Panel war noch nie in VR)
    pub size_page: Page,
    pub size_cm: Option<i32>,
    /// 🔘 Knopf-Größe (cm, None = Knopf war noch nie in VR)
    pub button_cm: Option<i32>,
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
    /// 🎬 Aufnahme-Knopf steht auf VID (sonst 🎞 GIF)
    pub rec_video: bool,
    /// 🟠 Layer veraltet: Hinweistext (None = alles passt) + aufgeklappt?
    pub layer_old: Option<String>,
    pub old_open: bool,
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
    /// ⚙ Einstellungs-Seite (nur wenn sie offen ist)
    pub settings: Option<SettingsView>,
    pub fixed_height: Option<f32>,
    /// 🌐 Seitenpanel rechts eingeklappt (layer.json „panel_side_closed“)
    pub side_closed: bool,
    /// 🌐 Foto ausgeblendet → Übersetzung nutzt die ganze Fläche (layer.json „panel_hide_photo“)
    pub hide_photo: bool,
    /// 🖐 Rahmen-Geste on / auto / off und 🥽 Overlay – schnell im Seitenpanel umschaltbar
    pub gesture_mode: String,
    pub overlay: bool,
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
    /// linker Rand und Breite der Spalte, in die gerade gezeichnet wird
    mx: f32,
    w: f32,
}

impl Layout<'_> {
    /// Ausgegrauter Knopf (z. B. ‹ beim ersten Foto) – sichtbar, aber ohne Klick-Fläche
    fn dead_button(&mut self, text: &str, x: f32, y: f32, w: f32) {
        if let Some(c) = self.c.as_deref_mut() {
            c.rounded(x + 0.5, y + 0.5, w - 1.0, BTN_H - 1.0, 6.0, Some(rgba(0x0d121b, 255)), Some((rgba(0x1a2436, 255), 1.0)));
            let st = Style::new(20.0, true, 0x3a4560);
            let (tw, th) = measure(self.f, text, None, st);
            c.text(self.f, text, x + ((w - tw) / 2.0).max(8.0), y + (BTN_H - th) / 2.0, Some(w - 16.0), st);
        }
    }

    fn button(&mut self, text: &str, x: f32, y: f32, w: f32, primary: bool, action: Action) {
        if let Some(c) = self.c.as_deref_mut() {
            let (bg, border, fg) = if primary { (PICKED_BG, HEAD, 0xffffff) } else { (BTN_BG, BTN_BORDER, BTN_TEXT) };
            c.rounded(x + 0.5, y + 0.5, w - 1.0, BTN_H - 1.0, 6.0, Some(rgba(bg, 255)), Some((rgba(border, 255), 1.0)));
            // blaue Linie unten (wie die Welt-Menüs in VRChat)
            c.rounded(x + 1.0, y + BTN_H - 3.0, w - 2.0, 2.0, 1.0, Some(rgba(if primary { HEAD } else { BLUE }, 255)), None);
            // zu lang für den Knopf → etwas kleiner statt umbrechen
            let mut st = Style::new(20.0, true, fg);
            while st.size > 14.0 && measure(self.f, text, None, st).0 > w - 16.0 {
                st = Style::new(st.size - 1.0, true, fg);
            }
            // immer noch zu lang (schmales Seitenpanel) → vor „  ▸“ mit … kürzen
            let mut shown = text.to_string();
            while measure(self.f, &shown, None, st).0 > w - 16.0 && shown.chars().count() > 4 {
                let (body, tail) = match shown.strip_suffix("  ▸") {
                    Some(b) => (b.trim_end_matches('…').to_string(), "…  ▸"),
                    None => (shown.trim_end_matches('…').to_string(), "…"),
                };
                let mut chars: Vec<char> = body.chars().collect();
                chars.pop();
                shown = format!("{}{tail}", chars.into_iter().collect::<String>().trim_end());
            }
            let (tw, th) = measure(self.f, &shown, None, st);
            c.text(self.f, &shown, x + ((w - tw) / 2.0).max(8.0), y + (BTN_H - th) / 2.0, None, st);
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

    /// Karte (Seitenpanel / Untermenü): eigener Grund, Rand, blaue Linie oben
    fn card(&mut self, x: f32, y: f32, w: f32, h: f32) {
        if let Some(c) = self.c.as_deref_mut() {
            c.rounded(x + 0.5, y + 0.5, w - 1.0, h - 1.0, 10.0, Some(rgba(CARD_BG, 255)), Some((rgba(FRAME, 255), 1.0)));
            c.rounded(x + 8.0, y + 1.0, w - 16.0, 3.0, 1.5, Some(rgba(BLUE, 255)), None);
        }
    }

    /// Nur messen (nichts zeichnen, keine Klick-Flächen) – gibt die Unterkante von `draw` zurück
    fn measure_with(&mut self, draw: impl FnOnce(&mut Self) -> f32) -> f32 {
        let c = self.c.take();
        let (n, pages) = (self.hits.len(), self.pages);
        let y = draw(self);
        self.hits.truncate(n);
        self.pages = pages;
        self.c = c;
        y
    }

    /// Nebeneinander liegende Knöpfe, der gewählte ist blau. Gibt die Unterkante zurück.
    fn choices(&mut self, y: f32, items: &[(String, String)], chosen: &str, make: impl Fn(&str) -> Action) -> f32 {
        let inner = self.w;
        let gap = 6.0;
        let w = (inner - gap * (items.len() as f32 - 1.0)) / items.len() as f32;
        for (i, (value, text)) in items.iter().enumerate() {
            self.button(text, self.mx + i as f32 * (w + gap), y, w, value == chosen, make(value));
        }
        y + BTN_H
    }

    /// Wie choices, aber Breite für `cols` Knöpfe (letzte Zeile eines Rasters bleibt gleich breit)
    fn choices_n(&mut self, y: f32, items: &[(String, String)], cols: usize, chosen: &str, make: impl Fn(&str) -> Action) -> f32 {
        let inner = self.w;
        let gap = 6.0;
        let w = (inner - gap * (cols as f32 - 1.0)) / cols as f32;
        for (i, (value, text)) in items.iter().enumerate() {
            self.button(text, self.mx + i as f32 * (w + gap), y, w, value == chosen, make(value));
        }
        y + BTN_H
    }

    /// Schieber (Klick irgendwo auf die Leiste = dieser Wert)
    fn bar(&mut self, y: f32, frac: f32, enabled: bool, action: Action) -> f32 {
        let mx = self.mx;
        let inner = self.w;
        if let Some(c) = self.c.as_deref_mut() {
            let (x, w) = (mx + BAR_PAD, inner - 2.0 * BAR_PAD);
            let cy = y + BAR_H / 2.0;
            c.rounded(x, cy - 5.0, w, 10.0, 5.0, Some(rgba(0x1d2a40, 255)), None);
            if enabled {
                c.rounded(x, cy - 5.0, (w * frac).max(10.0), 10.0, 5.0, Some(rgba(BLUE, 255)), None);
                c.circle(x + w * frac, cy, 14.0, rgba(0xe8ecf2, 255));
            }
        }
        if enabled {
            self.hits.push(([mx, y, inner, BAR_H], action));
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
    let pw = page_width(v.page);
    let height = {
        let mut l = Layout { f, c: None, hits: Vec::new(), pages: 1, mx: MX, w: pw - 2.0 * MX };
        content(&mut l, v, pics) + if nav { GAP + NAV_H } else { 0.0 }
    };
    let gallery_grid = nav && v.page == Page::Gallery;
    let auto_h = if gallery_grid { GALLERY_H } else { (height + MY).max(200.0) };
    // ⚙ Einstellungen: immer so hoch wie der Inhalt (Gruppen klappen auf und zu)
    let fixed = if v.settings.is_some() { None } else { v.fixed_height };
    let h = fixed.unwrap_or(auto_h).round();
    let mut canvas = Canvas::new(pw as u32, h as u32)?;
    canvas.rounded(1.0, 1.0, pw - 2.0, h - 2.0, 16.0, Some(rgba(BG, 255)), Some((rgba(FRAME, 255), 2.0)));
    canvas.rounded(16.0, 1.0, pw - 32.0, 4.0, 2.0, Some(rgba(BLUE, 255)), None);
    let (hits, pages) = {
        let mut l = Layout { f, c: Some(&mut canvas), hits: Vec::new(), pages: 1, mx: MX, w: pw - 2.0 * MX };
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
    let inner = l.w;
    let mut y = MY;
    let title = Style::new(24.0, true, HEAD);
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
                    c.rounded(MX, y, inner, ITEM_H, 6.0, Some(rgba(CAT_BG, 255)), None);
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
    match (v.page, &v.settings) {
        (Page::Settings, Some(s)) => settings_content(l, v, s),
        (Page::Gallery, _) => gallery_content(l, v, pics),
        _ => translate_content(l, v, pics.photo),
    }
}

/// ◀ ▶-Zeile unten nur auf den Hauptseiten (nicht in der Auswahl-Liste, Foto groß)
fn shows_nav(v: &View) -> bool {
    v.choosing.is_none() && !v.gallery.as_ref().is_some_and(|g| g.open.is_some())
}

/// Ganz unten: Tab-Leiste [🌐 Übersetzung] [🖼 Galerie] [⚙ Einstellungen] – offene Seite blau
fn nav_row(l: &mut Layout, v: &View, y: f32) {
    let lang = v.lang.as_str();
    let n = PAGES.len() as f32;
    let tw = (l.w - 8.0 * (n - 1.0)) / n;
    for (i, p) in PAGES.iter().enumerate() {
        let x = MX + i as f32 * (tw + 8.0);
        let on = *p == v.page;
        let text = format!("{}  {}", p.icon(), tr(lang, p.title_key(), &[]));
        if let Some(c) = l.c.as_deref_mut() {
            c.rounded(x + 0.5, y + 0.5, tw - 1.0, NAV_H - 1.0, 8.0, Some(rgba(if on { CAT_BG } else { BTN_BG }, 255)), Some((rgba(BTN_BORDER, 255), 1.0)));
            c.rounded(x + 6.0, y + 1.0, tw - 12.0, 3.0, 1.5, Some(rgba(if on { HEAD } else { 0x2c3d5c }, 255)), None);
            let st = Style::new(20.0, true, if on { 0x8fb6ff } else { 0xc9d3e3 });
            let (tx, th) = measure(l.f, &text, None, st);
            c.text(l.f, &text, x + ((tw - tx) / 2.0).max(8.0), y + (NAV_H - th) / 2.0, Some(tw - 16.0), st);
        }
        l.hits.push(([x, y, tw, NAV_H], Action::Goto(*p)));
    }
}

/// 🌐 Übersetzungs-Seite: links Foto + Übersetzung, rechts das Seitenpanel (ein-/ausklappbar).
/// Gibt die Unterkante zurück.
fn translate_content(l: &mut Layout, v: &View, photo: Option<&image::RgbaImage>) -> f32 {
    let (x0, inner) = (l.mx, l.w);
    let side_w = side_w(v.side_closed);
    let main_w = inner - side_w - COL_GAP;
    let side_x = x0 + main_w + COL_GAP;
    l.w = main_w;
    let main_bottom = translate_main(l, v, photo);
    l.mx = side_x;
    l.w = side_w;
    let bottom = if v.side_closed {
        side_strip(l, v, main_bottom, Action::Toggle("panel_side_closed".into()))
    } else {
        let side_bottom = l.measure_with(|l| side_panel(l, v));
        let bottom = main_bottom.max(side_bottom);
        l.card(side_x, MY, side_w, bottom - MY + CARD_PAD);
        side_panel(l, v);
        bottom + CARD_PAD
    };
    l.mx = x0;
    l.w = inner;
    bottom
}

/// Linke Spalte: Kopf, Foto mit ①②③, Übersetzung (▼ / ▲), Status
fn translate_main(l: &mut Layout, v: &View, photo: Option<&image::RgbaImage>) -> f32 {
    let (mx, lang) = (l.mx, v.lang.as_str());
    let inner = l.w;
    let mut y = MY;
    let title = Style::new(26.0, true, HEAD);

    // Kopf: 🌐 Übersetzung  [i] [🖼 ▲/▼] [🎞 GIF / 🎬 VID]
    let rec = if v.rec_video { "🎬 VID" } else { "🎞 GIF" };
    let rec_x = mx + inner - REC_W;
    l.button(rec, rec_x, y, REC_W, false, Action::Toggle("rec_video".into()));
    // 🖼 ▲ = Foto ausblenden (Übersetzung bekommt die ganze Fläche), 🖼 ▼ = wieder zeigen
    let pic_w = 84.0;
    let pic_x = rec_x - 8.0 - pic_w;
    l.button(if v.hide_photo { "🖼 ▼" } else { "🖼 ▲" }, pic_x, y, pic_w, v.hide_photo, Action::Toggle("panel_hide_photo".into()));
    let rec_x = pic_x;
    // 🟠 i: Layer passt nicht zum Dienst → antippen klappt den Hinweis auf
    let mut used = REC_W + pic_w + 16.0;
    if v.layer_old.is_some() {
        let d = BTN_H;
        let x = rec_x - 8.0 - d;
        if let Some(c) = l.c.as_deref_mut() {
            c.circle(x + d / 2.0, y + d / 2.0, d / 2.0, rgba(WARN, 255));
            let st = Style::new(24.0, true, BG);
            let (tw, th) = measure(l.f, "i", None, st);
            c.text(l.f, "i", x + (d - tw) / 2.0, y + (d - th) / 2.0, None, st);
        }
        l.hits.push(([x, y, d, d], Action::OldNote));
        used += d + 8.0;
    }
    let head = format!("🌐  {}", tr(lang, "vr_page_translate", &[]));
    let th = measure(l.f, &head, None, title).1;
    l.label(&head, mx, y + (BTN_H - th) / 2.0, inner - used, title);
    y += BTN_H + GAP;
    if let (Some(note), true) = (&v.layer_old, v.old_open) {
        y += l.label(note, mx, y, inner, Style::new(19.0, false, WARN)) + GAP;
    }
    let dim = Style::new(16.0, false, DIM);
    if v.edit {
        y += l.label(&format!("✥  {}", tr(lang, "panel_edit_help", &[])), mx, y, inner, dim) + GAP;
    }

    // Foto-Kasten + Übersetzungs-Kasten haben eine feste Größe – auch mit kleinem Foto,
    // wenig Text oder ohne Foto bleibt das Panel gleich groß (Rest = leerer Kasten)
    let bottom = match v.fixed_height {
        Some(fh) => (fh - MY - NAV_H - GAP).max(y + 2.0 * BTN_H),
        None => y + translate_area_h(),
    };
    if !v.hide_photo {
        let photo_h = PHOTO_MAX_H.min(((bottom - y - GAP) * 0.55).floor());
        if let Some(c) = l.c.as_deref_mut() {
            c.rounded(mx + 0.5, y + 0.5, inner - 1.0, photo_h - 1.0, 8.0, Some(rgba(CARD_BG, 255)), Some((rgba(BTN_BORDER, 255), 1.0)));
            if let Some(img) = photo {
                // von Hand kleiner gezogen → Foto passend verkleinern
                let small;
                let img = if img.height() as f32 > photo_h - 2.0 {
                    let k = (photo_h - 2.0) / img.height() as f32;
                    let w = (img.width() as f32 * k).round().max(1.0) as u32;
                    small = image::imageops::resize(img, w, (photo_h - 2.0).max(1.0) as u32, image::imageops::FilterType::Triangle);
                    &small
                } else {
                    img
                };
                let x = (mx + (inner - img.width() as f32) / 2.0).round();
                let iy = (y + (photo_h - img.height() as f32) / 2.0).round();
                c.image(img, x as i32, iy as i32);
            }
        }
        y += photo_h + GAP;
    }

    // Übersetzung im Kasten (blaue Linie unten), Status unten im Kasten; lang → Seiten (▼ / ▲) darunter
    let result = numbered(&v.lines, &v.result);
    let result = if result.is_empty() && v.status.starts_with('⏳') { "…".to_string() } else { result };
    let st = Style::new(22.0, false, TEXT);
    let lh = line_height(st);
    let text_w = inner - 24.0;
    let status_h = if v.status.is_empty() { 0.0 } else { measure(l.f, &v.status, Some(text_w), dim).1 + 8.0 };
    let lines = wrap_lines(l.f, &result, text_w, st);
    let per_page = |box_h: f32| (((box_h - 24.0 - status_h) / lh).floor().max(1.0)) as usize;
    let mut box_h = bottom - y;
    let mut pages = paginate(&lines, per_page(box_h));
    if pages.len() > 1 {
        box_h -= BTN_H + GAP;
        pages = paginate(&lines, per_page(box_h));
    }
    l.pages = pages.len();
    let page = v.result_page.min(pages.len() - 1);
    if let Some(c) = l.c.as_deref_mut() {
        c.rounded(mx + 0.5, y + 0.5, inner - 1.0, box_h - 1.0, 8.0, Some(rgba(CARD_BG, 255)), Some((rgba(BTN_BORDER, 255), 1.0)));
        c.rounded(mx + 1.0, y + box_h - 3.5, inner - 2.0, 3.0, 1.5, Some(rgba(BLUE, 255)), None);
    }
    l.label(&pages[page], mx + 12.0, y + 12.0, text_w, st);
    if status_h > 0.0 {
        l.label(&v.status, mx + 12.0, y + box_h - 12.0 - status_h + 8.0, text_w, dim);
    }
    y += box_h + GAP;
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
    }
    bottom
}

/// 🌐 Feste Höhe für Foto-Kasten + Übersetzungs-Kasten + ▲ ▼-Zeile (ohne von Hand gezogene Höhe)
fn translate_area_h() -> f32 {
    PHOTO_MAX_H + GAP + RESULT_MAX_H + BTN_H + GAP
}

/// Seitenpanel rechts (offen): ⚙ Einstellungen [›] · Dienst [↻] · Von · → Nach · Aufgabe · Letzte KI
fn side_panel(l: &mut Layout, v: &View) -> f32 {
    let lang = v.lang.as_str();
    let x = l.mx + CARD_PAD;
    let w = l.w - 2.0 * CARD_PAD;
    let mut y = MY + CARD_PAD;
    let title = Style::new(22.0, true, HEAD);
    let head = format!("⚙  {}", tr(lang, "panel_settings", &[]));
    let th = measure(l.f, &head, None, title).1;
    l.label(&head, x, y + (BTN_H - th) / 2.0, w - BTN_H - 8.0, title);
    l.button("›", x + w - BTN_H, y, BTN_H, false, Action::Toggle("panel_side_closed".into()));
    y += BTN_H + GAP;
    let rw = BTN_H;
    l.button(&format!("{}  ▸", v.method_label), x, y, w - rw - 8.0, false, Action::Choose(Choice::Method));
    l.button("↻", x + w - rw, y, rw, false, Action::Redo);
    y += BTN_H + GAP;
    l.button(&format!("{}  ▸", v.source_label), x, y, w, false, Action::Choose(Choice::Source));
    y += BTN_H + 6.0;
    l.button(&format!("→  {}  ▸", v.target_label), x, y, w, false, Action::Choose(Choice::Target));
    y += BTN_H + GAP;
    if let Some(mode) = &v.mode_label {
        l.button(&format!("{mode}  ▸"), x, y, w, false, Action::Choose(Choice::Mode));
        y += BTN_H + GAP;
    }
    let dim = Style::new(16.0, false, DIM);
    let last = format!("{}:  {}", tr(lang, "tr_last_ai", &[]), v.last_ai);
    y += l.label(&last, x, y, w, dim) + GAP + 4.0;

    // 🖐 Rahmen-Geste (🔫 Auto = Waffen-Schutz) und 🥽 Overlay – schnell umschalten
    let section = Style::new(16.0, false, SECTION);
    y += l.label(&tr(lang, "gesture_mode", &[]), x, y, w, section) + 4.0;
    let options: Vec<(String, String)> = spec_item("gesture_mode")
        .and_then(|i| i["options"].as_array())
        .into_iter()
        .flatten()
        .map(|o| (o[0].as_str().unwrap_or("").to_string(), spec_text(lang, o[1].as_str().unwrap_or(""))))
        .collect();
    let (mx, mw) = (l.mx, l.w);
    l.mx = x;
    l.w = w;
    y = l.choices(y, &options, &v.gesture_mode, |m| Action::Layer("gesture_mode".into(), m.to_string())) + GAP;
    l.mx = mx;
    l.w = mw;
    let text = format!("{}  {}", if v.overlay { "✔" } else { "✕" }, tr(lang, "vr_overlay_short", &[]));
    l.button(&text, x, y, w, v.overlay, Action::Toggle("overlay".into()));
    y + BTN_H
}

/// Seitenpanel eingeklappt: schmale Leiste mit ‹ und „Einstellungen“ senkrecht – antippen klappt auf
fn side_strip(l: &mut Layout, v: &View, bottom: f32, action: Action) -> f32 {
    let (x, w) = (l.mx, l.w);
    let h = (bottom - MY).max(260.0);
    l.card(x, MY, w, h);
    let text = tr(&v.lang, "panel_settings", &[]);
    if let Some(c) = l.c.as_deref_mut() {
        let st = Style::new(26.0, true, HEAD);
        let (aw, ah) = measure(l.f, "‹", None, st);
        c.text(l.f, "‹", x + (w - aw) / 2.0, MY + 18.0, None, st);
        vertical_text(c, l.f, &text, x + w / 2.0, MY + 18.0 + ah + (h - 18.0 - ah) / 2.0, Style::new(22.0, true, HEAD));
    }
    l.hits.push(([x, MY, w, h], action));
    MY + h
}

/// Text um 90° gedreht (von unten nach oben lesbar), Mitte bei cx / cy
fn vertical_text(c: &mut Canvas, f: &mut Fonts, text: &str, cx: f32, cy: f32, st: Style) {
    let (tw, th) = measure(f, text, None, st);
    let Some(mut tmp) = Canvas::new(tw.ceil() as u32 + 2, th.ceil() as u32 + 2) else { return };
    tmp.text(f, text, 1.0, 1.0, None, st);
    let (w, h) = (tmp.pix.width(), tmp.pix.height());
    let mut img = image::RgbaImage::new(w, h);
    for (i, px) in tmp.pix.pixels().iter().enumerate() {
        let d = px.demultiply();
        img.put_pixel(i as u32 % w, i as u32 / w, image::Rgba([d.red(), d.green(), d.blue(), d.alpha()]));
    }
    let img = image::imageops::rotate270(&img);
    c.image(&img, (cx - img.width() as f32 / 2.0).round() as i32, (cy - img.height() as f32 / 2.0).round() as i32);
}

/// Kopfzeile: Titel … [extra] [⚙] – gibt die x-Position links von ⚙ zurück
fn head_row(l: &mut Layout, title: &str, y: f32) -> f32 {
    let (mx, inner) = (l.mx, l.w);
    let st = Style::new(24.0, true, HEAD);
    l.button("⚙", mx + inner - TIP_W, y, TIP_W, false, Action::Settings);
    let th = measure(l.f, title, None, st).1;
    l.label(title, mx, y + (BTN_H - th) / 2.0, inner - TIP_W - 8.0, st);
    mx + inner - TIP_W - 8.0
}

/// Monats-Trenner „──── 2026 Oktober ────“
fn month_row(l: &mut Layout, text: &str, y: f32) {
    let (mx, inner) = (l.mx, l.w);
    let st = Style::new(18.0, true, 0xc7cdd6);
    let (tw, th) = measure(l.f, text, None, st);
    if let Some(c) = l.c.as_deref_mut() {
        let tx = mx + (inner - tw) / 2.0;
        let cy = y + MONTH_H / 2.0;
        c.rounded(mx, cy - 1.0, (tx - mx - 12.0).max(0.0), 2.0, 1.0, Some(rgba(BTN_BORDER, 255)), None);
        c.rounded(tx + tw + 12.0, cy - 1.0, (mx + inner - tx - tw - 12.0).max(0.0), 2.0, 1.0, Some(rgba(BTN_BORDER, 255)), None);
        c.text(l.f, text, tx, y + (MONTH_H - th) / 2.0, None, st);
    }
}

/// 🖼 Galerie-Seite: links das Raster mit Monats-Trennern, rechts das Seitenpanel
/// (Filter, Spalten, Blättern – einklappbar wie bei der Übersetzung). Gibt die Unterkante zurück.
fn gallery_content(l: &mut Layout, v: &View, pics: &Pics) -> f32 {
    let Some(g) = &v.gallery else { return MY + BTN_H + GAP };
    let (x0, inner) = (l.mx, l.w);
    let side_w = side_w(g.side_closed);
    let side_x = x0 + inner - side_w;
    l.w = inner - side_w - COL_GAP;
    let grid_bottom = gallery_grid(l, v, g, pics);
    // Seitenpanel bis ganz unten (über den Tabs), die Galerie ist immer gleich hoch
    let bottom = v.fixed_height.unwrap_or(GALLERY_H) - MY - NAV_H - GAP;
    l.mx = side_x;
    l.w = side_w;
    if g.side_closed {
        side_strip(l, v, bottom, Action::Toggle("gallery_side_closed".into()));
    } else {
        l.card(side_x, MY, side_w, bottom - MY);
        gallery_side(l, v, g);
    }
    l.mx = x0;
    l.w = inner;
    grid_bottom.max(bottom)
}

/// Linke Spalte der Galerie: Titel, Raster (Kacheln + Monats-Trenner)
fn gallery_grid(l: &mut Layout, v: &View, g: &GalleryView, pics: &Pics) -> f32 {
    let lang = v.lang.as_str();
    let (mx, inner) = (l.mx, l.w);
    let mut y = MY;
    let title = Style::new(26.0, true, HEAD);
    let head = format!("🖼  {}", tr(lang, "nav_gallery", &[]));
    let th = measure(l.f, &head, None, title).1;
    l.label(&head, mx, y + (BTN_H - th) / 2.0, inner, title);
    y += BTN_H + GAP;
    if g.total == 0 {
        return y + l.label(&tr(lang, "no_photo", &[]), mx, y, inner, Style::new(16.0, false, DIM));
    }
    let (cw, ch) = tile_size(g.side_closed, g.cols);
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
                    let x = mx + c as f32 * (cw + GRID_GAP);
                    if let Some(canvas) = l.c.as_deref_mut() {
                        canvas.rounded(x + 1.0, y + 1.0, cw - 2.0, ch - 2.0, 8.0, Some(rgba(CARD_BG, 255)), Some((rgba(BTN_BORDER, 255), 2.0)));
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

/// Seitenpanel der Galerie: ⚙ Einstellungen [›] · Filter · Spalten 3/4/5 · [▲] 1 / 3 [▼]
fn gallery_side(l: &mut Layout, v: &View, g: &GalleryView) {
    let lang = v.lang.as_str();
    let t = |k: &str| tr(lang, k, &[]);
    let (mx, mw) = (l.mx, l.w);
    let x = mx + CARD_PAD;
    let w = mw - 2.0 * CARD_PAD;
    let mut y = MY + CARD_PAD;
    let title = Style::new(22.0, true, HEAD);
    let head = format!("⚙  {}", t("panel_settings"));
    let th = measure(l.f, &head, None, title).1;
    l.label(&head, x, y + (BTN_H - th) / 2.0, w - BTN_H - 8.0, title);
    l.button("›", x + w - BTN_H, y, BTN_H, false, Action::Toggle("gallery_side_closed".into()));
    y += BTN_H + GAP;
    l.mx = x;
    l.w = w;
    // Filter: Alle · 📝 Text · 🔳 QR-Code · 🖼 Bild · 🎞 GIF/VID (wie in der Desktop-Galerie)
    let section = Style::new(16.0, false, SECTION);
    y += l.label(&t("vr_gallery_filter"), x, y, w, section) + 4.0;
    let filters: Vec<(String, String)> = [
        ("", t("filter_all")),
        ("text", format!("📝 {}", t("tag_text"))),
        ("qr", format!("🔳 {}", t("tag_qr"))),
        ("image", format!("🖼 {}", t("tag_image"))),
        ("gif_vid", format!("🎞 {}", t("tag_gif_vid"))),
    ]
    .into_iter()
    .map(|(k, text)| (k.to_string(), text))
    .collect();
    for row in filters.chunks(2) {
        y = l.choices_n(y, row, 2, &g.filter, |k| Action::GalFilter(k.to_string())) + 6.0;
    }
    y += GAP - 6.0;
    // Spalten im Raster
    y += l.label(&t("vr_gallery_cols"), x, y, w, section) + 4.0;
    let cols: Vec<(String, String)> = GALLERY_COLS.iter().map(|c| (c.to_string(), c.to_string())).collect();
    y = l.choices(y, &cols, &g.cols.to_string(), |c| Action::Layer("gallery_cols".into(), c.to_string())) + GAP;
    // Blättern
    let dim = Style::new(16.0, false, DIM);
    let iw = 64.0;
    let bw = (w - iw - 16.0) / 2.0;
    if g.page > 0 {
        l.button("▲", x, y, bw, false, Action::GalPage(-1));
    } else {
        l.dead_button("▲", x, y, bw);
    }
    let info = format!("{} / {}", g.page + 1, g.pages.max(1));
    let (tw, th) = measure(l.f, &info, None, dim);
    l.label(&info, x + bw + 8.0 + (iw - tw) / 2.0, y + (BTN_H - th) / 2.0, iw, dim);
    if g.page + 1 < g.pages {
        l.button("▼", x + w - bw, y, bw, false, Action::GalPage(1));
    } else {
        l.dead_button("▼", x + w - bw, y, bw);
    }
    l.mx = mx;
    l.w = mw;
}

/// Ein Foto groß – mit allen Aktionen wie in der Desktop-Galerie; gibt die Unterkante zurück
fn single_content(l: &mut Layout, v: &View, pics: &Pics) -> f32 {
    let lang = v.lang.as_str();
    let t = |k: &str| tr(lang, k, &[]);
    let inner = l.w;
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

/// Breite des Inhalts (🖼 Foto groß)
pub fn content_w() -> f32 {
    WIDE - 2.0 * MX
}

/// Breite des Seitenpanels rechts (offen / eingeklappt)
fn side_w(closed: bool) -> f32 {
    if closed {
        STRIP_W
    } else {
        SIDE_W
    }
}

/// Linke Spalte neben dem Seitenpanel (🌐 Foto, 🖼 Raster)
pub fn main_w(side_closed: bool) -> f32 {
    WIDE - 2.0 * MX - COL_GAP - side_w(side_closed)
}

/// 🖼 Spalten aus layer.json („gallery_cols“) – nur 3 / 4 / 5, sonst 4
pub fn gallery_cols(value: f64) -> usize {
    GALLERY_COLS.into_iter().find(|c| *c as f64 == value.round()).unwrap_or(GRID_COLS)
}

/// Pixel-Breite des Panel-Bilds je Seite (🌐 / ⚙ breiter, 🖼 Galerie wie bisher)
pub fn page_width(_page: Page) -> f32 {
    WIDE
}

/// 🌐 So breit darf das Foto links neben dem Seitenpanel sein
pub fn photo_w(side_closed: bool) -> f32 {
    main_w(side_closed)
}

/// Größe einer Kachel im Galerie-Raster (außen, mit Rand) – wie VRPanel.tile_size
pub fn tile_size(side_closed: bool, cols: usize) -> (u32, u32) {
    let cols = cols.max(1) as f32;
    let w = ((main_w(side_closed) - (cols - 1.0) * GRID_GAP) / cols).floor();
    (w as u32, (w * THUMB_RATIO).round() as u32)
}

/// Platz für das Raster: Panel-Höhe minus Rand, Kopf und Tab-Leiste (wie VRPanel.grid_height)
pub fn grid_room(fixed_height: Option<f32>, tile_h: u32) -> f32 {
    (fixed_height.unwrap_or(GALLERY_H) - 2.0 * MY - (BTN_H + GAP) - (NAV_H + GAP)).max(MONTH_H + tile_h as f32)
}

/// Fotos (Monat je Foto, neueste zuerst) → Raster-Seiten wie VRPanel.gallery_pages:
/// Zeilen mit bis zu GRID_COLS Fotos desselben Monats, ein Trenner je Monat; geht ein
/// Monat auf der nächsten Seite weiter, steht sein Trenner dort nochmal oben.
pub fn gallery_pages(months: &[(i32, u32)], titles: impl Fn(i32, u32) -> String, room: f32, cols: usize, tile_h: u32) -> Vec<Vec<GRow>> {
    let ch = tile_h as f32;
    let mut rows: Vec<((i32, u32), Vec<usize>)> = Vec::new();
    for (i, ym) in months.iter().enumerate() {
        match rows.last_mut() {
            Some((m, cur)) if m == ym && cur.len() < cols => cur.push(i),
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
    let img = image::open(crate::paths::preview_of(path)).ok()?;
    let mut out = img.resize_to_fill(w, h, image::imageops::FilterType::Triangle).to_rgba8();
    if crate::paths::is_video(path) {
        play_badge(&mut out);
    }
    Some(out)
}

/// 🎬 Video: weißes ▶ in einem dunklen Kreis in der Mitte (wie draw_play_badge in widgets.py)
pub fn play_badge(img: &mut image::RgbaImage) {
    let (w, h) = (img.width() as f32, img.height() as f32);
    let r = (w.min(h) / 6.0).max(12.0);
    let (cx, cy) = (w / 2.0, h / 2.0);
    let s = r * 0.55;
    for (x, y, px) in img.enumerate_pixels_mut() {
        let (dx, dy) = (x as f32 + 0.5 - cx, y as f32 + 0.5 - cy);
        if dx * dx + dy * dy > r * r {
            continue;
        }
        // Dreieck: links senkrechte Kante bei -0.6 s, Spitze bei +s
        let inside = dx >= -s * 0.6 && dx <= s && dy.abs() <= s * (s - dx) / (1.6 * s);
        let (c, a) = if inside { ([255u8, 255, 255], 1.0) } else { ([0u8, 0, 0], 150.0 / 255.0) };
        for k in 0..3 {
            px[k] = (px[k] as f32 * (1.0 - a) + c[k] as f32 * a).round() as u8;
        }
    }
}

/// Foto so verkleinert/vergrößert, dass es in w × h passt (Seitenverhältnis bleibt)
pub fn fit_photo(path: &std::path::Path, w: u32, h: u32) -> Option<image::RgbaImage> {
    Some(fit_image(image::open(crate::paths::preview_of(path)).ok()?, w, h))
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

/// Text aus der Einstellungs-Liste: "=1:1" = genau so, sonst i18n-Schlüssel
fn spec_text(lang: &str, key: &str) -> String {
    match key.strip_prefix('=') {
        Some(literal) => literal.to_string(),
        None => tr(lang, key, &[]),
    }
}

/// Zahl aus layer.json (true/false zählt als 1/0, fehlt → 0)
fn layer_num(layer: &serde_json::Map<String, serde_json::Value>, key: &str) -> i64 {
    match layer.get(key) {
        Some(serde_json::Value::Number(n)) => n.as_f64().unwrap_or(0.0).round() as i64,
        Some(serde_json::Value::String(t)) => t.trim().parse::<f64>().map(|f| f.round() as i64).unwrap_or(0),
        Some(serde_json::Value::Bool(b)) => i64::from(*b),
        _ => 0,
    }
}

fn layer_str(layer: &serde_json::Map<String, serde_json::Value>, key: &str) -> String {
    match layer.get(key) {
        Some(serde_json::Value::String(t)) => t.clone(),
        Some(serde_json::Value::Null) | None => String::new(),
        Some(v) => v.to_string(),
    }
}

/// Schieber-Wert auf Schrittweite + Grenzen bringen (wie vr_settings.snap)
pub fn snap(item: &serde_json::Value, value: f32) -> i64 {
    let lo = item["min"].as_i64().unwrap_or(0);
    let hi = item["max"].as_i64().unwrap_or(100);
    let step = item["step"].as_i64().unwrap_or(1).max(1);
    let v = lo + ((value - lo as f32) / step as f32).round() as i64 * step;
    v.clamp(lo, hi)
}

/// Eintrag der Einstellungs-Liste zu einem layer.json-Schlüssel
pub fn spec_item(key: &str) -> Option<&'static serde_json::Value> {
    crate::i18n::vr_settings()["tabs"]
        .as_array()?
        .iter()
        .flat_map(|t| t["groups"].as_array().into_iter().flatten())
        .flat_map(|g| g["items"].as_array().into_iter().flatten())
        .find(|i| i["key"].as_str() == Some(key))
}

/// ⚙ Einstellungs-Seite: links die Kategorien (📸 Shot / 🥽 VR mit ihren Gruppen),
/// rechts das Untermenü der gewählten Kategorie – wie die Welt-Menüs in VRChat
fn settings_content(l: &mut Layout, v: &View, s: &SettingsView) -> f32 {
    let lang = v.lang.as_str();
    let (x0, inner) = (l.mx, l.w);
    let mut y = MY;
    let title = Style::new(26.0, true, HEAD);
    let head = format!("⚙  {}", tr(lang, "panel_settings", &[]));
    let th = measure(l.f, &head, None, title).1;
    l.label(&head, x0, y + (BTN_H - th) / 2.0, inner, title);
    y += BTN_H + GAP;
    let top = y;
    let spec = crate::i18n::vr_settings();
    let tabs = spec["tabs"].as_array().cloned().unwrap_or_default();
    let groups: Vec<&serde_json::Value> = tabs.iter().flat_map(|t| t["groups"].as_array().into_iter().flatten()).collect();
    let chosen = s
        .open
        .as_deref()
        .and_then(|id| groups.iter().find(|g| g["id"].as_str() == Some(id)))
        .or(groups.first())
        .copied();

    // links: Kategorien
    let section = Style::new(18.0, true, SECTION);
    for tab in &tabs {
        // Überschrift ▾ 📸 Shot / ▸ 🥽 VR – antippen klappt ihre Kategorien ein/aus
        let tid = tab["id"].as_str().unwrap_or("");
        let folded = s.folded.iter().any(|f| f == tid);
        let head = format!("{}  {}", if folded { "▸" } else { "▾" }, tr(lang, tab["label"].as_str().unwrap_or(""), &[]));
        let hh = 40.0;
        let th = measure(l.f, &head, None, section).1;
        l.label(&head, x0 + 6.0, y + (hh - th) / 2.0, CAT_W, section);
        l.hits.push(([x0, y, CAT_W, hh], Action::FoldTab(tid.to_string())));
        y += hh + 4.0;
        if folded {
            continue;
        }
        for group in tab["groups"].as_array().into_iter().flatten() {
            let gid = group["id"].as_str().unwrap_or("");
            let on = chosen.is_some_and(|c| c["id"].as_str() == Some(gid));
            let icon = group["icon"].as_str().unwrap_or("");
            let name = tr(lang, group["title"].as_str().unwrap_or(""), &[]);
            let text = if icon.is_empty() { name } else { format!("{icon}  {name}") };
            if let Some(c) = l.c.as_deref_mut() {
                c.rounded(x0 + 0.5, y + 0.5, CAT_W - 1.0, GROUP_H - 1.0, 6.0, Some(rgba(if on { CAT_BG } else { BTN_BG }, 255)), Some((rgba(BTN_BORDER, 255), 1.0)));
                c.rounded(x0 + 1.0, y + GROUP_H - 3.0, CAT_W - 2.0, 2.0, 1.0, Some(rgba(if on { HEAD } else { BLUE }, 255)), None);
                // zu lang → etwas kleiner statt umbrechen
                let fg = if on { 0x8fb6ff } else { BTN_TEXT };
                let mut st = Style::new(20.0, true, fg);
                while st.size > 12.0 && measure(l.f, &text, None, st).0 > CAT_W - 48.0 {
                    st = Style::new(st.size - 1.0, true, fg);
                }
                let th = measure(l.f, &text, None, st).1;
                c.text(l.f, &text, x0 + 14.0, y + (GROUP_H - th) / 2.0, None, st);
                if on {
                    let ast = Style::new(26.0, true, HEAD);
                    let (aw, ah) = measure(l.f, "›", None, ast);
                    c.text(l.f, "›", x0 + CAT_W - 14.0 - aw, y + (GROUP_H - ah) / 2.0, None, ast);
                }
            }
            l.hits.push(([x0, y, CAT_W, GROUP_H], Action::Group(gid.to_string())));
            y += GROUP_H + 6.0;
        }
        y += 6.0;
    }
    let left_bottom = y - 12.0;

    // rechts: Untermenü der gewählten Kategorie (als Karte)
    let Some(group) = chosen else { return left_bottom };
    let rx = x0 + CAT_W + COL_GAP;
    let rw = inner - CAT_W - COL_GAP;
    let sub = |l: &mut Layout| {
        let mut y = top + CARD_PAD;
        let icon = group["icon"].as_str().unwrap_or("");
        let name = tr(lang, group["title"].as_str().unwrap_or(""), &[]);
        let text = if icon.is_empty() { name } else { format!("{icon}  {name}") };
        y += l.label(&text, l.mx, y, l.w, Style::new(22.0, true, HEAD)) + GAP;
        for item in group["items"].as_array().into_iter().flatten() {
            y = setting_item(l, v, s, item, y) + 10.0;
        }
        y - 10.0
    };
    l.mx = rx + CARD_PAD;
    l.w = rw - 2.0 * CARD_PAD;
    let right_bottom = l.measure_with(sub) + CARD_PAD;
    let bottom = left_bottom.max(right_bottom);
    l.card(rx, top, rw, bottom - top);
    sub(l);
    l.mx = x0;
    l.w = inner;
    bottom
}

/// Ein Eintrag der Einstellungs-Liste – gibt die Unterkante zurück
fn setting_item(l: &mut Layout, v: &View, s: &SettingsView, item: &serde_json::Value, mut y: f32) -> f32 {
    let lang = v.lang.as_str();
    let (mx, inner) = (l.mx, l.w);
    let section = Style::new(17.0, false, SECTION);
    let t = |k: &str| tr(lang, k, &[]);
    let key = item["key"].as_str().unwrap_or("");
    let label = item["label"].as_str().unwrap_or("");
    match item["type"].as_str().unwrap_or("") {
        "toggle" => {
            let on = layer_num(&s.layer, key) != 0;
            let text = format!("{}  {}", if on { "✔" } else { "✕" }, t(label));
            l.button(&text, mx, y, inner, on, Action::Toggle(key.to_string()));
            y + BTN_H
        }
        "choice" => {
            if !label.is_empty() {
                y += l.label(&t(label), mx, y, inner, section) + 4.0;
            }
            let options: Vec<(String, String)> = item["options"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|o| (o[0].as_str().unwrap_or("").to_string(), spec_text(lang, o[1].as_str().unwrap_or(""))))
                .collect();
            let cols = match item["cols"].as_u64().unwrap_or(0) as usize {
                0 => options.len().max(1),
                n => n,
            };
            let chosen = layer_str(&s.layer, key);
            let make = |value: &str| {
                if key == "panel_anchor" {
                    Action::Anchor(value.to_string())
                } else {
                    Action::Layer(key.to_string(), value.to_string())
                }
            };
            for row in options.chunks(cols) {
                y = l.choices_n(y, row, cols, &chosen, make) + 6.0;
            }
            y - 6.0
        }
        "slider" => {
            let (lo, hi) = (item["min"].as_i64().unwrap_or(0), item["max"].as_i64().unwrap_or(100));
            let current = if key == "@button_cm" { s.button_cm.map(i64::from) } else { Some(layer_num(&s.layer, key)) };
            let text = match (current, item["fmt"].as_str().filter(|f| !f.is_empty())) {
                (None, _) => format!("{}  {}", t(label), t("panel_size_later")),
                (Some(c), Some(fmt)) => tr(lang, fmt, &[("v", &c.to_string()), ("inv", &(lo + hi - c).to_string())]),
                (Some(c), None) => format!("{}:  {c}{}", t(label), item["unit"].as_str().unwrap_or("")),
            };
            y += l.label(&text, mx, y, inner, section) + 4.0;
            let frac = (current.unwrap_or(lo) - lo) as f32 / (hi - lo).max(1) as f32;
            l.bar(y, frac.clamp(0.0, 1.0), current.is_some(), Action::Slider(key.to_string()))
        }
        "size" => {
            let pages: Vec<(String, String)> = crate::i18n::vr_settings()["size_pages"]
                .as_array()
                .into_iter()
                .flatten()
                .map(|p| (p[0].as_str().unwrap_or("").to_string(), t(p[1].as_str().unwrap_or(""))))
                .collect();
            let name = pages.iter().find(|p| p.0 == s.size_page.key()).map(|p| p.1.clone()).unwrap_or_default();
            let text = match s.size_cm {
                Some(cm) => format!("{} · {name}:  {cm} cm", t("panel_size")),
                None => format!("{} · {name}  {}", t("panel_size"), t("panel_size_later")),
            };
            y += l.label(&text, mx, y, inner, section) + 4.0;
            y = l.choices(y, &pages, s.size_page.key(), |p| Action::SizePage(p.to_string())) + 4.0;
            let default = PAGE_SIZE_DEFAULT.iter().find(|d| d.0 == s.size_page.key()).map(|d| (d.1 * 100.0) as i32).unwrap_or(32);
            let cm = s.size_cm.unwrap_or(default);
            let frac = (cm - SIZE_CM.0) as f32 / (SIZE_CM.1 - SIZE_CM.0) as f32;
            l.bar(y, frac.clamp(0.0, 1.0), s.size_cm.is_some(), Action::Slider("@size".into()))
        }
        "actions" => {
            let actions = item["actions"].as_array().cloned().unwrap_or_default();
            let n = actions.len().max(1) as f32;
            let w = (inner - 8.0 * (n - 1.0)) / n;
            for (i, a) in actions.iter().enumerate() {
                let x = mx + i as f32 * (w + 8.0);
                let text = t(a[1].as_str().unwrap_or(""));
                if a[0].as_str() == Some("move") {
                    l.button(&format!("{}  {text}", if v.edit { "✔" } else { "✥" }), x, y, w, v.edit, Action::Move);
                } else {
                    l.button(&format!("⟲  {text}"), x, y, w, false, Action::Reset);
                }
            }
            y + BTN_H
        }
        "colors" => {
            let current = layer_str(&s.layer, key);
            let gap = 6.0;
            let sw = (inner - gap * (BUTTON_COLORS.len() as f32 - 1.0)) / BUTTON_COLORS.len() as f32;
            for (i, color) in BUTTON_COLORS.iter().enumerate() {
                let x = mx + i as f32 * (sw + gap);
                let hex = u32::from_str_radix(color.trim_start_matches('#'), 16).unwrap_or(BLUE);
                let chosen = current.eq_ignore_ascii_case(color);
                if let Some(c) = l.c.as_deref_mut() {
                    let border = if chosen { 0xffffff } else { 0x2b3240 };
                    c.rounded(x + 1.5, y + 1.5, sw - 3.0, BTN_H - 3.0, 10.0, Some(rgba(hex, 255)), Some((rgba(border, 255), 3.0)));
                }
                if chosen {
                    let st = Style::new(22.0, true, 0x10131a);
                    let (tw, th) = measure(l.f, "✔", None, st);
                    l.label("✔", x + (sw - tw) / 2.0, y + (BTN_H - th) / 2.0, sw, st);
                }
                l.hits.push(([x, y, sw, BTN_H], Action::Layer(key.to_string(), color.to_string())));
            }
            y + BTN_H
        }
        "list" => {
            let dim = Style::new(16.0, false, SECTION);
            y += l.label(&t(item["hint"].as_str().unwrap_or("")), mx, y, inner, dim) + 6.0;
            let entries: Vec<String> = s
                .layer
                .get(key)
                .and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|e| e.as_str().map(String::from)).collect())
                .unwrap_or_default();
            if entries.is_empty() {
                return y + l.label(&t(item["empty"].as_str().unwrap_or("")), mx, y, inner, section);
            }
            for name in entries {
                l.button(&format!("✕  {name}"), mx, y, inner, false, Action::ListRemove(key.to_string(), name.clone()));
                y += BTN_H + 6.0;
            }
            y - 6.0
        }
        _ => y,
    }
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

/// Breite einer Seite in VR (cm): die offene aus panel_pose.json, die anderen aus
/// panel_sizes.json (oder Standard) – wie vr_panel.page_width_cm
pub fn page_width_cm(page: Page) -> Option<i32> {
    let now = width_cm()?;
    if page == current_page() {
        return Some(now);
    }
    let sizes: serde_json::Value = std::fs::read_to_string(sizes_file()).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or_default();
    let default = PAGE_SIZE_DEFAULT.iter().find(|d| d.0 == page.key()).map(|d| d.1).unwrap_or(0.32);
    Some((sizes[page.key()]["width"].as_f64().unwrap_or(default) * 100.0).round() as i32)
}

/// Größe einer Seite ändern – die offene sofort in VR, die anderen beim nächsten Wechsel
pub fn set_page_width_cm(page: Page, cm: i32) -> bool {
    use serde_json::{json, Value};
    if page == current_page() {
        return set_width_cm(cm);
    }
    if width_cm().is_none() {
        return false;
    }
    let file = sizes_file();
    let mut sizes = std::fs::read_to_string(&file)
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}));
    let default = PAGE_SIZE_DEFAULT.iter().find(|d| d.0 == page.key()).map(|d| d.1).unwrap_or(0.32);
    let old = sizes[page.key()]["width"].as_f64().unwrap_or(default);
    let new = cm.clamp(SIZE_CM.0, SIZE_CM.1) as f64 / 100.0;
    let height = sizes[page.key()]["height"].as_f64().map(|h| json!(h * new / old)).unwrap_or(Value::Null);
    sizes[page.key()] = json!({"width": new, "height": height});
    crate::settings::write_json(&file, &sizes, 2).is_ok()
}

pub fn width_cm() -> Option<i32> {
    let text = std::fs::read_to_string(crate::paths::panel_pose_file()).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    Some((v["width"].as_f64()? * 100.0).round() as i32)
}

/// Von Hand gezogene Höhe (panel_pose.json) → Pixel-Höhe (bei dieser Seiten-Breite)
pub fn fixed_height(page: Page) -> Option<f32> {
    let text = std::fs::read_to_string(crate::paths::panel_pose_file()).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    let width = v["width"].as_f64()?;
    let height = v["height"].as_f64()?;
    if width <= 0.0 || height <= 0.0 {
        return None;
    }
    Some((page_width(page) as f64 * height / width).round().max(160.0) as f32)
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
            method_label: "Lingva (anonym, kein Konto nötig)".into(),
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
        assert_eq!(size.0 as f32, WIDE);
        // Seitenpanel rechts: Dienst, Von, Nach, Aufgabe, einklappen
        let (r, _) = hits.iter().find(|h| h.1 == Action::Choose(Choice::Method)).unwrap();
        assert!(r[0] > WIDE - MX - SIDE_W, "Dienst steht rechts im Seitenpanel");
        let (u, y) = ((r[0] + 20.0) / size.0 as f32, (r[1] + 20.0) / size.1 as f32);
        assert_eq!(hit(&hits, size, u, y).map(|h| h.0), Some(Action::Choose(Choice::Method)));
        for a in [Action::Choose(Choice::Source), Action::Choose(Choice::Target), Action::Choose(Choice::Mode), Action::Redo,
                  Action::Toggle("panel_side_closed".into()), Action::Toggle("rec_video".into()),
                  Action::Toggle("panel_hide_photo".into()), Action::Toggle("overlay".into()),
                  Action::Layer("gesture_mode".into(), "auto".into())] {
            assert!(hits.iter().any(|h| h.1 == a), "{a:?} fehlt");
        }
        // eingeklappt: nur die Leiste „Einstellungen“ – antippen klappt wieder auf
        let (c_closed, hits_closed, _) = render(&mut f, &View { side_closed: true, ..view() }, &Pics::default()).unwrap();
        assert_eq!(c_closed.pix.width(), c.pix.width(), "Breite bleibt gleich");
        assert!(!hits_closed.iter().any(|h| h.1 == Action::Choose(Choice::Method)));
        let (r, _) = hits_closed.iter().find(|h| h.1 == Action::Toggle("panel_side_closed".into())).unwrap();
        assert!(r[2] <= STRIP_W + 0.5 && r[0] > WIDE / 2.0);
        assert!(photo_w(true) > photo_w(false), "eingeklappt → Foto breiter");
        if let Some(out) = std::env::var_os("PANEL_OUT_CLOSED") {
            c_closed.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // feste Größe: wenig / kein Text, Foto aus → Panel bleibt gleich hoch
        let mut h = |v: View| render(&mut f, &v, &Pics::default()).unwrap().0.pix.height();
        let full = h(view());
        assert_eq!(h(View { result: "kurz".into(), lines: Vec::new(), ..view() }), full);
        assert_eq!(h(View { result: String::new(), status: String::new(), lines: Vec::new(), ..view() }), full);
        assert_eq!(h(View { hide_photo: true, result: "kurz".into(), lines: Vec::new(), ..view() }), full);
        if let Some(out) = std::env::var_os("PANEL_OUT_EMPTY") {
            let (c, _, _) = render(&mut f, &View { hide_photo: true, result: "Hallo".into(), lines: Vec::new(), ..view() }, &Pics::default()).unwrap();
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // 🖼 ▲: Foto weg → mehr Zeilen pro Seite
        let (_, _, pages_full) = render(&mut f, &View { hide_photo: true, ..view() }, &Pics::default()).unwrap();
        assert!(pages_full < pages, "ohne Foto passt mehr Text auf eine Seite");
        // 🟠 Layer veraltet: i-Knopf oben, angetippt erscheint der Hinweis darunter
        assert!(!hits.iter().any(|h| h.1 == Action::OldNote));
        let old = View { layer_old: Some("⚠ Layer veraltet".into()), ..view() };
        let (_, hits_old, _) = render(&mut f, &old, &Pics::default()).unwrap();
        let (r, _) = hits_old.iter().find(|h| h.1 == Action::OldNote).unwrap();
        assert!(r[1] < MY + 1.0);
        let down_y = |h: &Hits| h.iter().find(|x| x.1 == Action::Page(1)).unwrap().0[1];
        let (_, hits_open, _) = render(&mut f, &View { old_open: true, ..old }, &Pics::default()).unwrap();
        assert!(down_y(&hits_open) > down_y(&hits_old), "Hinweis schiebt den Rest nach unten");
        assert!(hits.iter().any(|h| h.1 == Action::Page(1)) && !hits.iter().any(|h| h.1 == Action::Page(-1)));
        for p in PAGES {
            assert!(hits.iter().any(|h| h.1 == Action::Goto(p)), "Tab {p:?} fehlt");
        }
        if let Some(out) = std::env::var_os("PANEL_OUT") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // ⚙ Einstellungs-Seite: Tabs, Gruppen, Schieber liefert die Position
        let layer: serde_json::Map<String, serde_json::Value> =
            serde_json::from_str(crate::settings::LAYER_DEFAULTS).unwrap();
        let settings = |tab: &str, open: Option<&str>| View {
            lang: "de".into(),
            page: Page::Settings,
            settings: Some(SettingsView {
                tab: tab.into(),
                open: open.map(String::from),
                folded: Vec::new(),
                layer: layer.clone(),
                size_page: Page::Translate,
                size_cm: Some(32),
                button_cm: Some(5),
            }),
            fixed_height: Some(300.0),
            ..view()
        };
        let (c, hits, _) = render(&mut f, &settings("shot", None), &Pics::default()).unwrap();
        assert!(c.pix.height() > 300, "⚙ Seite ignoriert die von Hand gezogene Höhe");
        // links alle Kategorien beider Tabs, rechts die erste (🎞 GIF) aufgeklappt
        for a in [Action::Group("gif".into()), Action::Group("excluded".into()), Action::Group("panel".into()),
                  Action::Group("overlay".into()), Action::Goto(Page::Translate)] {
            assert!(hits.iter().any(|h| h.1 == a), "{a:?} fehlt");
        }
        let (r, _) = hits.iter().find(|h| h.1 == Action::Slider("gif_max_s".into())).unwrap();
        assert!(r[0] > MX + CAT_W, "Untermenü rechts neben den Kategorien");
        assert!(hits.iter().any(|h| h.1 == Action::FoldTab("shot".into())) && hits.iter().any(|h| h.1 == Action::FoldTab("vr".into())));
        // 📸 Shot eingeklappt → seine Kategorien weg, 🥽 VR bleibt
        let mut folded = settings("shot", None);
        folded.settings.as_mut().unwrap().folded = vec!["shot".into()];
        let (c_fold, hits_f, _) = render(&mut f, &folded, &Pics::default()).unwrap();
        assert!(!hits_f.iter().any(|h| h.1 == Action::Group("eye".into())) && hits_f.iter().any(|h| h.1 == Action::Group("panel".into())));
        if let Some(out) = std::env::var_os("PANEL_OUT_FOLD") {
            c_fold.save(std::path::Path::new(&out), &[]).unwrap();
        }
        if let Some(out) = std::env::var_os("PANEL_OUT_SET") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        let (_, hits, _) = render(&mut f, &settings("shot", Some("gif")), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::Toggle("gif_hold".into())));
        assert!(hits.iter().any(|h| h.1 == Action::Layer("gif_stabilize".into(), "smooth".into())));
        let (_, hits, _) = render(&mut f, &settings("shot", Some("excluded")), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::ListRemove("excluded_apps".into(), "wayvr".into())));
        let (_, hits, _) = render(&mut f, &settings("shot", Some("icon")), &Pics::default()).unwrap();
        let icons: Vec<_> = hits.iter().filter(|h| matches!(&h.1, Action::Layer(k, _) if k == "icon_position")).collect();
        assert_eq!(icons.len(), 4);
        assert!(icons[2].0[1] > icons[0].0[1], "2 × 2 Raster");
        let (c, hits, _) = render(&mut f, &settings("vr", Some("panel")), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::Anchor("head".into())) && hits.iter().any(|h| h.1 == Action::Move));
        let (r, _) = hits.iter().find(|h| h.1 == Action::Slider("@size".into())).unwrap();
        let size = (c.pix.width(), c.pix.height());
        let u = (r[0] + BAR_PAD + 0.75 * (r[2] - 2.0 * BAR_PAD)) / size.0 as f32;
        let (a, frac) = hit(&hits, size, u, (r[1] + 10.0) / size.1 as f32).unwrap();
        assert_eq!(a, Action::Slider("@size".into()));
        assert!((frac - 0.75).abs() < 0.01);
        let eye = spec_item("eye_mix").unwrap();
        assert_eq!(snap(eye, 47.0), 45);
        assert_eq!(snap(eye, 120.0), 100);
        if let Some(out) = std::env::var_os("PANEL_OUT2") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
    }

    #[test]
    fn tiles_fit_and_pages_switch() {
        for (closed, cols) in [(false, 3), (false, 4), (false, 5), (true, 4)] {
            let (w, h) = tile_size(closed, cols);
            assert!(w as f32 * cols as f32 + GRID_GAP * (cols as f32 - 1.0) <= main_w(closed) + 0.5);
            assert_eq!(h, (w as f32 * THUMB_RATIO).round() as u32);
        }
        assert!(tile_size(true, 4).0 > tile_size(false, 4).0, "eingeklappt → größere Kacheln");
        assert_eq!((gallery_cols(5.0), gallery_cols(7.0), gallery_cols(0.0)), (5, 4, 4));
        assert_eq!(Page::from_key("gallery"), Page::Gallery);
        assert_eq!(Page::from_key("?"), Page::Translate);
        // gleicher Platz fürs Raster wie in vr_panel.py (GALLERY_H − Rand − Kopf − Tabs)
        assert_eq!(grid_room(None, 117), 608.0);
    }

    fn sample_months() -> Vec<(i32, u32)> {
        std::iter::repeat_n((2026, 10), 6).chain(std::iter::repeat_n((2026, 6), 15)).collect()
    }

    #[test]
    fn gallery_pages_like_the_app() {
        // 6 Fotos Oktober + 15 Fotos Juni, 4 Spalten → wie VRPanel.gallery_pages: [6 Zeilen, 3 Zeilen]
        let th = tile_size(false, 4).1;
        let pages = gallery_pages(&sample_months(), |y, m| format!("{y}-{m}"), grid_room(None, th), 4, th);
        assert_eq!(pages.iter().map(Vec::len).collect::<Vec<_>>(), [6, 3]);
        assert_eq!(pages[0][0], GRow::Month("2026-10".into()));
        assert_eq!(pages[0][1], GRow::Tiles(vec![0, 1, 2, 3]));
        assert_eq!(pages[0][2], GRow::Tiles(vec![4, 5]));
        assert_eq!(pages[0][3], GRow::Month("2026-6".into()));
        // Juni geht auf Seite 2 weiter → Trenner dort nochmal oben
        assert_eq!(pages[1][0], GRow::Month("2026-6".into()));
        assert!(gallery_pages(&[], |_, _| String::new(), 600.0, 4, th)[0].is_empty());
        // 3 Spalten → Oktober in zwei vollen Zeilen
        let th3 = tile_size(false, 3).1;
        let pages3 = gallery_pages(&sample_months(), |y, m| format!("{y}-{m}"), grid_room(None, th3), 3, th3);
        assert_eq!(pages3[0][1..3], [GRow::Tiles(vec![0, 1, 2]), GRow::Tiles(vec![3, 4, 5])]);
    }

    #[test]
    fn gallery_nav_and_single_view() {
        let mut f = Fonts::new();
        let (tw, th) = tile_size(false, 4);
        let pages = gallery_pages(&sample_months(), |y, m| format!("{y} {m}"), grid_room(None, th), 4, th);
        let tile_of = |i: usize| Tile { index: i, path: PathBuf::from(format!("/x/ViewShot_{i}.png")), mtime: None };
        let tiles: Vec<Tile> =
            pages[0].iter().flat_map(|r| if let GRow::Tiles(t) = r { t.clone() } else { vec![] }).map(tile_of).collect();
        let g = GalleryView {
            total: 21,
            page: 0,
            pages: 2,
            rows: pages[0].clone(),
            tiles: tiles.clone(),
            open: None,
            filter: String::new(),
            cols: 4,
            side_closed: false,
        };
        let thumb_img = image::RgbaImage::from_pixel(tw - 4, th - 4, image::Rgba([200, 80, 160, 255]));
        let pics = Pics { thumbs: vec![Some(&thumb_img); tiles.len()], ..Pics::default() };
        let v = View { page: Page::Gallery, gallery: Some(g.clone()), ..view() };
        let (c, hits, _) = render(&mut f, &v, &pics).unwrap();
        let size = (c.pix.width(), c.pix.height());
        assert_eq!(size.1 as f32, GALLERY_H, "Galerie nutzt die ganze Fläche");
        // Tabs ganz unten, 14 Kacheln (6 Okt + 8 Juni), rechts Seitenpanel: Filter, Spalten, nur ▼ (erste Seite)
        let (r, _) = hits.iter().find(|h| h.1 == Action::Goto(Page::Translate)).unwrap();
        assert!(r[1] + r[3] > size.1 as f32 - MY - 1.0 && r[0] < WIDE / 2.0);
        let (r, _) = hits.iter().find(|h| h.1 == Action::Goto(Page::Settings)).unwrap();
        assert!(r[0] > WIDE / 2.0);
        assert_eq!(hits.iter().filter(|h| matches!(h.1, Action::GalOpen(_))).count(), 14);
        for a in [Action::GalFilter("gif_vid".into()), Action::GalFilter("text".into()), Action::Layer("gallery_cols".into(), "5".into()),
                  Action::Toggle("gallery_side_closed".into())] {
            let (r, _) = hits.iter().find(|h| h.1 == a).unwrap_or_else(|| panic!("{a:?} fehlt"));
            assert!(r[0] > WIDE - MX - SIDE_W - 1.0, "{a:?} steht im Seitenpanel rechts");
        }
        assert!(hits.iter().any(|h| h.1 == Action::GalPage(1)) && !hits.iter().any(|h| h.1 == Action::GalPage(-1)));
        let (r, _) = hits.iter().find(|h| h.1 == Action::GalOpen(4)).unwrap();
        let (u, w) = ((r[0] + r[2] / 2.0) / size.0 as f32, (r[1] + r[3] / 2.0) / size.1 as f32);
        assert_eq!(hit(&hits, size, u, w).map(|h| h.0), Some(Action::GalOpen(4)));
        if let Some(out) = std::env::var_os("PANEL_OUT3") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // eingeklappt: nur die Leiste, Raster breiter
        let closed = View { gallery: Some(GalleryView { side_closed: true, ..g.clone() }), ..v.clone() };
        let (c, hits, _) = render(&mut f, &closed, &pics).unwrap();
        assert!(!hits.iter().any(|h| matches!(h.1, Action::GalFilter(_))));
        let (r, _) = hits.iter().find(|h| h.1 == Action::Toggle("gallery_side_closed".into())).unwrap();
        assert!(r[2] <= STRIP_W + 0.5);
        if let Some(out) = std::env::var_os("PANEL_OUT3C") {
            c.save(std::path::Path::new(&out), &[]).unwrap();
        }
        // Übersetzungs-Seite hat die Tab-Leiste auch
        let (_, hits, _) = render(&mut f, &view(), &Pics::default()).unwrap();
        assert!(hits.iter().any(|h| h.1 == Action::Goto(Page::Gallery)));
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
        assert!(!hits.iter().any(|h| matches!(h.1, Action::Goto(_))));
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
            Action::Settings,
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
        assert!(!hits.iter().any(|h| matches!(h.1, Action::GalOpen(_))) && hits.iter().any(|h| h.1 == Action::Goto(Page::Settings)));
    }

    #[test]
    fn page_sizes_switch_and_remember() {
        let dir = std::env::temp_dir().join(format!("viewshot-sizes-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("linuxvr-viewshot")).unwrap();
        std::env::set_var("XDG_CONFIG_HOME", &dir);
        let pose = crate::paths::panel_pose_file();
        std::fs::write(&pose, r#"{"anchor":"left","width":0.44,"height":0.2}"#).unwrap();
        switch_page_size(Page::Translate, Page::Gallery);
        let p: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&pose).unwrap()).unwrap();
        assert_eq!(p["width"], 0.62);
        assert!(p.get("height").is_none(), "Galerie: Höhe automatisch");
        assert_eq!(current_page(), Page::Gallery);
        switch_page_size(Page::Gallery, Page::Translate);
        let p: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&pose).unwrap()).unwrap();
        assert_eq!((p["width"].as_f64(), p["height"].as_f64()), (Some(0.44), Some(0.2)), "alte Größe zurück");
        assert_eq!(p["anchor"], "left", "Rest der Pose bleibt");
        // ⚙ 🪟 Größe für eine andere Seite: gemerkt, wirkt beim Wechsel
        assert_eq!(page_width_cm(Page::Gallery), Some(62));
        assert_eq!(page_width_cm(Page::Settings), Some(56), "Standard");
        assert!(set_page_width_cm(Page::Settings, 55));
        assert_eq!((page_width_cm(Page::Settings), width_cm()), (Some(55), Some(44)), "offene Seite bleibt");
        switch_page_size(Page::Translate, Page::Settings);
        assert_eq!(width_cm(), Some(55));
        assert!(set_page_width_cm(Page::Settings, 60) && width_cm() == Some(60), "offene Seite sofort");
        std::env::remove_var("XDG_CONFIG_HOME");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
