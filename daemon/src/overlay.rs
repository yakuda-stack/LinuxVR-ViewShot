//! 🥽 Übersetzung über dem Original (nur 🔁 Lens) – wie UI/core/overlay.py:
//! durchsichtiges Bild, über jeder erkannten Zeile ein graues Kästchen mit der
//! Übersetzung. PNG-Text "ViewShot-For" = "live" → der Layer legt es in den blauen Rahmen.

use crate::ocr::Line;
use crate::render::{measure, rgba, Canvas, Fonts, Style};

const MAX_SIZE: f32 = 1024.0;
pub const LIVE: &str = "live";

/// Übersetzte Zeilen den erkannten zuordnen; None = Anzahl passt nicht
pub fn pair_lines(lines: &[Line], translated: &str) -> Option<Vec<([i64; 4], String)>> {
    let boxed: Vec<&Line> = lines.iter().filter(|l| l.r#box.is_some()).collect();
    let tr: Vec<String> =
        crate::ocr::splitlines(translated).iter().map(|t| t.trim().to_string()).filter(|t| !t.is_empty()).collect();
    if boxed.is_empty() || tr.len() != boxed.len() || boxed.len() != lines.len() {
        return None;
    }
    Some(boxed.iter().zip(tr).map(|(l, t)| (l.r#box.unwrap(), t)).collect())
}

fn union_box(lines: &[Line], size: (u32, u32)) -> [i64; 4] {
    let boxes: Vec<[i64; 4]> = lines.iter().filter_map(|l| l.r#box).collect();
    if boxes.is_empty() {
        return [0, 0, size.0 as i64, size.1 as i64];
    }
    [
        boxes.iter().map(|b| b[0]).min().unwrap(),
        boxes.iter().map(|b| b[1]).min().unwrap(),
        boxes.iter().map(|b| b[2]).max().unwrap(),
        boxes.iter().map(|b| b[3]).max().unwrap(),
    ]
}

pub fn render(f: &mut Fonts, size: (u32, u32), lines: &[Line], translated: &str) -> Option<Canvas> {
    let (w, h) = (size.0 as f32, size.1 as f32);
    let scale = (MAX_SIZE / w.max(h).max(1.0)).min(1.0);
    let (iw, ih) = ((w * scale).round().max(1.0), (h * scale).round().max(1.0));
    let mut c = Canvas::new(iw as u32, ih as u32)?;
    if translated.trim().is_empty() {
        return Some(c);
    }
    let pairs = pair_lines(lines, translated).unwrap_or_else(|| vec![(union_box(lines, size), translated.trim().to_string())]);
    // kleinste Schrift: lieber klein als über den Rand / das halbe Bild zudecken
    let minimum = (ih / 90.0).max(7.0);
    for (b, text) in pairs {
        let (x0, y0, x1, y1) = (b[0] as f32 * scale, b[1] as f32 * scale, b[2] as f32 * scale, b[3] as f32 * scale);
        let line_h = (y1 - y0).max(8.0);
        let pad = (line_h * 0.12).clamp(2.0, 8.0);
        // Kästchen genau über dem Originaltext (nicht breiter) – zu langer Text → kleinere Schrift
        let (ax, ay) = ((x0 - pad).max(0.0), (y0 - pad).max(0.0));
        let width = ((x1 - x0).max(line_h * 2.0) + 2.0 * pad).min(iw - ax);
        let area_h = ((y1 - y0) + 2.0 * pad).min(ih - ay);
        let (text_w, text_h) = ((width - 2.0 * pad).max(1.0), (area_h - pad).max(1.0));
        let (st, need) = fit(f, &text, text_w, text_h, line_h * 0.8, minimum);
        // passt es selbst mit kleinster Schrift nicht: Kästchen wächst nach unten (bleibt im Bild)
        let box_h = area_h.max(need + pad).min(ih - ay);
        c.rounded(ax, ay, width, box_h, pad, Some(rgba(0x1e2028, 225)), None);
        let ty = ay + ((box_h - need) / 2.0).max(pad * 0.5); // senkrecht mittig
        c.text(f, &text, ax + pad, ty, Some(text_w), st);
    }
    Some(c)
}

/// Größte Schrift (ab `start`, kleiner werdend), mit der `text` umbrochen in w×h passt –
/// Breite UND Höhe (lange deutsche Wörter!). Klappt das nicht: `minimum`. → (Stil, Höhe)
fn fit(f: &mut Fonts, text: &str, w: f32, h: f32, start: f32, minimum: f32) -> (Style, f32) {
    let mut size_px = start.max(minimum);
    loop {
        let st = Style::new(size_px.round().max(1.0), true, 0xffffff);
        let (nw, nh) = measure(f, text, Some(w), st);
        if (nw <= w * 1.02 && nh <= h * 1.05) || size_px <= minimum {
            return (st, nh);
        }
        size_px = (size_px * 0.9).max(minimum);
    }
}

/// Overlay für 🔁 Lens schreiben (Größe = Live-Bild). `seq` = Nummer des Live-Bilds –
/// der Layer legt die Übersetzung damit fest in die Welt, genau dorthin, wo das Bild gemacht wurde.
/// `roll` = so weit wurde das Bild geradegedreht (Grad) – der Layer dreht das Quad zurück.
pub fn write_live(f: &mut Fonts, size: (u32, u32), lines: &[Line], translated: &str, seq: &str, roll: &str) {
    if let Some(c) = render(f, size, lines, translated) {
        let text = [("ViewShot-For", LIVE), ("ViewShot-Seq", seq), ("ViewShot-Roll", roll)];
        if let Err(e) = c.save(&crate::paths::overlay_file(), &text) {
            crate::log::line(&format!("Overlay: {e}"));
        }
    }
}

/// Overlay weg (🔁 Lens: kein Text mehr im Bild)
pub fn clear() {
    let _ = std::fs::remove_file(crate::paths::overlay_file());
}

/// Unter so viel Schräglage (Grad) wird nicht gedreht – spart Zeit und macht das Bild nicht unscharf
const MIN_ROLL_DEG: f32 = 2.0;

/// 🔁 Lens / 📌 Pin: live.png EINMAL lesen → (Größe, Nummer, Drehung in Grad) + Bild nach `out`.
/// War der Kopf schräg ("ViewShot-Roll"), wird das Bild so gedreht, dass der Text waagerecht
/// liegt (Fläche wird größer, Ecken schwarz) – die OCR erkennt ihn so auch besser.
pub fn upright_snapshot(path: &std::path::Path, out: &std::path::Path) -> Result<((u32, u32), String, String), String> {
    let bytes = std::fs::read(path).map_err(|e| format!("Live-Bild: {e}"))?;
    let seq = png_text_bytes(&bytes, "ViewShot-Seq");
    let deg: f32 = png_text_bytes(&bytes, "ViewShot-Roll").trim().parse().unwrap_or(0.0);
    let img = image::load_from_memory(&bytes).map_err(|e| format!("Live-Bild: {e}"))?.to_rgb8();
    let (img, roll) = if deg.abs() >= MIN_ROLL_DEG { (rotate_ccw(&img, deg.to_radians()), deg) } else { (img, 0.0) };
    img.save_with_format(out, image::ImageFormat::Png).map_err(|e| format!("Live-Bild: {e}"))?;
    Ok((img.dimensions(), seq, format!("{roll:.2}")))
}

/// Bild sichtbar gegen den Uhrzeigersinn um `angle` (Radiant) drehen, Fläche wächst mit (bilinear)
pub fn rotate_ccw(src: &image::RgbImage, angle: f32) -> image::RgbImage {
    let (w, h) = (src.width() as f32, src.height() as f32);
    let (c, s) = (angle.cos(), angle.sin());
    // (- 0.001: Rundungsfehler bei 90° sollen nicht ein Pixel mehr ergeben)
    let nw = (w * c.abs() + h * s.abs() - 0.001).ceil().max(1.0) as u32;
    let nh = (w * s.abs() + h * c.abs() - 0.001).ceil().max(1.0) as u32;
    let (cx, cy) = (w / 2.0, h / 2.0);
    let (ncx, ncy) = (nw as f32 / 2.0, nh as f32 / 2.0);
    let mut out = image::RgbImage::new(nw, nh);
    for (xo, yo, px) in out.enumerate_pixels_mut() {
        // Ziel → Quelle (Rückwärtsdrehung), gerechnet mit y nach OBEN
        let (dx, dy) = (xo as f32 + 0.5 - ncx, -(yo as f32 + 0.5 - ncy));
        let (xi, yi) = (dx * c + dy * s, -dx * s + dy * c);
        let (sx, sy) = (cx + xi - 0.5, cy - yi - 0.5);
        if sx < -0.5 || sy < -0.5 || sx > w - 0.5 || sy > h - 0.5 {
            continue; // außerhalb → schwarz
        }
        let (x0, y0) = (sx.floor(), sy.floor());
        let (fx, fy) = (sx - x0, sy - y0);
        let get = |x: f32, y: f32| *src.get_pixel(x.clamp(0.0, w - 1.0) as u32, y.clamp(0.0, h - 1.0) as u32);
        let (a, b, cc, d) = (get(x0, y0), get(x0 + 1.0, y0), get(x0, y0 + 1.0), get(x0 + 1.0, y0 + 1.0));
        for i in 0..3 {
            let top = a[i] as f32 * (1.0 - fx) + b[i] as f32 * fx;
            let bot = cc[i] as f32 * (1.0 - fx) + d[i] as f32 * fx;
            px[i] = (top * (1.0 - fy) + bot * fy).round() as u8;
        }
    }
    out
}

fn png_text_bytes(bytes: &[u8], key: &str) -> String {
    let Ok(reader) = png::Decoder::new(std::io::Cursor::new(bytes)).read_info() else { return String::new() };
    png_text_info(reader.info(), key)
}

/// Text-Stück aus dem PNG (z. B. "ViewShot-Seq"), "" = keins
fn png_text_info(info: &png::Info, key: &str) -> String {
    info.uncompressed_latin1_text
        .iter()
        .filter(|t| t.keyword == key)
        .map(|t| t.text.clone())
        .chain(info.utf8_text.iter().filter(|t| t.keyword == key).filter_map(|t| t.get_text().ok()))
        .next()
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rotate_ccw_moves_right_pixel_up() {
        // 3×3, rechte Mitte rot → nach 90° gegen den Uhrzeigersinn oben Mitte
        let mut img = image::RgbImage::new(3, 3);
        img.put_pixel(2, 1, image::Rgb([255, 0, 0]));
        let out = rotate_ccw(&img, std::f32::consts::FRAC_PI_2);
        assert_eq!(out.dimensions(), (3, 3));
        assert_eq!(out.get_pixel(1, 0)[0], 255);
        // schräg → Fläche wächst
        let big = rotate_ccw(&image::RgbImage::new(100, 50), 0.3);
        assert!(big.width() > 100 && big.height() > 50);
    }
}
