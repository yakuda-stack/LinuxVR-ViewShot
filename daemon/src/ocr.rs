//! Texterkennung – dieselben PaddleOCR-Modelle und derselbe Ablauf wie RapidOCR
//! in der App (UI/core/ocr.py): Text finden (det) → gerade ausschneiden →
//! auf dem Kopf? (cls) → lesen (rec). Ergebnis wie `ocr.read_lines`:
//! Zeilen mit Text + Rechteck im Originalbild.
//!
//! onnxruntime wird zur Laufzeit geladen (dlopen) – dieselbe Bibliothek, die auch
//! die App benutzt (bei der Installation nach ~/.local/lib/linuxvr-viewshot kopiert).

use crate::imgops::{rotate_crop, Img};
use ort::session::Session;
use ort::value::Tensor;
use std::path::{Path, PathBuf};

pub const DET_MODEL: &str = "PP-OCRv6_det_small.onnx";
pub const CLS_MODEL: &str = "ch_ppocr_mobile_v2.0_cls_mobile.onnx";
pub const REC_MODEL: &str = "PP-OCRv6_rec_small.onnx";

// Werte aus rapidocr/config.yaml
const TEXT_SCORE: f32 = 0.5;
const MIN_SIDE: usize = 30;
const MAX_SIDE: usize = 2000;
const MIN_HEIGHT: usize = 30;
const WIDTH_HEIGHT_RATIO: f32 = 8.0;
const DET_LIMIT_SIDE: usize = 736; // limit_type "min"
const DET_THRESH: f32 = 0.3;
const BOX_THRESH: f32 = 0.5;
const MAX_CANDIDATES: usize = 1000;
const UNCLIP_RATIO: f32 = 1.6;
const MIN_SIZE: f32 = 3.0;
const CLS_SHAPE: (usize, usize) = (48, 192);
const CLS_THRESH: f32 = 0.9;
const REC_SHAPE: (usize, usize) = (48, 320);
const BATCH: usize = 6;
const SORT_Y_THRESHOLD: f32 = 10.0;

#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Line {
    pub text: String,
    /// [x0, y0, x1, y1] im Originalbild (Pixel), None = unbekannt
    pub r#box: Option<[i64; 4]>,
}

pub struct Engine {
    det: Session,
    cls: Session,
    rec: Session,
    chars: Vec<String>,
}

/// Wo liegt libonnxruntime.so? Zuerst unser Ordner (Installation kopiert sie dorthin),
/// dann das System (Arch: onnxruntime-cpu) und Python-Pakete.
pub fn find_onnxruntime() -> Option<PathBuf> {
    if let Some(p) = std::env::var_os("ORT_DYLIB_PATH") {
        return Some(PathBuf::from(p));
    }
    let mut dirs: Vec<PathBuf> = vec![crate::paths::lib_dir()];
    dirs.extend(["/usr/lib", "/usr/lib64", "/usr/local/lib"].iter().map(PathBuf::from));
    let home = dirs::home_dir().unwrap_or_default();
    for base in [home.join(".local/lib"), PathBuf::from("/usr/lib"), PathBuf::from("/usr/local/lib")] {
        if let Ok(rd) = std::fs::read_dir(&base) {
            for e in rd.flatten() {
                let name = e.file_name().to_string_lossy().to_string();
                if name.starts_with("python3") {
                    for sub in ["site-packages", "dist-packages"] {
                        dirs.push(e.path().join(sub).join("onnxruntime/capi"));
                    }
                }
            }
        }
    }
    for dir in dirs {
        let Ok(rd) = std::fs::read_dir(&dir) else { continue };
        let mut found: Vec<PathBuf> = rd
            .flatten()
            .map(|e| e.path())
            .filter(|p| {
                p.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.starts_with("libonnxruntime.so"))
            })
            .collect();
        found.sort();
        if let Some(p) = found.pop() {
            return Some(p);
        }
    }
    None
}

/// Ordner mit den drei Modellen (unser Ordner, sonst rapidocr/models).
pub fn find_models() -> Option<PathBuf> {
    let mut dirs = vec![crate::paths::lib_dir().join("ocr-models")];
    let home = dirs::home_dir().unwrap_or_default();
    dirs.push(home.join(".cache/linuxvr-viewshot/ocr-models"));
    for base in [home.join(".local/lib"), PathBuf::from("/usr/lib"), PathBuf::from("/usr/local/lib")] {
        if let Ok(rd) = std::fs::read_dir(&base) {
            for e in rd.flatten() {
                if e.file_name().to_string_lossy().starts_with("python3") {
                    for sub in ["site-packages", "dist-packages"] {
                        dirs.push(e.path().join(sub).join("rapidocr/models"));
                    }
                }
            }
        }
    }
    dirs.into_iter().find(|d| [DET_MODEL, CLS_MODEL, REC_MODEL].iter().all(|m| d.join(m).is_file()))
}

type Res<T> = Result<T, String>;

fn err<E: std::fmt::Display>(what: &str) -> impl Fn(E) -> String + '_ {
    move |e| format!("{what}: {e}")
}

impl Engine {
    pub fn load() -> Res<Engine> {
        let lib = find_onnxruntime().ok_or("onnxruntime nicht gefunden (in der App einmal „Neu bauen“)")?;
        let models = find_models().ok_or("OCR-Modelle nicht gefunden (in der App einmal „Neu bauen“)")?;
        Self::load_from(&lib, &models)
    }

    pub fn load_from(lib: &Path, models: &Path) -> Res<Engine> {
        static INIT: std::sync::OnceLock<Result<(), String>> = std::sync::OnceLock::new();
        INIT.get_or_init(|| {
            ort::init_from(lib.to_string_lossy().to_string()).with_name("viewshot").commit().map(|_| ()).map_err(|e| e.to_string())
        })
        .clone()
        .map_err(|e| format!("onnxruntime ({}): {e}", lib.display()))?;
        let open = |name: &str| -> Res<Session> {
            // wie RapidOCR: kein Speicher-Vorrat (enable_cpu_mem_arena: false) → deutlich weniger RAM
            let cpu = ort::execution_providers::CPUExecutionProvider::default().with_arena_allocator(false).build();
            Session::builder()
                .and_then(|b| b.with_execution_providers([cpu]))
                .and_then(|b| b.with_memory_pattern(false))
                .and_then(|b| b.with_intra_threads(threads()))
                .and_then(|b| b.commit_from_file(models.join(name)))
                .map_err(err(name))
        };
        let det = open(DET_MODEL)?;
        let cls = open(CLS_MODEL)?;
        let rec = open(REC_MODEL)?;
        let keys = {
            let meta = rec.metadata().map_err(err("Metadaten"))?;
            meta.custom("character").map_err(err("Zeichen"))?.ok_or("Zeichenliste fehlt im Modell")?
        };
        let mut chars = vec!["blank".to_string()];
        chars.extend(splitlines(&keys));
        chars.push(" ".to_string());
        Ok(Engine { det, cls, rec, chars })
    }

    /// Text im Bild lesen → Zeilen (leere und unsichere fallen weg).
    pub fn read(&mut self, path: &Path) -> Res<Vec<Line>> {
        let dynimg = image::open(path).map_err(err("Bild"))?;
        self.read_image(&Img::from_dynamic(&dynimg))
    }

    pub fn read_image(&mut self, ori: &Img) -> Res<Vec<Line>> {
        if ori.w == 0 || ori.h == 0 {
            return Ok(Vec::new());
        }
        // 1) Größe begrenzen (resize_image_within_bounds)
        let (img, ratio_h, ratio_w) = within_bounds(ori);
        // 2) sehr flache Bilder oben/unten auffüllen (apply_vertical_padding)
        let (img, pad_top) = vertical_padding(img);
        // 3) Text finden
        let timing = std::env::var_os("VIEWSHOT_OCR_TIMING").is_some();
        let t = std::time::Instant::now();
        let boxes = self.detect(&img)?;
        if timing {
            eprintln!("det {:?} ({} Bereiche)", t.elapsed(), boxes.len());
        }
        if boxes.is_empty() {
            return Ok(Vec::new());
        }
        let t = std::time::Instant::now();
        let mut crops: Vec<Img> = boxes.iter().map(|b| rotate_crop(&img, b)).collect();
        // 4) auf dem Kopf? → drehen
        self.classify(&mut crops)?;
        if timing {
            eprintln!("crop+cls {:?}", t.elapsed());
        }
        let t = std::time::Instant::now();
        // 5) lesen
        let texts = self.recognize(&crops)?;
        if timing {
            eprintln!("rec {:?}", t.elapsed());
        }
        let mut lines = Vec::new();
        for (b, (text, score)) in boxes.iter().zip(texts) {
            if text.trim().is_empty() || score < TEXT_SCORE {
                continue;
            }
            // zurück ins Originalbild (map_boxes_to_original)
            let pts: Vec<(f32, f32)> = b
                .iter()
                .map(|p| {
                    let x = (p[0] * ratio_w).clamp(0.0, ori.w as f32);
                    let y = ((p[1] - pad_top as f32) * ratio_h).clamp(0.0, ori.h as f32);
                    (x, y)
                })
                .collect();
            let xs = pts.iter().map(|p| p.0);
            let ys = pts.iter().map(|p| p.1);
            let bx = [
                round_half_even(xs.clone().fold(f32::MAX, f32::min)),
                round_half_even(ys.clone().fold(f32::MAX, f32::min)),
                round_half_even(xs.fold(f32::MIN, f32::max)),
                round_half_even(ys.fold(f32::MIN, f32::max)),
            ];
            lines.push(Line { text: text.trim().to_string(), r#box: Some(bx) });
        }
        Ok(lines)
    }

    fn detect(&mut self, img: &Img) -> Res<Vec<[[f32; 2]; 4]>> {
        let (h, w) = (img.h, img.w);
        // DetPreProcess: kleinste Seite auf 736, Vielfaches von 32
        let ratio = if h.min(w) < DET_LIMIT_SIDE {
            DET_LIMIT_SIDE as f32 / h.min(w) as f32
        } else {
            1.0
        };
        let rh = round32((h as f32 * ratio) as usize);
        let rw = round32((w as f32 * ratio) as usize);
        if rh == 0 || rw == 0 {
            return Ok(Vec::new());
        }
        let resized = img.resize(rw, rh);
        let input = to_tensor(&resized, rw);
        let tensor = Tensor::from_array(([1usize, 3, rh, rw], input)).map_err(err("det"))?;
        let out = self.det.run(ort::inputs![tensor]).map_err(err("det"))?;
        let (shape, pred) = out[0].try_extract_tensor::<f32>().map_err(err("det"))?;
        let (ph, pw) = (shape[2] as usize, shape[3] as usize);
        let pred = &pred[..ph * pw];
        Ok(db_postprocess(pred, pw, ph, w, h))
    }

    fn classify(&mut self, crops: &mut [Img]) -> Res<()> {
        let order = argsort_ratio(crops);
        let (ch, cw) = CLS_SHAPE;
        for chunk in order.chunks(BATCH) {
            let mut data = Vec::with_capacity(chunk.len() * 3 * ch * cw);
            for &i in chunk {
                let img = &crops[i];
                let ratio = img.w as f32 / img.h as f32;
                let rw = ((ch as f32 * ratio).ceil() as usize).min(cw).max(1);
                data.extend(norm_padded(&img.resize(rw, ch), cw));
            }
            let tensor = Tensor::from_array(([chunk.len(), 3, ch, cw], data)).map_err(err("cls"))?;
            let out = self.cls.run(ort::inputs![tensor]).map_err(err("cls"))?;
            let (_s, probs) = out[0].try_extract_tensor::<f32>().map_err(err("cls"))?;
            for (n, &i) in chunk.iter().enumerate() {
                let (p0, p180) = (probs[n * 2], probs[n * 2 + 1]);
                if p180 > p0 && p180 > CLS_THRESH {
                    crops[i] = crops[i].rot180();
                }
            }
        }
        Ok(())
    }

    fn recognize(&mut self, crops: &[Img]) -> Res<Vec<(String, f32)>> {
        let order = argsort_ratio(crops);
        let (rh, rw) = REC_SHAPE;
        let mut result = vec![(String::new(), 0.0); crops.len()];
        for chunk in order.chunks(BATCH) {
            let mut max_ratio = rw as f32 / rh as f32;
            for &i in chunk {
                max_ratio = max_ratio.max(crops[i].w as f32 / crops[i].h as f32);
            }
            let width = (rh as f32 * max_ratio) as usize;
            let mut data = Vec::with_capacity(chunk.len() * 3 * rh * width);
            for &i in chunk {
                let img = &crops[i];
                let ratio = img.w as f32 / img.h as f32;
                let resized_w = ((rh as f32 * ratio).ceil() as usize).min(width).max(1);
                data.extend(norm_padded(&img.resize(resized_w, rh), width));
            }
            let tensor = Tensor::from_array(([chunk.len(), 3, rh, width], data)).map_err(err("rec"))?;
            let out = self.rec.run(ort::inputs![tensor]).map_err(err("rec"))?;
            let (shape, preds) = out[0].try_extract_tensor::<f32>().map_err(err("rec"))?;
            let (t, classes) = (shape[1] as usize, shape[2] as usize);
            for (n, &i) in chunk.iter().enumerate() {
                let seq = &preds[n * t * classes..(n + 1) * t * classes];
                result[i] = ctc_decode(seq, t, classes, &self.chars);
            }
        }
        Ok(result)
    }
}

fn threads() -> usize {
    // wie RapidOCR in der App: alle Kerne (die Erkennung dauert nur 1–2 s)
    std::thread::available_parallelism().map(|n| n.get()).unwrap_or(2)
}

/// Python str.splitlines() – trennt auch an \x0b, \x1c … (wichtig: sonst verrutschen die Zeichen!)
pub fn splitlines(s: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '\r' => {
                if chars.peek() == Some(&'\n') {
                    chars.next();
                }
                out.push(std::mem::take(&mut cur));
            }
            '\n' | '\x0b' | '\x0c' | '\x1c' | '\x1d' | '\x1e' | '\u{85}' | '\u{2028}' | '\u{2029}' => {
                out.push(std::mem::take(&mut cur));
            }
            _ => cur.push(c),
        }
    }
    if !cur.is_empty() {
        out.push(cur);
    }
    out
}

fn round32(v: usize) -> usize {
    ((v as f32 / 32.0).round_ties_even() as usize) * 32
}

fn round_half_even(v: f32) -> i64 {
    v.round_ties_even() as i64
}

fn within_bounds(img: &Img) -> (Img, f32, f32) {
    let (mut cur, mut rh, mut rw) = (img.clone(), 1.0f32, 1.0f32);
    if cur.w.max(cur.h) > MAX_SIDE {
        let ratio = MAX_SIDE as f32 / cur.w.max(cur.h) as f32;
        let (nh, nw) = (round32((cur.h as f32 * ratio) as usize), round32((cur.w as f32 * ratio) as usize));
        if nh > 0 && nw > 0 {
            rh = cur.h as f32 / nh as f32;
            rw = cur.w as f32 / nw as f32;
            cur = cur.resize(nw, nh);
        }
    }
    if cur.w.min(cur.h) < MIN_SIDE {
        let ratio = MIN_SIDE as f32 / cur.w.min(cur.h) as f32;
        let (nh, nw) = (round32((cur.h as f32 * ratio) as usize), round32((cur.w as f32 * ratio) as usize));
        if nh > 0 && nw > 0 {
            // wie RapidOCR: Verhältnis bezogen aufs Bild VOR diesem Schritt
            rh = cur.h as f32 / nh as f32;
            rw = cur.w as f32 / nw as f32;
            cur = cur.resize(nw, nh);
        }
    }
    (cur, rh, rw)
}

fn vertical_padding(img: Img) -> (Img, usize) {
    let (h, w) = (img.h, img.w);
    if h <= MIN_HEIGHT || w as f32 / h as f32 > WIDTH_HEIGHT_RATIO {
        let new_h = ((w as f32 / WIDTH_HEIGHT_RATIO) as usize).max(MIN_HEIGHT) * 2;
        let pad = ((new_h as i64 - h as i64).unsigned_abs() / 2) as usize;
        return (img.pad_vertical(pad), pad);
    }
    (img, 0)
}

/// HWC-BGR → CHW, (x/255 - 0.5)/0.5
fn to_tensor(img: &Img, width: usize) -> Vec<f32> {
    let (w, h) = (img.w, img.h);
    let mut out = vec![0f32; 3 * h * width];
    for y in 0..h {
        for x in 0..w {
            let i = (y * w + x) * 3;
            for c in 0..3 {
                out[c * h * width + y * width + x] = (img.data[i + c] as f32 / 255.0 - 0.5) / 0.5;
            }
        }
    }
    out
}

/// normalisiert + rechts mit 0 aufgefüllt bis `width`
fn norm_padded(img: &Img, width: usize) -> Vec<f32> {
    to_tensor(img, width)
}

fn argsort_ratio(imgs: &[Img]) -> Vec<usize> {
    let mut idx: Vec<usize> = (0..imgs.len()).collect();
    idx.sort_by(|&a, &b| {
        let ra = imgs[a].w as f32 / imgs[a].h as f32;
        let rb = imgs[b].w as f32 / imgs[b].h as f32;
        ra.total_cmp(&rb)
    });
    idx
}

fn ctc_decode(seq: &[f32], t: usize, classes: usize, chars: &[String]) -> (String, f32) {
    let mut text = String::new();
    let mut confs = Vec::new();
    let mut prev = usize::MAX;
    for step in 0..t {
        let row = &seq[step * classes..(step + 1) * classes];
        let (mut best, mut prob) = (0usize, f32::MIN);
        for (k, &v) in row.iter().enumerate() {
            if v > prob {
                prob = v;
                best = k;
            }
        }
        let keep = best != prev && best != 0;
        prev = best;
        if keep {
            if let Some(ch) = chars.get(best) {
                text.push_str(ch);
                confs.push(prob);
            }
        }
    }
    let score = if confs.is_empty() { 0.0 } else { confs.iter().sum::<f32>() / confs.len() as f32 };
    (text, score)
}

// ───────────────────────── DB-Nachbearbeitung (Textbereiche) ─────────────────────────

/// Wahrscheinlichkeitskarte → Vierecke im Bild (w×h) – wie DBPostProcess + sorted_boxes.
fn db_postprocess(pred: &[f32], pw: usize, ph: usize, dest_w: usize, dest_h: usize) -> Vec<[[f32; 2]; 4]> {
    // Schwelle + Dilatation 2×2 (Anker in der Mitte → Nachbarn links/oben)
    let seg: Vec<bool> = pred.iter().map(|&v| v > DET_THRESH).collect();
    let mut mask = vec![false; pw * ph];
    for y in 0..ph {
        for x in 0..pw {
            let mut on = false;
            for dy in 0..2 {
                for dx in 0..2 {
                    if x >= dx && y >= dy && seg[(y - dy) * pw + (x - dx)] {
                        on = true;
                    }
                }
            }
            mask[y * pw + x] = on;
        }
    }
    let mut boxes: Vec<([[f32; 2]; 4], f32)> = Vec::new();
    for comp in components(&mask, pw, ph).into_iter().take(MAX_CANDIDATES) {
        let hull = convex_hull(&comp);
        let Some(rect) = min_area_rect(&hull) else { continue };
        if rect.sside() < MIN_SIZE {
            continue;
        }
        let pts = mini_box(&rect);
        let score = box_score_fast(pred, pw, ph, &pts);
        if BOX_THRESH > score {
            continue;
        }
        // unclip: Viereck um distance = Fläche·1.6/Umfang nach außen schieben
        let area = rect.w * rect.h;
        let perim = 2.0 * (rect.w + rect.h);
        let d = area * UNCLIP_RATIO / perim;
        let big = RotRect { w: rect.w + 2.0 * d, h: rect.h + 2.0 * d, ..rect };
        if big.sside() < MIN_SIZE + 2.0 {
            continue;
        }
        let mut pts = mini_box(&big);
        for p in pts.iter_mut() {
            p[0] = (p[0] / pw as f32 * dest_w as f32).round_ties_even().clamp(0.0, dest_w as f32);
            p[1] = (p[1] / ph as f32 * dest_h as f32).round_ties_even().clamp(0.0, dest_h as f32);
        }
        boxes.push((pts, score));
    }
    // filter_det_res: Reihenfolge im Uhrzeigersinn, ins Bild klemmen, Winzlinge weg
    let mut out = Vec::new();
    for (b, _s) in boxes {
        let mut b = order_clockwise(b);
        for p in b.iter_mut() {
            p[0] = p[0].clamp(0.0, dest_w as f32 - 1.0).trunc();
            p[1] = p[1].clamp(0.0, dest_h as f32 - 1.0).trunc();
        }
        let dist = |a: [f32; 2], c: [f32; 2]| ((a[0] - c[0]).powi(2) + (a[1] - c[1]).powi(2)).sqrt() as i64;
        if dist(b[0], b[1]) <= 3 || dist(b[0], b[3]) <= 3 {
            continue;
        }
        out.push(b);
    }
    sorted_boxes(out)
}

/// Zusammenhängende Flächen (8er-Nachbarschaft) → Pixel-Koordinaten
fn components(mask: &[bool], w: usize, h: usize) -> Vec<Vec<(f32, f32)>> {
    let mut seen = vec![false; w * h];
    let mut out = Vec::new();
    let mut stack = Vec::new();
    for start in 0..w * h {
        if !mask[start] || seen[start] {
            continue;
        }
        let mut pts = Vec::new();
        seen[start] = true;
        stack.push(start);
        while let Some(i) = stack.pop() {
            let (x, y) = ((i % w) as i64, (i / w) as i64);
            pts.push((x as f32, y as f32));
            for dy in -1..=1i64 {
                for dx in -1..=1i64 {
                    let (nx, ny) = (x + dx, y + dy);
                    if nx < 0 || ny < 0 || nx >= w as i64 || ny >= h as i64 {
                        continue;
                    }
                    let j = ny as usize * w + nx as usize;
                    if mask[j] && !seen[j] {
                        seen[j] = true;
                        stack.push(j);
                    }
                }
            }
        }
        out.push(pts);
    }
    out
}

fn convex_hull(pts: &[(f32, f32)]) -> Vec<(f32, f32)> {
    let mut p: Vec<(f32, f32)> = pts.to_vec();
    p.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.total_cmp(&b.1)));
    p.dedup();
    if p.len() < 3 {
        return p;
    }
    let cross = |o: (f32, f32), a: (f32, f32), b: (f32, f32)| (a.0 - o.0) * (b.1 - o.1) - (a.1 - o.1) * (b.0 - o.0);
    let mut lower: Vec<(f32, f32)> = Vec::new();
    for &q in &p {
        while lower.len() >= 2 && cross(lower[lower.len() - 2], lower[lower.len() - 1], q) <= 0.0 {
            lower.pop();
        }
        lower.push(q);
    }
    let mut upper: Vec<(f32, f32)> = Vec::new();
    for &q in p.iter().rev() {
        while upper.len() >= 2 && cross(upper[upper.len() - 2], upper[upper.len() - 1], q) <= 0.0 {
            upper.pop();
        }
        upper.push(q);
    }
    lower.pop();
    upper.pop();
    lower.extend(upper);
    lower
}

#[derive(Clone, Copy, Debug)]
struct RotRect {
    cx: f32,
    cy: f32,
    w: f32,
    h: f32,
    /// Richtung der Seite w (Einheitsvektor)
    ux: f32,
    uy: f32,
}

impl RotRect {
    fn sside(&self) -> f32 {
        self.w.min(self.h)
    }
    fn corners(&self) -> [[f32; 2]; 4] {
        let (vx, vy) = (-self.uy, self.ux);
        let (hw, hh) = (self.w / 2.0, self.h / 2.0);
        let c = |sw: f32, sh: f32| [self.cx + sw * hw * self.ux + sh * hh * vx, self.cy + sw * hw * self.uy + sh * hh * vy];
        [c(-1.0, -1.0), c(1.0, -1.0), c(1.0, 1.0), c(-1.0, 1.0)]
    }
}

/// Kleinstes gedrehtes Rechteck um die Hülle (cv2.minAreaRect, drehende Messschieber).
fn min_area_rect(hull: &[(f32, f32)]) -> Option<RotRect> {
    if hull.is_empty() {
        return None;
    }
    if hull.len() == 1 {
        return Some(RotRect { cx: hull[0].0, cy: hull[0].1, w: 0.0, h: 0.0, ux: 1.0, uy: 0.0 });
    }
    let mut best: Option<(f32, RotRect)> = None;
    let n = hull.len();
    for i in 0..n {
        let (a, b) = (hull[i], hull[(i + 1) % n]);
        let (dx, dy) = (b.0 - a.0, b.1 - a.1);
        let len = (dx * dx + dy * dy).sqrt();
        if len < 1e-6 {
            continue;
        }
        let (ux, uy) = (dx / len, dy / len);
        let (vx, vy) = (-uy, ux);
        let (mut min_u, mut max_u, mut min_v, mut max_v) = (f32::MAX, f32::MIN, f32::MAX, f32::MIN);
        for &(x, y) in hull {
            let u = x * ux + y * uy;
            let v = x * vx + y * vy;
            min_u = min_u.min(u);
            max_u = max_u.max(u);
            min_v = min_v.min(v);
            max_v = max_v.max(v);
        }
        let (w, h) = (max_u - min_u, max_v - min_v);
        let area = w * h;
        if best.as_ref().is_none_or(|(a, _)| area < *a) {
            let (cu, cv) = ((min_u + max_u) / 2.0, (min_v + max_v) / 2.0);
            let cx = cu * ux + cv * vx;
            let cy = cu * uy + cv * vy;
            best = Some((area, RotRect { cx, cy, w, h, ux, uy }));
        }
    }
    best.map(|(_, r)| r)
}

/// get_mini_boxes: Ecken nach x sortiert, dann oben-links, oben-rechts, unten-rechts, unten-links.
fn mini_box(r: &RotRect) -> [[f32; 2]; 4] {
    let mut p = r.corners().to_vec();
    p.sort_by(|a, b| a[0].total_cmp(&b[0]));
    let (i1, i4) = if p[1][1] > p[0][1] { (0, 1) } else { (1, 0) };
    let (i2, i3) = if p[3][1] > p[2][1] { (2, 3) } else { (3, 2) };
    [p[i1], p[i2], p[i3], p[i4]]
}

fn box_score_fast(pred: &[f32], w: usize, h: usize, pts: &[[f32; 2]; 4]) -> f32 {
    let xs = pts.iter().map(|p| p[0]);
    let ys = pts.iter().map(|p| p[1]);
    let xmin = (xs.clone().fold(f32::MAX, f32::min).floor() as i64).clamp(0, w as i64 - 1);
    let xmax = (xs.fold(f32::MIN, f32::max).ceil() as i64).clamp(0, w as i64 - 1);
    let ymin = (ys.clone().fold(f32::MAX, f32::min).floor() as i64).clamp(0, h as i64 - 1);
    let ymax = (ys.fold(f32::MIN, f32::max).ceil() as i64).clamp(0, h as i64 - 1);
    // Polygon (wie astype(int32): abgeschnitten) relativ zu xmin/ymin
    let poly: Vec<(f32, f32)> =
        pts.iter().map(|p| ((p[0] - xmin as f32).trunc(), (p[1] - ymin as f32).trunc())).collect();
    let (mut sum, mut n) = (0f64, 0usize);
    for y in ymin..=ymax {
        for x in xmin..=xmax {
            let (px, py) = ((x - xmin) as f32, (y - ymin) as f32);
            if in_convex(&poly, px, py) {
                sum += pred[y as usize * w + x as usize] as f64;
                n += 1;
            }
        }
    }
    if n == 0 {
        0.0
    } else {
        (sum / n as f64) as f32
    }
}

fn in_convex(poly: &[(f32, f32)], x: f32, y: f32) -> bool {
    let n = poly.len();
    let (mut pos, mut neg) = (false, false);
    for i in 0..n {
        let (a, b) = (poly[i], poly[(i + 1) % n]);
        let c = (b.0 - a.0) * (y - a.1) - (b.1 - a.1) * (x - a.0);
        if c > 1e-3 {
            pos = true;
        } else if c < -1e-3 {
            neg = true;
        }
        if pos && neg {
            return false;
        }
    }
    true
}

fn order_clockwise(pts: [[f32; 2]; 4]) -> [[f32; 2]; 4] {
    let mut xs = pts.to_vec();
    xs.sort_by(|a, b| a[0].total_cmp(&b[0]));
    let mut left = [xs[0], xs[1]];
    let mut right = [xs[2], xs[3]];
    left.sort_by(|a, b| a[1].total_cmp(&b[1]));
    right.sort_by(|a, b| a[1].total_cmp(&b[1]));
    [left[0], right[0], right[1], left[1]]
}

/// Leserichtung: oben → unten, in einer Zeile (y-Abstand < 10) links → rechts.
fn sorted_boxes(mut boxes: Vec<[[f32; 2]; 4]>) -> Vec<[[f32; 2]; 4]> {
    boxes.sort_by(|a, b| a[0][1].total_cmp(&b[0][1])); // stabil
    let mut line = 0usize;
    let mut keyed: Vec<(usize, f32, [[f32; 2]; 4])> = Vec::with_capacity(boxes.len());
    for (i, b) in boxes.iter().enumerate() {
        if i > 0 && b[0][1] - boxes[i - 1][0][1] >= SORT_Y_THRESHOLD {
            line += 1;
        }
        keyed.push((line, b[0][0], *b));
    }
    keyed.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.total_cmp(&b.1)));
    keyed.into_iter().map(|k| k.2).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_splitlines() {
        assert_eq!(splitlines("a\nb\r\nc\x0bd"), vec!["a", "b", "c", "d"]);
        assert_eq!(splitlines("a\n\nb\n"), vec!["a", "", "b"]);
    }

    #[test]
    fn rect_of_axis_aligned_block() {
        let pts: Vec<(f32, f32)> = (0..10).flat_map(|x| (0..4).map(move |y| (x as f32, y as f32))).collect();
        let r = min_area_rect(&convex_hull(&pts)).unwrap();
        assert!((r.w.max(r.h) - 9.0).abs() < 1e-3 && (r.sside() - 3.0).abs() < 1e-3);
        let b = mini_box(&r);
        assert_eq!(b[0], [0.0, 0.0]);
        assert_eq!(b[2], [9.0, 3.0]);
    }

    #[test]
    fn ctc_skips_blank_and_repeats() {
        let chars: Vec<String> = ["blank", "a", "b", " "].iter().map(|s| s.to_string()).collect();
        // Schritte: a a blank b b
        let mut seq = vec![0f32; 5 * 4];
        for (t, k) in [1, 1, 0, 2, 2].iter().enumerate() {
            seq[t * 4 + k] = 0.9;
        }
        let (text, score) = ctc_decode(&seq, 5, 4, &chars);
        assert_eq!(text, "ab");
        assert!((score - 0.9).abs() < 1e-6);
    }

    #[test]
    fn reading_order() {
        let b = |x: f32, y: f32| [[x, y], [x + 5.0, y], [x + 5.0, y + 5.0], [x, y + 5.0]];
        let out = sorted_boxes(vec![b(50.0, 2.0), b(0.0, 30.0), b(10.0, 0.0)]);
        assert_eq!(out[0][0], [10.0, 0.0]);
        assert_eq!(out[1][0], [50.0, 2.0]);
        assert_eq!(out[2][0], [0.0, 30.0]);
    }
}
