//! Typ-Symbol am Rahmen und was der Auslöser damit macht.
//!
//! Mit der Typ-Taste (Standard: linker Trigger) schaltet man weiter:
//!   automatisch:  🪄 Auto → 🔁 Lens → 🪄 Auto …
//!   manuell:      🖼 Bild → 📝 Text → 🔳 QR → 🔁 Lens → 🖼 Bild …
//! Bild/Text/QR landen als PNG-Text-Chunk "ViewShot-Type" im Foto – die UI taggt es
//! direkt. Bei 🔁 Lens macht der Auslöser KEIN Foto, sondern startet den Live-Modus
//! (derselbe Bereich wird alle paar Sekunden neu fotografiert und übersetzt).
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
    Auto,
    Lens,
}

/// Reihenfolge beim Weiterschalten
const MANUAL: [PhotoType; 4] = [PhotoType::Image, PhotoType::Text, PhotoType::Qr, PhotoType::Lens];
const AUTO: [PhotoType; 2] = [PhotoType::Auto, PhotoType::Lens];

impl PhotoType {
    /// Alle Symbole – Reihenfolge = Ebene in der Symbol-Swapchain
    pub const ALL: [PhotoType; 5] = [PhotoType::Image, PhotoType::Text, PhotoType::Qr, PhotoType::Auto, PhotoType::Lens];

    /// Name wie in der UI (core/tags.py)
    pub fn as_str(self) -> &'static str {
        match self {
            PhotoType::Image => "image",
            PhotoType::Text => "text",
            PhotoType::Qr => "qr",
            PhotoType::Auto => "auto",
            PhotoType::Lens => "lens",
        }
    }

    /// Typ fürs PNG ("ViewShot-Type") – nur Bild/Text/QR, Auto erkennt die UI selbst
    pub fn tag(self) -> Option<&'static str> {
        matches!(self, PhotoType::Image | PhotoType::Text | PhotoType::Qr).then(|| self.as_str())
    }

    /// Nummer = Ebene in der Symbol-Swapchain
    pub fn index(self) -> u32 {
        self as u32
    }

    fn order(manual: bool) -> &'static [PhotoType] {
        if manual {
            &MANUAL
        } else {
            &AUTO
        }
    }

    /// Nächster Typ in der Reihenfolge des Modus
    pub fn next(self, manual: bool) -> Self {
        let order = Self::order(manual);
        match order.iter().position(|t| *t == self) {
            Some(i) => order[(i + 1) % order.len()],
            None => order[0],
        }
    }
}

/// Aktueller Typ – gilt für den ganzen Prozess, bleibt also auch bei einer
/// neuen Session (z. B. Welt-Wechsel) erhalten.
static CURRENT: AtomicU8 = AtomicU8::new(0);

/// Aktueller Typ; passt er nicht zum Modus (z. B. "Text" im Auto-Modus), der erste des Modus.
pub fn current(manual: bool) -> PhotoType {
    let t = PhotoType::ALL[CURRENT.load(Ordering::Relaxed) as usize % PhotoType::ALL.len()];
    let order = PhotoType::order(manual);
    if order.contains(&t) {
        t
    } else {
        order[0]
    }
}

/// Weiterschalten, gibt den neuen Typ zurück
pub fn cycle(manual: bool) -> PhotoType {
    let next = current(manual).next(manual);
    CURRENT.store(next.index() as u8, Ordering::Relaxed);
    next
}

const PNGS: [&[u8]; 5] = [
    include_bytes!("../assets/icon_image.png"),
    include_bytes!("../assets/icon_text.png"),
    include_bytes!("../assets/icon_qr.png"),
    include_bytes!("../assets/icon_auto.png"),
    include_bytes!("../assets/icon_lens.png"),
];

/// Alle Symbole als RGBA-Pixel (ICON_SIZE × ICON_SIZE), Reihenfolge wie PhotoType::ALL.
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
        // manuell: Bild → Text → QR → Lens → Bild
        assert_eq!(PhotoType::Image.next(true), PhotoType::Text);
        assert_eq!(PhotoType::Text.next(true), PhotoType::Qr);
        assert_eq!(PhotoType::Qr.next(true), PhotoType::Lens);
        assert_eq!(PhotoType::Lens.next(true), PhotoType::Image);
        // automatisch: Auto ↔ Lens
        assert_eq!(PhotoType::Auto.next(false), PhotoType::Lens);
        assert_eq!(PhotoType::Lens.next(false), PhotoType::Auto);
        // Typ aus dem anderen Modus → Anfang
        assert_eq!(PhotoType::Text.next(false), PhotoType::Auto);
        assert_eq!(PhotoType::Auto.next(true), PhotoType::Image);
    }

    #[test]
    fn only_photo_types_are_tagged() {
        assert_eq!(PhotoType::Qr.tag(), Some("qr"));
        assert_eq!(PhotoType::Auto.tag(), None);
        assert_eq!(PhotoType::Lens.tag(), None);
    }

    #[test]
    fn icons_decode() {
        let icons = pixels(false).unwrap();
        assert_eq!(icons.len(), PhotoType::ALL.len());
        assert!(icons.iter().all(|p| p.len() == (ICON_SIZE * ICON_SIZE * 4) as usize));
        // Ecke = roter Rand
        assert!(icons[0][0] > 200 && icons[0][2] < 60);
        // BGR: Rot landet hinten
        let bgr = pixels(true).unwrap();
        assert!(bgr[0][2] > 200 && bgr[0][0] < 60);
    }
}
