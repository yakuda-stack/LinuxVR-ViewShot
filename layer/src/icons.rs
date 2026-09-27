//! Foto-Typ im manuellen Modus (Bild / Text / QR) und die Symbole dafür.
//!
//! Im manuellen Modus (layer.json: "detect_mode": "manual") zeigt der
//! Rahmen unten rechts ein Symbol. Mit der Typ-Taste schaltet man weiter:
//! Bild → Text → QR → Bild … Das Foto bekommt den Typ als PNG-Text-Chunk
//! "ViewShot-Type" mit – die UI liest ihn und taggt das Foto direkt.
//!
//! Die Symbole liegen als kleine PNGs in layer/assets/ und werden beim
//! Bauen fest in die .so eingebaut (include_bytes!).

use std::sync::atomic::{AtomicU8, Ordering};

pub const ICON_SIZE: u32 = 128;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PhotoType {
    Image,
    Text,
    Qr,
}

impl PhotoType {
    pub const ALL: [PhotoType; 3] = [PhotoType::Image, PhotoType::Text, PhotoType::Qr];

    /// Name wie in der UI (core/tags.py)
    pub fn as_str(self) -> &'static str {
        match self {
            PhotoType::Image => "image",
            PhotoType::Text => "text",
            PhotoType::Qr => "qr",
        }
    }

    /// Nummer = Ebene in der Symbol-Swapchain
    pub fn index(self) -> u32 {
        self as u32
    }

    pub fn next(self) -> Self {
        Self::ALL[(self.index() as usize + 1) % Self::ALL.len()]
    }
}

/// Aktueller Typ – gilt für den ganzen Prozess, bleibt also auch bei einer
/// neuen Session (z. B. Welt-Wechsel) erhalten.
static CURRENT: AtomicU8 = AtomicU8::new(0);

pub fn current() -> PhotoType {
    PhotoType::ALL[CURRENT.load(Ordering::Relaxed) as usize % PhotoType::ALL.len()]
}

/// Weiterschalten, gibt den neuen Typ zurück
pub fn cycle() -> PhotoType {
    let next = current().next();
    CURRENT.store(next.index() as u8, Ordering::Relaxed);
    next
}

const PNGS: [&[u8]; 3] = [
    include_bytes!("../assets/icon_image.png"),
    include_bytes!("../assets/icon_text.png"),
    include_bytes!("../assets/icon_qr.png"),
];

/// Die drei Symbole als RGBA-Pixel (ICON_SIZE × ICON_SIZE), Reihenfolge wie PhotoType::ALL.
/// `bgr` = für B8G8R8A8-Swapchains Rot und Blau tauschen.
pub fn pixels(bgr: bool) -> Result<Vec<Vec<u8>>, String> {
    PNGS.iter().map(|bytes| decode(bytes, bgr)).collect()
}

fn decode(bytes: &[u8], bgr: bool) -> Result<Vec<u8>, String> {
    let mut dec = png::Decoder::new(std::io::Cursor::new(bytes));
    dec.set_transformations(png::Transformations::EXPAND);
    let mut reader = dec.read_info().map_err(|e| format!("Symbol: {e}"))?;
    let mut buf = vec![0; reader.output_buffer_size().ok_or("Symbol: Größe unbekannt")?];
    let info = reader.next_frame(&mut buf).map_err(|e| format!("Symbol: {e}"))?;
    if info.width != ICON_SIZE || info.height != ICON_SIZE {
        return Err(format!("Symbol hat {}x{} statt {ICON_SIZE}", info.width, info.height));
    }
    let channels = info.color_type.samples();
    let mut out = Vec::with_capacity((ICON_SIZE * ICON_SIZE * 4) as usize);
    for px in buf[..info.buffer_size()].chunks_exact(channels) {
        let (r, g, b) = if channels >= 3 { (px[0], px[1], px[2]) } else { (px[0], px[0], px[0]) };
        let (r, b) = if bgr { (b, r) } else { (r, b) };
        out.extend_from_slice(&[r, g, b, 255]);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cycle_order() {
        assert_eq!(PhotoType::Image.next(), PhotoType::Text);
        assert_eq!(PhotoType::Text.next(), PhotoType::Qr);
        assert_eq!(PhotoType::Qr.next(), PhotoType::Image);
    }

    #[test]
    fn icons_decode() {
        let icons = pixels(false).unwrap();
        assert_eq!(icons.len(), 3);
        assert!(icons.iter().all(|p| p.len() == (ICON_SIZE * ICON_SIZE * 4) as usize));
        // Ecke = roter Rand
        assert!(icons[0][0] > 200 && icons[0][2] < 60);
        // BGR: Rot landet hinten
        let bgr = pixels(true).unwrap();
        assert!(bgr[0][2] > 200 && bgr[0][0] < 60);
    }
}
