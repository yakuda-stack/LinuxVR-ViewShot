//! Pixel umwandeln und als PNG speichern (im Hintergrund-Thread,
//! damit das Spiel nicht ruckelt).

use std::path::PathBuf;

/// Vulkan-Formate, die wir verstehen (Zahlen aus vulkan_core.h)
pub const R8G8B8A8_UNORM: i64 = 37;
pub const R8G8B8A8_SRGB: i64 = 43;
pub const B8G8R8A8_UNORM: i64 = 44;
pub const B8G8R8A8_SRGB: i64 = 50;

pub fn is_supported(format: i64) -> bool {
    matches!(format, R8G8B8A8_UNORM | R8G8B8A8_SRGB | B8G8R8A8_UNORM | B8G8R8A8_SRGB)
}

/// Linear → sRGB (für UNORM-Swapchains, die OpenXR als "linear" behandelt)
fn linear_to_srgb_lut() -> [u8; 256] {
    let mut lut = [0u8; 256];
    for (i, v) in lut.iter_mut().enumerate() {
        let l = i as f32 / 255.0;
        let s = if l <= 0.003_130_8 { l * 12.92 } else { 1.055 * l.powf(1.0 / 2.4) - 0.055 };
        *v = (s * 255.0).round().clamp(0.0, 255.0) as u8;
    }
    lut
}

/// Rohdaten (4 Byte pro Pixel) → RGB8
pub fn to_rgb(raw: &[u8], format: i64) -> Vec<u8> {
    let bgr = matches!(format, B8G8R8A8_UNORM | B8G8R8A8_SRGB);
    let linear = matches!(format, R8G8B8A8_UNORM | B8G8R8A8_UNORM);
    let lut = linear_to_srgb_lut();
    let mut out = Vec::with_capacity(raw.len() / 4 * 3);
    // as_chunks: feste 4er-Stücke ([u8; 4]) – Rest (unvollständiges Pixel) fällt weg
    for px in raw.as_chunks::<4>().0 {
        let (r, g, b) = if bgr { (px[2], px[1], px[0]) } else { (px[0], px[1], px[2]) };
        if linear {
            out.extend_from_slice(&[lut[r as usize], lut[g as usize], lut[b as usize]]);
        } else {
            out.extend_from_slice(&[r, g, b]);
        }
    }
    out
}

/// Zielordner: $VIEWSHOT_OUTPUT_DIR oder ~/Bilder/LinuxVR-ViewShot
pub fn output_dir() -> PathBuf {
    if let Ok(d) = std::env::var("VIEWSHOT_OUTPUT_DIR") {
        return PathBuf::from(d);
    }
    dirs::picture_dir()
        .or_else(|| dirs::home_dir().map(|h| h.join("Pictures")))
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join("LinuxVR-ViewShot")
}

/// `photo_type` (manueller Modus): landet als Text-Chunk "ViewShot-Type"
/// im PNG ("image" / "text" / "qr") – die UI taggt das Foto dann direkt.
/// Name fürs nächste Foto – vorher festgelegt, damit der Layer weiß, zu welchem
/// Foto das 🥽 Overlay der UI gehört ("ViewShot-For").
pub fn photo_name() -> String {
    chrono::Local::now().format("ViewShot_%Y-%m-%d_%H-%M-%S%.3f.png").to_string()
}

/// 🎞 Name fürs nächste GIF (gleiches Schema wie die Fotos → Galerie sortiert richtig)
pub fn gif_name() -> String {
    chrono::Local::now().format("ViewShot_%Y-%m-%d_%H-%M-%S%.3f.gif").to_string()
}

pub fn save_png_async(name: String, raw: Vec<u8>, format: i64, w: u32, h: u32, photo_type: Option<&'static str>) {
    std::thread::spawn(move || {
        let rgb = to_rgb(&raw, format);
        let dir = output_dir();
        if let Err(e) = std::fs::create_dir_all(&dir) {
            crate::log!("Ordner {} kann nicht angelegt werden: {e}", dir.display());
            return;
        }
        let path = dir.join(name);
        let text: Vec<(&str, &str)> = photo_type.map(|t| ("ViewShot-Type", t)).into_iter().collect();
        let result = write_png(&path, &rgb, w, h, &text);
        match result {
            Ok(()) => crate::log!(
                "Foto gespeichert: {} ({w}x{h}){}",
                path.display(),
                photo_type.map(|t| format!(", Typ {t}")).unwrap_or_default()
            ),
            Err(e) => crate::log!("Foto speichern fehlgeschlagen: {e}"),
        }
    });
}

/// Live-Modus: immer DIESELBE Datei überschreiben (live/live.png) – landet nicht in
/// der Galerie. Die UI schaut auf die Änderungszeit und übersetzt das neue Bild.
/// `seq` = Nummer des Bilds ("ViewShot-Seq") – kommt mit der Übersetzung zurück,
/// so weiß der Layer, von wo aus das Bild gemacht wurde.
/// `roll` = Schräglage des Kopfes (Grad, "ViewShot-Roll") – der Dienst dreht das Bild gerade.
pub fn save_live_png_async(raw: Vec<u8>, format: i64, w: u32, h: u32, seq: u64, roll: f32) {
    std::thread::spawn(move || {
        let rgb = to_rgb(&raw, format);
        let dir = output_dir().join("live");
        if let Err(e) = std::fs::create_dir_all(&dir) {
            crate::log!("Ordner {} kann nicht angelegt werden: {e}", dir.display());
            return;
        }
        if let Err(e) = write_png(
            &dir.join("live.png"),
            &rgb,
            w,
            h,
            &[("ViewShot-Seq", &seq.to_string()), ("ViewShot-Roll", &format!("{roll:.2}"))],
        ) {
            crate::log!("Live-Bild speichern fehlgeschlagen: {e}");
        }
    });
}

/// Lens beendet → Live-Bild löschen, damit die UI zurück zum normalen Foto schaltet.
pub fn remove_live_png() {
    let _ = std::fs::remove_file(output_dir().join("live").join("live.png"));
}

/// RGB8-Pixel als PNG schreiben, mit Text-Stücken (z. B. "ViewShot-Type").
///
/// Erst in eine VERSTECKTE Hilfsdatei (".ViewShot_….png.part"), dann in
/// einem Schritt umbenennen. Die UI beobachtet den Ordner und würde sonst
/// eine halb geschriebene Datei öffnen (leeres Bild, OCR ohne Text).
/// Die Hilfsdatei hat keine ".png"-Endung → die UI ignoriert sie.
pub fn write_png(
    path: &std::path::Path,
    rgb: &[u8],
    w: u32,
    h: u32,
    text: &[(&str, &str)],
) -> Result<(), Box<dyn std::error::Error>> {
    use std::io::Write;
    let name = path.file_name().ok_or("kein Dateiname")?.to_string_lossy();
    let tmp = path.with_file_name(format!(".{name}.part"));
    let result = (|| -> Result<(), Box<dyn std::error::Error>> {
        let mut buf = std::io::BufWriter::new(std::fs::File::create(&tmp)?);
        let mut enc = png::Encoder::new(&mut buf, w, h);
        enc.set_color(png::ColorType::Rgb);
        enc.set_depth(png::BitDepth::Eight);
        for (key, value) in text {
            enc.add_text_chunk((*key).into(), (*value).into())?;
        }
        let mut writer = enc.write_header()?;
        writer.write_image_data(rgb)?;
        writer.finish()?; // IEND schreiben – Fehler NICHT beim Drop verschlucken
        buf.flush()?;
        Ok(())
    })();
    match result {
        Ok(()) => Ok(std::fs::rename(&tmp, path)?),
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
    fn bgr_swap() {
        assert_eq!(to_rgb(&[1, 2, 3, 255], B8G8R8A8_SRGB), vec![3, 2, 1]);
        assert_eq!(to_rgb(&[1, 2, 3, 255], R8G8B8A8_SRGB), vec![1, 2, 3]);
    }

    #[test]
    fn type_chunk_is_written() {
        let path = std::env::temp_dir().join("viewshot_type_test.png");
        write_png(&path, &[255; 2 * 2 * 3], 2, 2, &[("ViewShot-Type", "qr")]).unwrap();
        let dec = png::Decoder::new(std::io::BufReader::new(std::fs::File::open(&path).unwrap()));
        let reader = dec.read_info().unwrap();
        let text = &reader.info().uncompressed_latin1_text;
        assert!(text.iter().any(|t| t.keyword == "ViewShot-Type" && t.text == "qr"));
    }

    #[test]
    fn no_half_written_png_is_visible() {
        // Nur die fertige Datei liegt am Ende da – keine .part-Reste
        let dir = std::env::temp_dir().join("viewshot_atomic_test");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("ViewShot_test.png");
        write_png(&path, &[7; 4 * 4 * 3], 4, 4, &[]).unwrap();
        let names: Vec<_> = std::fs::read_dir(&dir).unwrap().map(|e| e.unwrap().file_name()).collect();
        assert_eq!(names, vec![std::ffi::OsString::from("ViewShot_test.png")]);
        // vollständig lesbar (IEND geschrieben)
        let mut reader = png::Decoder::new(std::io::BufReader::new(std::fs::File::open(&path).unwrap()))
            .read_info()
            .unwrap();
        let mut buf = vec![0; reader.output_buffer_size().unwrap()];
        reader.next_frame(&mut buf).unwrap();
        assert!(buf.iter().all(|&b| b == 7));
    }

    #[test]
    fn linear_brightens() {
        let out = to_rgb(&[128, 0, 255, 255], R8G8B8A8_UNORM);
        assert!(out[0] > 128 && out[1] == 0 && out[2] == 255);
    }
}
