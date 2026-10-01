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
    for (b, text) in pairs {
        let (x0, y0, x1, y1) = (b[0] as f32 * scale, b[1] as f32 * scale, b[2] as f32 * scale, b[3] as f32 * scale);
        let line_h = (y1 - y0).max(8.0);
        let pad = (line_h * 0.15).max(3.0);
        let width = (iw - (x0 - pad)).min((x1 - x0).max(line_h * 4.0) * 1.25 + 2.0 * pad);
        let (ax, ay) = (x0 - pad, y0 - pad);
        let text_w = width - 2.0 * pad;
        let area_h = (y1 - y0) + 2.0 * pad;
        let text_h = area_h - pad;
        // größte Schrift, die in die Höhe passt (sonst kleinste, Kästchen wächst)
        let minimum = (ih / 40.0).max(9.0);
        let mut size_px = line_h * 0.8;
        let (st, need) = loop {
            let st = Style::new(size_px.round().max(1.0), true, 0xffffff);
            let (_, nh) = measure(f, &text, Some(text_w.max(1.0)), st);
            if nh <= text_h * 1.05 || size_px <= minimum {
                break (st, nh);
            }
            size_px *= 0.9;
        };
        let box_h = (ih - ay).min(need + pad * 1.5);
        c.rounded(ax, ay, width, box_h, pad, Some(rgba(0x1e2028, 225)), None);
        c.text(f, &text, ax + pad, ay + pad * 0.5, Some(text_w.max(1.0)), st);
    }
    Some(c)
}

/// Overlay für 🔁 Lens schreiben (Größe = Live-Bild)
pub fn write_live(f: &mut Fonts, size: (u32, u32), lines: &[Line], translated: &str) {
    if let Some(c) = render(f, size, lines, translated) {
        if let Err(e) = c.save(&crate::paths::overlay_file(), &[("ViewShot-For", LIVE)]) {
            crate::log::line(&format!("Overlay: {e}"));
        }
    }
}
