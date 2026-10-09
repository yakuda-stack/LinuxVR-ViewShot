//! 🎞 GIF-Aufnahme: Auslöser im Rahmen gedrückt halten → kurzes GIF.
//!
//! Der Layer kopiert nur die Rohpixel (wie beim Foto) und schickt sie hierher.
//! Ein eigener Thread macht den Rest – Farben umwandeln, verkleinern, ins GIF
//! schreiben –, damit das Spiel nicht ruckelt. Die Datei entsteht wie beim Foto
//! erst versteckt (".ViewShot_….gif.part") und wird am Ende umbenannt.

use std::sync::mpsc::{channel, Receiver, Sender};
use std::time::{Duration, Instant};

/// Längste Seite im GIF (Pixel) – hält Datei und Arbeitsspeicher klein
pub const MAX_SIDE: u32 = 512;

pub struct Recorder {
    tx: Sender<(Vec<u8>, u32, u32, Instant)>,
    pub frames: u32,
}

impl Recorder {
    /// `w`/`h` = Größe des Ausschnitts, `interval` = Abstand zwischen zwei Bildern
    pub fn start(name: String, format: i64, w: u32, h: u32, interval: Duration) -> Recorder {
        let (tx, rx) = channel();
        std::thread::spawn(move || {
            if let Err(e) = run(rx, &crate::save::output_dir(), &name, format, w, h, interval) {
                crate::log!("GIF speichern fehlgeschlagen: {e}");
            }
        });
        Recorder { tx, frames: 0 }
    }

    /// `w`/`h` = Größe DIESES Bilds (📌 Pin-GIF: ändert sich, wenn man sich bewegt)
    pub fn push(&mut self, raw: Vec<u8>, w: u32, h: u32, at: Instant) {
        if self.tx.send((raw, w, h, at)).is_ok() {
            self.frames += 1;
        }
    }

    /// Aufnahme beenden – der Thread schreibt das GIF fertig.
    pub fn finish(self) {
        crate::log!("GIF: Aufnahme beendet ({} Bilder)", self.frames);
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

/// Zeit zwischen zwei Bildern in 1/100 s (GIF-Einheit), mindestens 2
fn centis(d: Duration) -> u16 {
    ((d.as_millis() as f32 / 10.0).round() as u16).max(2)
}

fn run(
    rx: Receiver<(Vec<u8>, u32, u32, Instant)>,
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
        for (raw, fw, fh, at) in rx {
            // jedes Bild auf dieselbe GIF-Größe (Pin: Ausschnitt ist mal größer, mal kleiner)
            let rgb = downscale(&crate::save::to_rgb(&raw, format), fw, fh, ow, oh);
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
        let (tx, rx) = channel();
        let t0 = Instant::now();
        // 📌 Pin-GIF: die Bilder sind unterschiedlich groß → alle landen in 8×4
        for (i, (w, h)) in [(8u32, 4u32), (12, 6), (6, 3)].into_iter().enumerate() {
            let raw = [i as u8 * 80, 10, 200, 255].repeat((w * h) as usize); // RGBA
            tx.send((raw, w, h, t0 + Duration::from_millis(100 * i as u64))).unwrap();
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
}
