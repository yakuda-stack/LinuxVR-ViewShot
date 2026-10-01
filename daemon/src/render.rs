//! Zeichnen: Flächen (tiny-skia) + Text mit Systemschriften (cosmic-text –
//! findet Japanisch/Chinesisch/Emoji über die installierten Fonts, wie Qt).

use cosmic_text::{Attrs, Buffer, Color, Family, FontSystem, Metrics, Shaping, SwashCache, Weight};
use tiny_skia::{FillRule, Paint, PathBuilder, Pixmap, Rect, Stroke, Transform};

pub struct Fonts {
    pub system: FontSystem,
    cache: SwashCache,
}

impl Fonts {
    pub fn new() -> Fonts {
        Fonts { system: FontSystem::new(), cache: SwashCache::new() }
    }
}

pub fn rgba(hex: u32, alpha: u8) -> tiny_skia::Color {
    tiny_skia::Color::from_rgba8((hex >> 16) as u8, (hex >> 8) as u8, hex as u8, alpha)
}

#[derive(Clone, Copy)]
pub struct Style {
    pub size: f32,
    pub bold: bool,
    pub color: u32,
    pub alpha: u8,
}

impl Style {
    pub fn new(size: f32, bold: bool, color: u32) -> Style {
        Style { size, bold, color, alpha: 255 }
    }
}

fn buffer(f: &mut Fonts, text: &str, width: Option<f32>, st: Style) -> Buffer {
    let mut buf = Buffer::new(&mut f.system, Metrics::new(st.size, (st.size * 1.3).ceil()));
    buf.set_size(&mut f.system, width, None);
    let attrs = Attrs::new().family(Family::SansSerif).weight(if st.bold { Weight::BOLD } else { Weight::NORMAL });
    buf.set_text(&mut f.system, text, &attrs, Shaping::Advanced);
    buf.shape_until_scroll(&mut f.system, false);
    buf
}

/// (Breite, Höhe) des Texts, umbrochen auf `width` (None = eine Zeile je \n)
pub fn measure(f: &mut Fonts, text: &str, width: Option<f32>, st: Style) -> (f32, f32) {
    let buf = buffer(f, text, width, st);
    let mut w = 0f32;
    let mut h = 0f32;
    for run in buf.layout_runs() {
        w = w.max(run.line_w);
        h = h.max(run.line_top + run.line_height);
    }
    (w, h)
}

/// Text in Zeilen umbrechen, wie er gezeichnet würde (zum Blättern ▼ / ▲)
pub fn wrap_lines(f: &mut Fonts, text: &str, width: f32, st: Style) -> Vec<String> {
    let buf = buffer(f, text, Some(width), st);
    let mut out = Vec::new();
    for run in buf.layout_runs() {
        match (run.glyphs.first(), run.glyphs.last()) {
            (Some(a), Some(b)) => out.push(run.text[a.start.min(b.start)..a.end.max(b.end)].trim_end().to_string()),
            _ => out.push(String::new()),
        }
    }
    out
}

pub fn line_height(st: Style) -> f32 {
    (st.size * 1.3).ceil()
}

pub struct Canvas {
    pub pix: Pixmap,
}

impl Canvas {
    pub fn new(w: u32, h: u32) -> Option<Canvas> {
        Some(Canvas { pix: Pixmap::new(w.max(1), h.max(1))? })
    }

    #[allow(clippy::too_many_arguments)] // x, y, w, h, Radius, Füllung, Rand – so am lesbarsten
    pub fn rounded(&mut self, x: f32, y: f32, w: f32, h: f32, r: f32, fill: Option<tiny_skia::Color>, stroke: Option<(tiny_skia::Color, f32)>) {
        let Some(path) = rounded_path(x, y, w, h, r) else { return };
        if let Some(c) = fill {
            let mut p = Paint::default();
            p.set_color(c);
            p.anti_alias = true;
            self.pix.fill_path(&path, &p, FillRule::Winding, Transform::identity(), None);
        }
        if let Some((c, width)) = stroke {
            let mut p = Paint::default();
            p.set_color(c);
            p.anti_alias = true;
            let s = Stroke { width, ..Stroke::default() };
            self.pix.stroke_path(&path, &p, &s, Transform::identity(), None);
        }
    }

    pub fn circle(&mut self, cx: f32, cy: f32, r: f32, c: tiny_skia::Color) {
        let Some(path) = PathBuilder::from_circle(cx, cy, r) else { return };
        let mut p = Paint::default();
        p.set_color(c);
        p.anti_alias = true;
        self.pix.fill_path(&path, &p, FillRule::Winding, Transform::identity(), None);
    }

    pub fn rect_outline(&mut self, x: f32, y: f32, w: f32, h: f32, c: tiny_skia::Color, width: f32) {
        let Some(r) = Rect::from_xywh(x, y, w.max(1.0), h.max(1.0)) else { return };
        let path = PathBuilder::from_rect(r);
        let mut p = Paint::default();
        p.set_color(c);
        p.anti_alias = true;
        self.pix.stroke_path(&path, &p, &Stroke { width, ..Stroke::default() }, Transform::identity(), None);
    }

    /// Text zeichnen (links oben = x/y), umbrochen auf `width`. Gibt die Höhe zurück.
    pub fn text(&mut self, f: &mut Fonts, text: &str, x: f32, y: f32, width: Option<f32>, st: Style) -> f32 {
        let buf = buffer(f, text, width, st);
        let color = Color::rgba((st.color >> 16) as u8, (st.color >> 8) as u8, st.color as u8, st.alpha);
        let (pw, ph) = (self.pix.width() as i32, self.pix.height() as i32);
        let data = self.pix.data_mut();
        let Fonts { system, cache } = f;
        buf.draw(system, cache, color, |gx, gy, gw, gh, c| {
            let a = c.a() as u32;
            if a == 0 {
                return;
            }
            for yy in gy..gy + gh as i32 {
                for xx in gx..gx + gw as i32 {
                    let (px, py) = (xx + x.round() as i32, yy + y.round() as i32);
                    if px < 0 || py < 0 || px >= pw || py >= ph {
                        continue;
                    }
                    let i = ((py * pw + px) * 4) as usize;
                    // vormultipliert mischen (tiny-skia speichert premultiplied RGBA)
                    let inv = 255 - a;
                    let blend = |src: u8, dst: u8| ((src as u32 * a + dst as u32 * inv) / 255) as u8;
                    data[i] = blend(c.r(), data[i]);
                    data[i + 1] = blend(c.g(), data[i + 1]);
                    data[i + 2] = blend(c.b(), data[i + 2]);
                    data[i + 3] = (a + data[i + 3] as u32 * inv / 255) as u8;
                }
            }
        });
        let mut h = 0f32;
        for run in buf.layout_runs() {
            h = h.max(run.line_top + run.line_height);
        }
        h
    }

    /// RGBA-Bild (nicht vormultipliert) an x/y zeichnen
    pub fn image(&mut self, img: &image::RgbaImage, x: i32, y: i32) {
        let (pw, ph) = (self.pix.width() as i32, self.pix.height() as i32);
        let data = self.pix.data_mut();
        for (ix, iy, p) in img.enumerate_pixels() {
            let (px, py) = (x + ix as i32, y + iy as i32);
            if px < 0 || py < 0 || px >= pw || py >= ph {
                continue;
            }
            let i = ((py * pw + px) * 4) as usize;
            let a = p[3] as u32;
            let inv = 255 - a;
            for c in 0..3 {
                data[i + c] = ((p[c] as u32 * a + data[i + c] as u32 * inv) / 255) as u8;
            }
            data[i + 3] = (a + data[i + 3] as u32 * inv / 255) as u8;
        }
    }

    /// Anderes Bild darüberlegen (y darf negativ sein – für das Aufklappen)
    pub fn draw(&mut self, other: &Canvas, x: i32, y: i32) {
        self.pix.draw_pixmap(x, y, other.pix.as_ref(), &tiny_skia::PixmapPaint::default(), Transform::identity(), None);
    }

    /// Ganzes Bild durchsichtiger machen (Deckkraft 0..1)
    pub fn fade(&mut self, alpha: f32) {
        if alpha >= 1.0 {
            return;
        }
        for v in self.pix.data_mut() {
            *v = (*v as f32 * alpha).round() as u8;
        }
    }

    /// Als PNG speichern (erst Hilfsdatei, dann umbenennen). `text` = PNG-Textfelder.
    pub fn save(&self, target: &std::path::Path, text: &[(&str, &str)]) -> std::io::Result<()> {
        let (w, h) = (self.pix.width(), self.pix.height());
        // premultiplied → straight RGBA
        let mut raw = Vec::with_capacity((w * h * 4) as usize);
        for px in self.pix.pixels() {
            let c = px.demultiply();
            raw.extend([c.red(), c.green(), c.blue(), c.alpha()]);
        }
        if let Some(dir) = target.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let name = target.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        let tmp = target.with_file_name(format!(".{name}.part"));
        {
            use std::io::Write;
            let mut file = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
            {
                let mut enc = png::Encoder::new(&mut file, w, h);
                enc.set_color(png::ColorType::Rgba);
                enc.set_depth(png::BitDepth::Eight);
                for (k, v) in text {
                    enc.add_text_chunk((*k).to_string(), (*v).to_string()).map_err(std::io::Error::other)?;
                }
                let mut wr = enc.write_header().map_err(std::io::Error::other)?;
                wr.write_image_data(&raw).map_err(std::io::Error::other)?;
                wr.finish().map_err(std::io::Error::other)?;
            }
            file.flush()?; // Fehler nicht verschlucken → nie ein halbes Bild umbenennen
        }
        std::fs::rename(&tmp, target)
    }
}

fn rounded_path(x: f32, y: f32, w: f32, h: f32, r: f32) -> Option<tiny_skia::Path> {
    let r = r.min(w / 2.0).min(h / 2.0).max(0.0);
    let mut pb = PathBuilder::new();
    pb.move_to(x + r, y);
    pb.line_to(x + w - r, y);
    pb.quad_to(x + w, y, x + w, y + r);
    pb.line_to(x + w, y + h - r);
    pb.quad_to(x + w, y + h, x + w - r, y + h);
    pb.line_to(x + r, y + h);
    pb.quad_to(x, y + h, x, y + h - r);
    pb.line_to(x, y + r);
    pb.quad_to(x, y, x + r, y);
    pb.close();
    pb.finish()
}
