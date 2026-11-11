//! 🎬 Video-Aufnahme (MP4, H.264) – wie das GIF, nur als Video.
//!
//! Alles in Rust, ohne ffmpeg: läuft auch, wenn das Spiel im Steam-Container steckt.
//! OpenH264 (Cisco, BSD) kodiert, `mp4` packt die Bilder in eine .mp4-Datei.
//! Discord, Browser und Handys spielen das direkt ab.

use openh264::encoder::{BitRate, Encoder, EncoderConfig, FrameRate, FrameType, RateControlMode};
use openh264::formats::{RgbSliceU8, YUVBuffer};
use openh264::OpenH264API;
use std::io::{Seek, Write};
use std::time::Duration;

/// Längste Seite im Video (Pixel)
pub const MAX_SIDE: u32 = 1280;
/// ~3 Mbit/s → 15 s ≈ 6 MB (passt zu Discord ohne Nitro)
const BITRATE: u32 = 3_000_000;
/// Zeit-Einheit im MP4: Millisekunden
const TIMESCALE: u32 = 1000;

type Res<T> = Result<T, Box<dyn std::error::Error>>;

/// Zielgröße: längste Seite höchstens MAX_SIDE, gerade Zahlen (H.264 braucht das)
pub fn out_size(w: u32, h: u32) -> (u32, u32) {
    let scale = (MAX_SIDE as f32 / w.max(h).max(1) as f32).min(1.0);
    let even = |x: f32| ((x.round() as u32) / 2 * 2).max(2);
    (even(w as f32 * scale), even(h as f32 * scale))
}

/// Annex-B-Strom (00 00 01 / 00 00 00 01) in einzelne NAL-Einheiten teilen
pub fn split_nals(data: &[u8]) -> Vec<&[u8]> {
    let mut starts = Vec::new();
    let mut i = 0;
    while i + 3 <= data.len() {
        if data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 1 {
            starts.push((i, i + 3));
            i += 3;
        } else {
            i += 1;
        }
    }
    let mut out = Vec::new();
    for (k, &(_, begin)) in starts.iter().enumerate() {
        let mut end = starts.get(k + 1).map_or(data.len(), |s| s.0);
        while end > begin && data[end - 1] == 0 {
            end -= 1;
        }
        if end > begin {
            out.push(&data[begin..end]);
        }
    }
    out
}

pub struct VideoWriter<W: Write + Seek> {
    enc: Encoder,
    mp4: Option<mp4::Mp4Writer<W>>,
    sink: Option<W>,
    w: u32,
    h: u32,
    yuv: YUVBuffer,
    /// Ein Bild zurückhalten: seine Dauer = Abstand zum nächsten
    pending: Option<(Vec<u8>, bool, u64)>,
    pub frames: u32,
}

impl<W: Write + Seek> VideoWriter<W> {
    pub fn new(sink: W, w: u32, h: u32, fps: f32) -> Res<Self> {
        let cfg = EncoderConfig::new()
            .bitrate(BitRate::from_bps(BITRATE))
            .max_frame_rate(FrameRate::from_hz(fps))
            .rate_control_mode(RateControlMode::Bitrate)
            .skip_frames(true);
        let enc = Encoder::with_api_config(OpenH264API::from_source(), cfg)?;
        let yuv = YUVBuffer::new(w as usize, h as usize);
        Ok(VideoWriter { enc, mp4: None, sink: Some(sink), w, h, yuv, pending: None, frames: 0 })
    }

    /// Ein Bild (RGB8, genau w×h) zum Zeitpunkt `ms` (ab Aufnahmestart)
    pub fn push(&mut self, rgb: &[u8], ms: u64) -> Res<()> {
        self.yuv.read_rgb8(RgbSliceU8::new(rgb, (self.w as usize, self.h as usize)));
        let bs = self.enc.encode(&self.yuv)?;
        if matches!(bs.frame_type(), FrameType::Skip | FrameType::Invalid) {
            return Ok(());
        }
        let sync = matches!(bs.frame_type(), FrameType::IDR | FrameType::I);
        let annexb = bs.to_vec();
        let mut sample = Vec::with_capacity(annexb.len() + 16);
        let (mut sps, mut pps) = (None, None);
        for nal in split_nals(&annexb) {
            match nal[0] & 0x1f {
                7 => sps = Some(nal.to_vec()),
                8 => pps = Some(nal.to_vec()),
                9 => {}
                _ => {
                    sample.extend_from_slice(&(nal.len() as u32).to_be_bytes());
                    sample.extend_from_slice(nal);
                }
            }
        }
        if self.mp4.is_none() {
            let (Some(sps), Some(pps)) = (sps, pps) else { return Err("erstes Bild ohne SPS/PPS".into()) };
            self.start_mp4(sps, pps)?;
        }
        if sample.is_empty() {
            return Ok(());
        }
        if let Some((prev, psync, t0)) = self.pending.replace((sample, sync, ms)) {
            self.write(prev, psync, t0, ms.saturating_sub(t0).max(1) as u32)?;
        }
        Ok(())
    }

    fn start_mp4(&mut self, sps: Vec<u8>, pps: Vec<u8>) -> Res<()> {
        let brand = |s: &str| s.parse::<mp4::FourCC>();
        let cfg = mp4::Mp4Config {
            major_brand: brand("isom")?,
            minor_version: 512,
            compatible_brands: vec![brand("isom")?, brand("iso2")?, brand("avc1")?, brand("mp41")?],
            timescale: TIMESCALE,
        };
        let mut m = mp4::Mp4Writer::write_start(self.sink.take().ok_or("schon gestartet")?, &cfg)?;
        m.add_track(&mp4::TrackConfig {
            track_type: mp4::TrackType::Video,
            timescale: TIMESCALE,
            language: "und".into(),
            media_conf: mp4::MediaConfig::AvcConfig(mp4::AvcConfig {
                width: self.w as u16,
                height: self.h as u16,
                seq_param_set: sps,
                pic_param_set: pps,
            }),
        })?;
        self.mp4 = Some(m);
        Ok(())
    }

    fn write(&mut self, bytes: Vec<u8>, sync: bool, start: u64, dur: u32) -> Res<()> {
        let m = self.mp4.as_mut().ok_or("kein MP4")?;
        let sample = mp4::Mp4Sample { start_time: start, duration: dur, rendering_offset: 0, is_sync: sync, bytes: bytes.into() };
        m.write_sample(1, &sample)?;
        self.frames += 1;
        Ok(())
    }

    /// Letztes Bild schreiben (Dauer = `last`), Datei abschließen
    pub fn finish(mut self, last: Duration) -> Res<u32> {
        if let Some((prev, sync, t0)) = self.pending.take() {
            self.write(prev, sync, t0, last.as_millis().max(1) as u32)?;
        }
        if let Some(mut m) = self.mp4.take() {
            m.write_end()?;
            m.into_writer().flush()?;
        }
        Ok(self.frames)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn out_size_is_even_and_small() {
        assert_eq!(out_size(1500, 1000), (1280, 852));
        assert_eq!(out_size(301, 201), (300, 200));
    }

    #[test]
    fn splits_annexb() {
        let data = [0, 0, 0, 1, 0x67, 1, 2, 0, 0, 1, 0x68, 3, 0, 0, 0, 1, 0x65, 4, 5];
        let nals = split_nals(&data);
        assert_eq!(nals, vec![&[0x67, 1, 2][..], &[0x68, 3][..], &[0x65, 4, 5][..]]);
    }

    #[test]
    fn writes_mp4() {
        let (w, h) = (64u32, 48u32);
        let mut buf = std::io::Cursor::new(Vec::new());
        let mut v = VideoWriter::new(&mut buf, w, h, 10.0).unwrap();
        for i in 0..10u32 {
            let rgb: Vec<u8> = (0..w * h).flat_map(|p| [((p + i * 7) % 256) as u8, 80, 160]).collect();
            v.push(&rgb, i as u64 * 100).unwrap();
        }
        assert!(v.finish(Duration::from_millis(100)).unwrap() >= 2);
        let data = buf.into_inner();
        assert_eq!(&data[4..8], b"ftyp");
        let r = mp4::Mp4Reader::read_header(std::io::Cursor::new(&data), data.len() as u64).unwrap();
        assert_eq!(r.tracks().len(), 1);
    }
}
