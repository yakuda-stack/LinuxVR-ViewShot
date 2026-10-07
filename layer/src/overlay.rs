//! 🥽 Übersetzung in VR über dem Original.
//!
//! Die UI malt die Übersetzung als durchsichtiges PNG (graue Kästchen über den
//! Textzeilen) nach  <Foto-Ordner>/overlay/overlay.png. Im PNG steht als Text
//! "ViewShot-For", wofür es ist: der Dateiname des Fotos oder "live" (🔁 Lens).
//!
//! Der Layer schaut höchstens alle 0,25 s nach, ob die Datei neu ist, und lädt
//! sie dann in einem eigenen Thread (ein 1024er-PNG dekodieren dauert ein paar
//! ms – das soll nicht im Render-Thread des Spiels passieren).

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime};

/// "ViewShot-For" im Lens-Modus
pub const LIVE: &str = "live";

/// Ein geladenes Overlay-Bild (RGBA, nicht vormultipliert)
pub struct Image {
    pub for_name: String,
    /// 🔁 Lens: zu welchem Live-Bild ("ViewShot-Seq"), 0 = unbekannt
    pub seq: u64,
    /// Bild wurde um so viel geradegedreht (Radiant, "ViewShot-Roll" in Grad)
    pub roll: f32,
    pub w: u32,
    pub h: u32,
    pub rgba: Vec<u8>,
    /// Änderungszeit der Datei – älter als Foto/Lens-Start = gehört nicht dazu
    pub modified: SystemTime,
}

pub fn path() -> PathBuf {
    crate::save::output_dir().join("overlay").join("overlay.png")
}

/// PNG → RGBA + "ViewShot-For"
pub fn decode(bytes: &[u8], modified: SystemTime) -> Result<Image, String> {
    let mut dec = png::Decoder::new(std::io::Cursor::new(bytes));
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = dec.read_info().map_err(|e| format!("Overlay: {e}"))?;
    let mut buf = vec![0; reader.output_buffer_size().ok_or("Overlay: Größe unbekannt")?];
    let frame = reader.next_frame(&mut buf).map_err(|e| format!("Overlay: {e}"))?;
    let _ = reader.finish(); // Text-Stücke hinter den Bilddaten auch noch lesen
    let info = reader.info();
    let for_name = png_text(info, "ViewShot-For");
    // 🔁 Lens: Nummer des Live-Bilds, zu dem die Übersetzung gehört (0 = unbekannt)
    let seq = png_text(info, "ViewShot-Seq").trim().parse().unwrap_or(0);
    // so weit hat der Dienst das Bild geradegedreht (Grad → Radiant), 0 = gar nicht
    let roll = png_text(info, "ViewShot-Roll").trim().parse::<f32>().unwrap_or(0.0).to_radians();

    let px = &buf[..frame.buffer_size()];
    let rgba: Vec<u8> = match frame.color_type {
        png::ColorType::Rgba => px.to_vec(),
        png::ColorType::Rgb => px.as_chunks::<3>().0.iter().flat_map(|p| [p[0], p[1], p[2], 255]).collect(),
        png::ColorType::GrayscaleAlpha => px.as_chunks::<2>().0.iter().flat_map(|p| [p[0], p[0], p[0], p[1]]).collect(),
        png::ColorType::Grayscale => px.iter().flat_map(|&g| [g, g, g, 255]).collect(),
        png::ColorType::Indexed => return Err("Overlay: Palette nicht erwartet".into()),
    };
    Ok(Image { for_name, seq, roll, w: frame.width, h: frame.height, rgba, modified })
}

/// Text-Stück aus dem PNG (alle drei Arten), "" = keins
fn png_text(info: &png::Info, key: &str) -> String {
    info.uncompressed_latin1_text
        .iter()
        .filter(|t| t.keyword == key)
        .map(|t| t.text.clone())
        .chain(info.utf8_text.iter().filter(|t| t.keyword == key).filter_map(|t| t.get_text().ok()))
        .chain(info.compressed_latin1_text.iter().filter(|t| t.keyword == key).filter_map(|t| t.get_text().ok()))
        .next()
        .unwrap_or_default()
}

struct State {
    checked: Option<Instant>,
    modified: Option<SystemTime>,
    loading: bool,
    current: Option<Arc<Image>>,
}

/// Beobachtete Bilddatei: lädt eine neue Version im Hintergrund-Thread.
pub struct Watched {
    path: fn() -> PathBuf,
    state: Mutex<State>,
}

impl Watched {
    pub const fn new(path: fn() -> PathBuf) -> Self {
        Watched { path, state: Mutex::new(State { checked: None, modified: None, loading: false, current: None }) }
    }

    /// Aktuelles Bild (None = keins da). Lädt ein neues im Hintergrund.
    pub fn get(&'static self) -> Option<Arc<Image>> {
        let mut st = self.state.lock().unwrap_or_else(|e| e.into_inner());
        // alle 80 ms nachsehen (nur ein stat) – so läuft auch das Aufklappen im Panel flüssig
        if st.checked.is_none_or(|t| t.elapsed() >= Duration::from_millis(80)) {
            st.checked = Some(Instant::now());
            let p = (self.path)();
            match std::fs::metadata(&p).and_then(|m| m.modified()) {
                Err(_) => {
                    st.current = None; // Datei weg (UI hat es ausgeschaltet)
                    st.modified = None;
                }
                Ok(m) if Some(m) != st.modified && !st.loading => {
                    st.modified = Some(m);
                    st.loading = true;
                    std::thread::spawn(move || {
                        let loaded = std::fs::read(&p).map_err(|e| e.to_string()).and_then(|b| decode(&b, m));
                        let mut st = self.state.lock().unwrap_or_else(|e| e.into_inner());
                        st.loading = false;
                        match loaded {
                            Ok(img) => st.current = Some(Arc::new(img)),
                            Err(e) => crate::log!("Bild nicht lesbar ({}): {e}", p.display()),
                        }
                    });
                }
                Ok(_) => {}
            }
        }
        st.current.clone()
    }
}

pub static OVERLAY: Watched = Watched::new(path);
pub static PANEL: Watched = Watched::new(crate::panel::image_file);

/// Aktuelles Overlay-Bild (None = keins da).
pub fn get() -> Option<Arc<Image>> {
    OVERLAY.get()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn png_with_text(key: &str, value: &str) -> Vec<u8> {
        let mut out = Vec::new();
        {
            let mut enc = png::Encoder::new(&mut out, 2, 1);
            enc.set_color(png::ColorType::Rgba);
            enc.set_depth(png::BitDepth::Eight);
            enc.add_text_chunk(key.into(), value.into()).unwrap();
            let mut w = enc.write_header().unwrap();
            w.write_image_data(&[10, 20, 30, 0, 200, 200, 200, 230]).unwrap();
        }
        out
    }

    #[test]
    fn decode_keeps_alpha_and_reads_target() {
        let img = decode(&png_with_text("ViewShot-For", "ViewShot_1.png"), SystemTime::UNIX_EPOCH).unwrap();
        assert_eq!((img.w, img.h), (2, 1));
        assert_eq!(img.for_name, "ViewShot_1.png");
        assert_eq!(img.rgba, vec![10, 20, 30, 0, 200, 200, 200, 230]);
    }

    #[test]
    fn decode_without_target_is_empty_name() {
        let img = decode(&png_with_text("Other", "x"), SystemTime::UNIX_EPOCH).unwrap();
        assert_eq!(img.for_name, "");
        assert_eq!(img.seq, 0);
    }

    #[test]
    fn decode_reads_lens_seq() {
        let img = decode(&png_with_text("ViewShot-Seq", "1791388657056"), SystemTime::UNIX_EPOCH).unwrap();
        assert_eq!(img.seq, 1791388657056);
    }
}
