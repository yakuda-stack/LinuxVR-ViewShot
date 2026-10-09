//! 🗜 GIF verkleinern, bis es unter eine Größe passt (Discord: 10 MB).
//!
//!   viewshot-daemon gif-shrink EIN.gif AUS.gif [MAX_BYTES]
//!
//! Die Desktop-App ruft das auf (Galerie → 🗜 Komprimieren). Kein Python-Paket nötig.
//! Stellschrauben, in dieser Reihenfolge:
//!   1. mehr als 10 Bilder/s → Bilder auslassen (Anzeigedauer wird addiert, Länge bleibt gleich)
//!   2. kleiner skalieren (aber nicht unter MIN_SIDE an der längsten Seite)
//!   3. dann doch weniger Bilder/s
//!
//! Jede Runde schätzt aus der letzten Dateigröße, wie viel noch fehlt.
//! Ausgabe auf stdout: eine JSON-Zeile mit Größe, Maßen, Bildern, Bildern/s.

use image::AnimationDecoder;
use std::io::Write;
use std::path::Path;

/// Discord (ohne Nitro) nimmt bis 10 MB – etwas Luft lassen
pub const DEFAULT_MAX: u64 = 9_500_000;
/// Nicht kleiner als das an der längsten Seite skalieren (sonst lieber weniger Bilder/s)
const MIN_SIDE: f32 = 320.0;
/// Größere Bilder schon beim Einlesen verkleinern (spart Arbeitsspeicher)
const READ_MAX_SIDE: u32 = 1024;
/// Mehr Bilder/s braucht ein GIF zum Teilen nicht
const MAX_FPS: f32 = 10.0;
const MAX_ROUNDS: usize = 8;

/// fertiges GIF, (Breite, Höhe), Anzahl Bilder
type Encoded = (Vec<u8>, (u32, u32), usize);

struct Clip {
    frames: Vec<(image::RgbaImage, u32)>, // Bild, Anzeigedauer in ms
}

fn read(path: &Path) -> Result<Clip, String> {
    let file = std::io::BufReader::new(std::fs::File::open(path).map_err(|e| format!("{}: {e}", path.display()))?);
    let dec = image::codecs::gif::GifDecoder::new(file).map_err(|e| format!("kein GIF: {e}"))?;
    let mut frames = Vec::new();
    for f in dec.into_frames() {
        let f = f.map_err(|e| format!("GIF kaputt: {e}"))?;
        let (n, d) = f.delay().numer_denom_ms();
        let ms = n.checked_div(d).unwrap_or(100).max(20);
        let mut img = f.into_buffer();
        let side = img.width().max(img.height());
        if side > READ_MAX_SIDE {
            let s = READ_MAX_SIDE as f32 / side as f32;
            img = scale(&img, s);
        }
        frames.push((img, ms));
    }
    if frames.is_empty() {
        return Err("GIF ohne Bilder".into());
    }
    Ok(Clip { frames })
}

fn scale(img: &image::RgbaImage, s: f32) -> image::RgbaImage {
    let w = ((img.width() as f32 * s).round() as u32).max(1);
    let h = ((img.height() as f32 * s).round() as u32).max(1);
    if (w, h) == img.dimensions() {
        return img.clone();
    }
    image::imageops::resize(img, w, h, image::imageops::FilterType::Triangle)
}

/// Jedes `step`-te Bild nehmen, die Anzeigedauer der ausgelassenen dazuzählen
fn thin(frames: &[(image::RgbaImage, u32)], step: usize) -> Vec<(&image::RgbaImage, u32)> {
    frames
        .chunks(step.max(1))
        .map(|c| (&c[0].0, c.iter().map(|f| f.1).sum()))
        .collect()
}

/// GIF bauen: Farben je Bild parallel ausrechnen (das dauert), dann der Reihe nach schreiben
fn encode(clip: &Clip, s: f32, step: usize) -> Result<Encoded, String> {
    let picked = thin(&clip.frames, step);
    let threads = std::thread::available_parallelism().map_or(4, |n| n.get()).clamp(1, 8);
    let chunk = picked.len().div_ceil(threads).max(1);
    let mut out: Vec<gif::Frame<'static>> = Vec::with_capacity(picked.len());
    std::thread::scope(|sc| {
        let handles: Vec<_> = picked
            .chunks(chunk)
            .map(|part| {
                sc.spawn(move || {
                    part.iter()
                        .map(|(img, ms)| {
                            let small = scale(img, s);
                            let (w, h) = small.dimensions();
                            let mut px = small.into_raw();
                            let mut f = gif::Frame::from_rgba_speed(w as u16, h as u16, &mut px, 10);
                            f.delay = ((*ms as f32 / 10.0).round() as u16).max(2);
                            f
                        })
                        .collect::<Vec<_>>()
                })
            })
            .collect();
        for h in handles {
            out.extend(h.join().unwrap_or_default());
        }
    });
    let (w, h) = out.first().map(|f| (f.width as u32, f.height as u32)).ok_or("keine Bilder")?;
    let mut buf = Vec::new();
    {
        let mut enc = gif::Encoder::new(&mut buf, w as u16, h as u16, &[]).map_err(|e| e.to_string())?;
        enc.set_repeat(gif::Repeat::Infinite).map_err(|e| e.to_string())?;
        for f in &out {
            enc.write_frame(f).map_err(|e| e.to_string())?;
        }
    }
    Ok((buf, (w, h), out.len()))
}

/// Verkleinern, bis es unter `max` Bytes passt. → ((GIF, Maße, Bilder), Bilder/s)
pub fn shrink(input: &Path, max: u64) -> Result<(Encoded, f32), String> {
    let clip = read(input)?;
    let total_ms: u32 = clip.frames.iter().map(|f| f.1).sum();
    let fps0 = clip.frames.len() as f32 * 1000.0 / total_ms.max(1) as f32;
    let side0 = clip.frames[0].0.width().max(clip.frames[0].0.height()) as f32;
    // 1. höchstens MAX_FPS
    let mut step = (fps0 / MAX_FPS).ceil().max(1.0) as usize;
    let mut s = 1.0f32;
    for round in 0..MAX_ROUNDS {
        let (data, dims, n) = encode(&clip, s, step)?;
        let fps = fps0 / step as f32;
        crate::log::line(&format!(
            "GIF verkleinern, Runde {}: {}×{}, {n} Bilder ({fps:.1}/s) → {:.1} MB",
            round + 1,
            dims.0,
            dims.1,
            data.len() as f64 / 1e6
        ));
        if data.len() as u64 <= max {
            return Ok(((data, dims, n), fps));
        }
        if n <= 2 {
            break;
        }
        // Größe ~ Fläche × Bilder → so viel muss noch weg (mit etwas Reserve)
        let need = (max as f32 / data.len() as f32) * 0.92;
        let want_s = s * need.sqrt();
        if side0 * want_s >= MIN_SIDE {
            s = want_s.max(s * 0.5);
        } else {
            // 2. Fläche nur bis MIN_SIDE, 3. den Rest über weniger Bilder/s
            let floor = (MIN_SIDE / side0).min(1.0);
            let area_gain = (floor / s).powi(2); // < 1, wenn wir noch kleiner skalieren
            s = floor.min(s);
            let more = need / area_gain;
            // reicht das Kleiner-Skalieren (fast) schon, die Bilder/s erst mal lassen
            if more < 0.92 {
                let more = more.max(0.05);
                step = ((step as f32 / more).ceil() as usize).max(step + 1);
            }
        }
    }
    Err(format!("passt nicht unter {:.1} MB", max as f64 / 1e6))
}

/// `viewshot-daemon gif-shrink EIN AUS [MAX_BYTES]` – Exit 0 = fertig, 1 = Fehler
pub fn main(args: &[String]) -> i32 {
    let (Some(input), Some(output)) = (args.first(), args.get(1)) else {
        eprintln!("viewshot-daemon gif-shrink EIN.gif AUS.gif [MAX_BYTES]");
        return 2;
    };
    let max = args.get(2).and_then(|m| m.parse().ok()).unwrap_or(DEFAULT_MAX);
    match shrink(Path::new(input), max) {
        Ok(((data, (w, h), n), fps)) => {
            let write = std::fs::File::create(output).and_then(|mut f| f.write_all(&data).and_then(|_| f.flush()));
            if let Err(e) = write {
                eprintln!("{output}: {e}");
                return 1;
            }
            println!("{}", serde_json::json!({"size": data.len(), "w": w, "h": h, "frames": n, "fps": (fps * 10.0).round() / 10.0}));
            0
        }
        Err(e) => {
            eprintln!("{e}");
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shrinks_below_limit() {
        // 40 Bilder 400×300 Rauschen (lässt sich schlecht packen) mit 20 Bildern/s
        let dir = std::env::temp_dir().join(format!("viewshot_shrink_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let src = dir.join("in.gif");
        {
            let mut f = std::fs::File::create(&src).unwrap();
            let mut enc = gif::Encoder::new(&mut f, 400, 300, &[]).unwrap();
            let mut seed = 1u32;
            for _ in 0..40 {
                let mut px: Vec<u8> = (0..400 * 300 * 4)
                    .map(|i| {
                        seed = seed.wrapping_mul(1_103_515_245).wrapping_add(12345);
                        if i % 4 == 3 { 255 } else { (seed >> 16) as u8 }
                    })
                    .collect();
                let mut fr = gif::Frame::from_rgba_speed(400, 300, &mut px, 30);
                fr.delay = 5;
                enc.write_frame(&fr).unwrap();
            }
        }
        let before = std::fs::metadata(&src).unwrap().len();
        let max = before / 4;
        let ((data, (w, _), n), fps) = shrink(&src, max).unwrap();
        assert!((data.len() as u64) <= max, "{} > {max}", data.len());
        assert!(fps <= MAX_FPS + 0.01, "fps {fps}");
        assert!(n >= 2 && w <= 400);
        // ist ein lesbares GIF
        image::load_from_memory(&data).unwrap();
        std::fs::remove_dir_all(&dir).ok();
    }
}
