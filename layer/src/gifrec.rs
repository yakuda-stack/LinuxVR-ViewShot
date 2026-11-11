//! 🎞 GIF-Aufnahme: Auslöser im Rahmen gedrückt halten → kurzes GIF
//! (oder 🎬 MP4-Video, wenn der Knopf auf VID steht – siehe vidrec.rs).
//!
//! Der Layer kopiert nur die Rohpixel (wie beim Foto) und schickt sie hierher.
//! Ein eigener Thread macht den Rest – Farben umwandeln, verkleinern, ins GIF
//! schreiben –, damit das Spiel nicht ruckelt. Die Datei entsteht wie beim Foto
//! erst versteckt (".ViewShot_….gif.part") und wird am Ende umbenannt.

use std::sync::mpsc::{sync_channel, Receiver, SyncSender, TrySendError};
use std::time::{Duration, Instant};

/// Längste Seite im GIF (Pixel) – hält Datei und Arbeitsspeicher klein
pub const MAX_SIDE: u32 = 512;

/// So viele Bilder dürfen auf den Schreib-Thread warten – kommt er nicht hinterher,
/// fällt ein Bild aus (die Zeitstempel halten die Länge trotzdem richtig)
const QUEUE: usize = 6;

/// Ecken des Rahmens im Bild (oben links, oben rechts, unten rechts, unten links), Pixel
/// relativ zum kopierten Ausschnitt. Some = 📌 Pin / 🎯 Stabilisator: Bild wird entzerrt.
pub type Quad = [[f32; 2]; 4];

type Frame = (Vec<u8>, u32, u32, Instant, Option<Quad>);

pub struct Recorder {
    tx: SyncSender<Frame>,
    pub frames: u32,
    dropped: u32,
    video: bool,
}

impl Recorder {
    /// `w`/`h` = Größe des Ausschnitts, `interval` = Abstand zwischen zwei Bildern
    /// `video` = 🎬 MP4 statt GIF
    pub fn start(name: String, format: i64, w: u32, h: u32, interval: Duration, video: bool) -> Recorder {
        let (tx, rx) = sync_channel(QUEUE);
        std::thread::spawn(move || {
            let dir = crate::save::gif_vid_dir();
            let r = if video { run_video(rx, &dir, &name, format, w, h, interval) } else { run(rx, &dir, &name, format, w, h, interval) };
            if let Err(e) = r {
                crate::log!("{} speichern fehlgeschlagen: {e}", if video { "Video" } else { "GIF" });
            }
        });
        Recorder { tx, frames: 0, dropped: 0, video }
    }

    /// `w`/`h` = Größe DIESES Bilds (📌 Pin-GIF: ändert sich, wenn man sich bewegt)
    pub fn push(&mut self, raw: Vec<u8>, w: u32, h: u32, at: Instant, quad: Option<Quad>) {
        match self.tx.try_send((raw, w, h, at, quad)) {
            Ok(()) => self.frames += 1,
            Err(TrySendError::Full(_)) => self.dropped += 1,
            Err(TrySendError::Disconnected(_)) => {}
        }
    }

    /// Aufnahme beenden – der Thread schreibt das GIF fertig.
    pub fn finish(self) {
        let kind = if self.video { "Video" } else { "GIF" };
        crate::log!("{kind}: Aufnahme beendet ({} Bilder, {} ausgelassen)", self.frames, self.dropped);
        drop(self.tx);
    }
}

/// Zielgröße: längste Seite höchstens MAX_SIDE, Seitenverhältnis bleibt
pub fn out_size(w: u32, h: u32) -> (u32, u32) {
    let scale = (MAX_SIDE as f32 / w.max(h).max(1) as f32).min(1.0);
    (((w as f32 * scale).round() as u32).max(1), ((h as f32 * scale).round() as u32).max(1))
}

/// RGB8 verkleinern (Mittelwert aller Pixel, die in ein Ziel-Pixel fallen)
pub fn downscale(rgb: &[u8], w: u32, h: u32, ow: u32, oh: u32) -> Vec<u8> {
    if (ow, oh) == (w, h) {
        return rgb.to_vec();
    }
    let (w, h, ow, oh) = (w as usize, h as usize, ow as usize, oh as usize);
    let mut out = Vec::with_capacity(ow * oh * 3);
    for oy in 0..oh {
        let y0 = oy * h / oh;
        let y1 = ((oy + 1) * h / oh).max(y0 + 1).min(h);
        for ox in 0..ow {
            let x0 = ox * w / ow;
            let x1 = ((ox + 1) * w / ow).max(x0 + 1).min(w);
            let mut sum = [0u32; 3];
            for y in y0..y1 {
                for x in x0..x1 {
                    let i = (y * w + x) * 3;
                    sum[0] += rgb[i] as u32;
                    sum[1] += rgb[i + 1] as u32;
                    sum[2] += rgb[i + 2] as u32;
                }
            }
            let n = ((y1 - y0) * (x1 - x0)) as u32;
            out.extend(sum.iter().map(|s| (s / n) as u8));
        }
    }
    out
}

/// Ein Bild auf die Ausgabegröße bringen: mit `quad` perspektivisch entzerrt, sonst nur verkleinert
pub fn to_out(rgb: &[u8], w: u32, h: u32, quad: Option<Quad>, ow: u32, oh: u32) -> Vec<u8> {
    match quad {
        Some(q) => warp(rgb, w, h, &q, ow, oh),
        None => downscale(rgb, w, h, ow, oh),
    }
}

/// Abbildung Einheitsquadrat → Viereck (Heckbert): (u, v) ∈ [0,1]² → Pixel im Viereck.
/// Ecken: q[0] = (0,0) oben links, q[1] = (1,0), q[2] = (1,1), q[3] = (0,1).
pub fn square_to_quad(q: &Quad) -> [f32; 8] {
    let ([x0, y0], [x1, y1], [x2, y2], [x3, y3]) = (q[0], q[1], q[2], q[3]);
    let (dx3, dy3) = (x0 - x1 + x2 - x3, y0 - y1 + y2 - y3);
    if dx3.abs() < 1e-6 && dy3.abs() < 1e-6 {
        return [x1 - x0, x3 - x0, x0, y1 - y0, y3 - y0, y0, 0.0, 0.0];
    }
    let (dx1, dx2, dy1, dy2) = (x1 - x2, x3 - x2, y1 - y2, y3 - y2);
    let det = dx1 * dy2 - dx2 * dy1;
    if det.abs() < 1e-9 {
        return [x1 - x0, x3 - x0, x0, y1 - y0, y3 - y0, y0, 0.0, 0.0];
    }
    let g = (dx3 * dy2 - dx2 * dy3) / det;
    let h = (dx1 * dy3 - dx3 * dy1) / det;
    [x1 - x0 + g * x1, x3 - x0 + h * x3, x0, y1 - y0 + g * y1, y3 - y0 + h * y3, y0, g, h]
}

fn map(m: &[f32; 8], u: f32, v: f32) -> (f32, f32) {
    let w = (m[6] * u + m[7] * v + 1.0).max(1e-6);
    ((m[0] * u + m[1] * v + m[2]) / w, (m[3] * u + m[4] * v + m[5]) / w)
}

/// RGB8 an (x, y) bilinear lesen – außerhalb des Bilds schwarz
fn sample(rgb: &[u8], w: usize, h: usize, x: f32, y: f32) -> [f32; 3] {
    let (x, y) = (x - 0.5, y - 0.5);
    if x < -0.5 || y < -0.5 || x > w as f32 - 0.5 || y > h as f32 - 0.5 {
        return [0.0; 3];
    }
    let (x0, y0) = (x.floor().max(0.0) as usize, y.floor().max(0.0) as usize);
    let (x1, y1) = ((x0 + 1).min(w - 1), (y0 + 1).min(h - 1));
    let (fx, fy) = ((x - x0 as f32).clamp(0.0, 1.0), (y - y0 as f32).clamp(0.0, 1.0));
    let px = |xx: usize, yy: usize, c: usize| rgb[(yy * w + xx) * 3 + c] as f32;
    let mut out = [0.0; 3];
    for (c, o) in out.iter_mut().enumerate() {
        let top = px(x0, y0, c) * (1.0 - fx) + px(x1, y0, c) * fx;
        let bot = px(x0, y1, c) * (1.0 - fx) + px(x1, y1, c) * fx;
        *o = top * (1.0 - fy) + bot * fy;
    }
    out
}

/// 🎯 Entzerren: das (schräg/gedreht gesehene) Viereck `q` wird wieder zum geraden Bild ow × oh.
/// Wird stark verkleinert, liest es 2 × 2 Punkte je Pixel (sonst flimmert es).
pub fn warp(rgb: &[u8], w: u32, h: u32, q: &Quad, ow: u32, oh: u32) -> Vec<u8> {
    let m = square_to_quad(q);
    let (w, h) = (w as usize, h as usize);
    let len = |a: [f32; 2], b: [f32; 2]| ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt();
    let scale = (len(q[0], q[1]) / ow as f32).max(len(q[0], q[3]) / oh as f32);
    let ss = if scale > 1.5 { 2 } else { 1 };
    let n = (ss * ss) as f32;
    let row = (ow * 3) as usize;
    let mut out = vec![0u8; row * oh as usize];
    // Zeilen auf bis zu 4 Kerne verteilen (Video: 1280 px × 24 Bilder/s)
    let threads = std::thread::available_parallelism().map_or(1, |n| n.get()).clamp(1, 4);
    let chunk_rows = (oh as usize).div_ceil(threads).max(1);
    std::thread::scope(|scope| {
        for (k, chunk) in out.chunks_mut(chunk_rows * row).enumerate() {
            let m = &m;
            scope.spawn(move || {
                for (r, line) in chunk.chunks_mut(row).enumerate() {
                    let oy = (k * chunk_rows + r) as f32;
                    for ox in 0..ow as usize {
                        let mut sum = [0.0f32; 3];
                        for sy in 0..ss {
                            for sx in 0..ss {
                                let u = (ox as f32 + (sx as f32 + 0.5) / ss as f32) / ow as f32;
                                let v = (oy + (sy as f32 + 0.5) / ss as f32) / oh as f32;
                                let (x, y) = map(m, u, v);
                                let p = sample(rgb, w, h, x, y);
                                sum = [sum[0] + p[0], sum[1] + p[1], sum[2] + p[2]];
                            }
                        }
                        for c in 0..3 {
                            line[ox * 3 + c] = (sum[c] / n).round().clamp(0.0, 255.0) as u8;
                        }
                    }
                }
            });
        }
    });
    out
}

/// Zeit zwischen zwei Bildern in 1/100 s (GIF-Einheit), mindestens 2
fn centis(d: Duration) -> u16 {
    ((d.as_millis() as f32 / 10.0).round() as u16).max(2)
}

/// 🖼 Vorschaubild eines Videos – die Galerien zeigen es statt des Videos
pub fn poster_path(dir: &std::path::Path, name: &str) -> std::path::PathBuf {
    dir.join(format!(".{name}.png"))
}

/// 🎬 Wie `run`, nur als MP4 (H.264)
fn run_video(rx: Receiver<Frame>, dir: &std::path::Path, name: &str, format: i64, w: u32, h: u32, interval: Duration) -> Result<(), Box<dyn std::error::Error>> {
    let (ow, oh) = crate::vidrec::out_size(w, h);
    std::fs::create_dir_all(dir)?;
    let path = dir.join(name);
    let tmp = dir.join(format!(".{name}.part"));
    let result = (|| -> Result<u32, Box<dyn std::error::Error>> {
        let file = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
        let fps = 1.0 / interval.as_secs_f32().max(0.001);
        let mut v = crate::vidrec::VideoWriter::new(file, ow, oh, fps)?;
        let mut t0 = None;
        for (raw, fw, fh, at, quad) in rx {
            let first = t0.is_none();
            let start = *t0.get_or_insert(at);
            let rgb = to_out(&crate::save::to_rgb(&raw, format), fw, fh, quad, ow, oh);
            if first {
                // 🖼 Vorschaubild für die Galerien (versteckt: „.ViewShot_….mp4.png“)
                if let Err(e) = crate::save::write_png(&poster_path(dir, name), &rgb, ow, oh, &[]) {
                    crate::log!("Video: Vorschaubild fehlgeschlagen: {e}");
                }
            }
            v.push(&rgb, at.duration_since(start).as_millis() as u64)?;
        }
        v.finish(interval)
    })();
    match result {
        Ok(n) if n >= 2 => {
            std::fs::rename(&tmp, &path)?;
            crate::log!("Video gespeichert: {} ({n} Bilder, {ow}x{oh})", path.display());
            Ok(())
        }
        Ok(n) => {
            let _ = std::fs::remove_file(&tmp);
            let _ = std::fs::remove_file(poster_path(dir, name));
            crate::log!("Video zu kurz ({n} Bild) – nicht gespeichert");
            Ok(())
        }
        Err(e) => {
            let _ = std::fs::remove_file(&tmp);
            Err(e)
        }
    }
}

fn run(
    rx: Receiver<Frame>,
    dir: &std::path::Path,
    name: &str,
    format: i64,
    w: u32,
    h: u32,
    interval: Duration,
) -> Result<(), Box<dyn std::error::Error>> {
    let (ow, oh) = out_size(w, h);
    std::fs::create_dir_all(dir)?;
    let path = dir.join(name);
    let tmp = dir.join(format!(".{name}.part"));

    let result = (|| -> Result<u32, Box<dyn std::error::Error>> {
        let file = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
        let mut enc = gif::Encoder::new(file, ow as u16, oh as u16, &[])?;
        enc.set_repeat(gif::Repeat::Infinite)?;
        let mut count = 0u32;
        let mut write = |enc: &mut gif::Encoder<std::io::BufWriter<std::fs::File>>, rgb: Vec<u8>, delay: u16| -> Result<(), gif::EncodingError> {
            let mut frame = gif::Frame::from_rgb_speed(ow as u16, oh as u16, &rgb, 10);
            frame.delay = delay;
            count += 1;
            enc.write_frame(&frame)
        };
        // Ein Bild zurückhalten: seine Anzeigedauer = Abstand zum nächsten
        let mut pending: Option<(Vec<u8>, Instant)> = None;
        for (raw, fw, fh, at, quad) in rx {
            // jedes Bild auf dieselbe GIF-Größe (Pin: entzerrt, sonst nur verkleinert)
            let rgb = to_out(&crate::save::to_rgb(&raw, format), fw, fh, quad, ow, oh);
            if let Some((prev, t0)) = pending.replace((rgb, at)) {
                write(&mut enc, prev, centis(at.duration_since(t0)))?;
            }
        }
        if let Some((last, _)) = pending {
            write(&mut enc, last, centis(interval))?;
        }
        let mut file = enc.into_inner()?; // schreibt das GIF-Ende
        std::io::Write::flush(&mut file)?;
        Ok(count)
    })();

    match result {
        Ok(n) if n >= 2 => {
            std::fs::rename(&tmp, &path)?;
            crate::log!("GIF gespeichert: {} ({n} Bilder, {ow}x{oh})", path.display());
            Ok(())
        }
        Ok(n) => {
            let _ = std::fs::remove_file(&tmp);
            crate::log!("GIF zu kurz ({n} Bild) – nicht gespeichert");
            Ok(())
        }
        Err(e) => {
            let _ = std::fs::remove_file(&tmp);
            Err(e)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn out_size_keeps_ratio() {
        assert_eq!(out_size(1024, 576), (512, 288));
        assert_eq!(out_size(300, 200), (300, 200));
        assert_eq!(out_size(200, 1000), (102, 512));
    }

    #[test]
    fn downscale_averages() {
        // 2×2 → 1×1: Mittelwert
        let rgb = [0, 0, 0, 100, 100, 100, 200, 200, 200, 100, 100, 100];
        assert_eq!(downscale(&rgb, 2, 2, 1, 1), vec![100, 100, 100]);
    }

    #[test]
    fn writes_animated_gif() {
        let dir = std::env::temp_dir().join(format!("viewshot_gif_test_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let (tx, rx) = sync_channel(8);
        let t0 = Instant::now();
        // 📌 Pin-GIF: die Bilder sind unterschiedlich groß → alle landen in 8×4
        for (i, (w, h)) in [(8u32, 4u32), (12, 6), (6, 3)].into_iter().enumerate() {
            let raw = [i as u8 * 80, 10, 200, 255].repeat((w * h) as usize); // RGBA
            tx.send((raw, w, h, t0 + Duration::from_millis(100 * i as u64), None)).unwrap();
        }
        drop(tx);
        run(rx, &dir, "t.gif", crate::save::R8G8B8A8_SRGB, 8, 4, Duration::from_millis(100)).unwrap();
        let mut dec = gif::DecodeOptions::new().read_info(std::fs::File::open(dir.join("t.gif")).unwrap()).unwrap();
        let mut n = 0;
        while let Some(f) = dec.read_next_frame().unwrap() {
            assert_eq!((f.width, f.height, f.delay), (8, 4, 10));
            n += 1;
        }
        assert_eq!(n, 3);
        // keine .part-Reste
        assert_eq!(std::fs::read_dir(&dir).unwrap().count(), 1);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn writes_mp4_video() {
        let dir = std::env::temp_dir().join(format!("viewshot_vid_test_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let (tx, rx) = sync_channel(16);
        let t0 = Instant::now();
        for i in 0..8u32 {
            let (w, h) = if i % 2 == 0 { (64u32, 48u32) } else { (80, 60) };
            let raw = [(i * 30) as u8, 10, 200, 255].repeat((w * h) as usize);
            tx.send((raw, w, h, t0 + Duration::from_millis(100 * i as u64), None)).unwrap();
        }
        drop(tx);
        run_video(rx, &dir, "t.mp4", crate::save::R8G8B8A8_SRGB, 64, 48, Duration::from_millis(100)).unwrap();
        let data = std::fs::read(dir.join("t.mp4")).unwrap();
        assert_eq!(&data[4..8], b"ftyp");
        assert!(poster_path(&dir, "t.mp4").exists());
        assert_eq!(std::fs::read_dir(&dir).unwrap().count(), 2);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn warp_is_fast_enough_for_video() {
        let (w, h) = (1400u32, 900u32);
        let rgb = vec![128u8; (w * h * 3) as usize];
        let q = [[10.0, 20.0], [1390.0, 5.0], [1380.0, 880.0], [5.0, 890.0]];
        let t = Instant::now();
        let out = warp(&rgb, w, h, &q, 1280, 822);
        eprintln!("warp 1280×822: {:?}", t.elapsed());
        assert_eq!(out.len(), 1280 * 822 * 3);
    }

    #[test]
    fn warp_straightens_a_tilted_quad() {
        // 40×40-Bild: links schwarz, rechts weiß (Grenze bei x = 20)
        let (w, h) = (40u32, 40u32);
        let rgb: Vec<u8> = (0..w * h).flat_map(|p| if p % w < 20 { [0, 0, 0] } else { [255, 255, 255] }).collect();
        // gerades Viereck = ganzes Bild → Ergebnis wie verkleinert
        let full = [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]];
        let out = warp(&rgb, w, h, &full, 20, 20);
        assert_eq!(out.len(), 20 * 20 * 3);
        assert!(out[0] < 20 && out[(19 * 3) as usize] > 235);
        // nur die rechte Hälfte als Viereck → alles weiß
        let right = [[22.0, 0.0], [40.0, 0.0], [40.0, 40.0], [22.0, 40.0]];
        assert!(warp(&rgb, w, h, &right, 10, 10).iter().all(|&c| c > 235));
        // Abbildung trifft die Ecken auch bei einem schiefen Viereck
        let q = [[3.0, 2.0], [30.0, 6.0], [35.0, 33.0], [1.0, 28.0]];
        let m = square_to_quad(&q);
        for ((u, v), want) in [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)].into_iter().zip(q) {
            let (x, y) = map(&m, u, v);
            assert!((x - want[0]).abs() < 1e-3 && (y - want[1]).abs() < 1e-3);
        }
    }
}
