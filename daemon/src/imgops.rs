//! Bild-Operationen für die Texterkennung – so nah wie möglich an OpenCV
//! (cv2.resize INTER_LINEAR, cv2.warpPerspective INTER_CUBIC + BORDER_REPLICATE),
//! damit dieselben Modelle dieselben Ergebnisse liefern wie RapidOCR in der App.
//!
//! Bilder sind immer 3 Kanäle, Reihenfolge **BGR** (wie OpenCV/RapidOCR).

#[derive(Clone, Debug)]
pub struct Img {
    pub w: usize,
    pub h: usize,
    /// BGR, Zeile für Zeile
    pub data: Vec<u8>,
}

impl Img {
    pub fn new(w: usize, h: usize) -> Self {
        Img { w, h, data: vec![0; w * h * 3] }
    }

    #[inline]
    pub fn px(&self, x: usize, y: usize) -> [u8; 3] {
        let i = (y * self.w + x) * 3;
        [self.data[i], self.data[i + 1], self.data[i + 2]]
    }

    /// Aus einem RGBA-/RGB-Bild (image-Crate). Durchsichtige Stellen → wie RapidOCR:
    /// auf Weiß gelegt (cvt_four_to_three mischt mit weißem Hintergrund).
    pub fn from_dynamic(img: &image::DynamicImage) -> Self {
        let rgba = img.to_rgba8();
        let (w, h) = (rgba.width() as usize, rgba.height() as usize);
        let mut out = Img::new(w, h);
        for (i, p) in rgba.pixels().enumerate() {
            let a = p[3] as f32 / 255.0;
            let mix = |c: u8| (c as f32 * a + 255.0 * (1.0 - a)).round().clamp(0.0, 255.0) as u8;
            let (r, g, b) = if p[3] == 255 { (p[0], p[1], p[2]) } else { (mix(p[0]), mix(p[1]), mix(p[2])) };
            out.data[i * 3] = b;
            out.data[i * 3 + 1] = g;
            out.data[i * 3 + 2] = r;
        }
        out
    }

    /// Wie cv2.resize(..., INTER_LINEAR): Pixelmitten, keine Kantenglättung beim Verkleinern.
    pub fn resize(&self, nw: usize, nh: usize) -> Img {
        let mut out = Img::new(nw.max(1), nh.max(1));
        if self.w == 0 || self.h == 0 {
            return out;
        }
        let sx = self.w as f32 / out.w as f32;
        let sy = self.h as f32 / out.h as f32;
        let xs: Vec<(usize, usize, f32)> = (0..out.w).map(|x| lin_coord(x, sx, self.w)).collect();
        for y in 0..out.h {
            let (y0, y1, fy) = lin_coord(y, sy, self.h);
            for (x, &(x0, x1, fx)) in xs.iter().enumerate() {
                for c in 0..3 {
                    let p = |xx: usize, yy: usize| self.data[(yy * self.w + xx) * 3 + c] as f32;
                    let top = p(x0, y0) * (1.0 - fx) + p(x1, y0) * fx;
                    let bot = p(x0, y1) * (1.0 - fx) + p(x1, y1) * fx;
                    let v = top * (1.0 - fy) + bot * fy;
                    out.data[(y * out.w + x) * 3 + c] = v.round().clamp(0.0, 255.0) as u8;
                }
            }
        }
        out
    }

    /// Schwarzen Rand oben/unten anfügen (cv2.copyMakeBorder, BORDER_CONSTANT 0).
    pub fn pad_vertical(&self, pad: usize) -> Img {
        let mut out = Img::new(self.w, self.h + 2 * pad);
        let row = self.w * 3;
        out.data[pad * row..(pad + self.h) * row].copy_from_slice(&self.data);
        out
    }

    /// np.rot90: 90° gegen den Uhrzeigersinn.
    pub fn rot90(&self) -> Img {
        let mut out = Img::new(self.h, self.w);
        for y in 0..out.h {
            for x in 0..out.w {
                // out[y][x] = in[x][W-1-y]
                let p = self.px(self.w - 1 - y, x);
                let i = (y * out.w + x) * 3;
                out.data[i..i + 3].copy_from_slice(&p);
            }
        }
        out
    }

    /// cv2.rotate(img, ROTATE_180)
    pub fn rot180(&self) -> Img {
        let mut out = Img::new(self.w, self.h);
        let n = self.w * self.h;
        for i in 0..n {
            let j = n - 1 - i;
            out.data[i * 3..i * 3 + 3].copy_from_slice(&self.data[j * 3..j * 3 + 3]);
        }
        out
    }
}

/// Quell-Koordinate für bilineares Verkleinern/Vergrößern (OpenCV-Regeln an den Rändern).
fn lin_coord(d: usize, scale: f32, len: usize) -> (usize, usize, f32) {
    let f = (d as f32 + 0.5) * scale - 0.5;
    let mut s = f.floor();
    let mut frac = f - s;
    if s < 0.0 {
        s = 0.0;
        frac = 0.0;
    }
    let s = s as usize;
    if s >= len - 1 {
        return (len - 1, len - 1, 0.0);
    }
    (s, s + 1, frac)
}

/// Kubischer Kern von OpenCV (A = -0.75).
fn cubic_weights(t: f32) -> [f32; 4] {
    const A: f32 = -0.75;
    let w0 = ((A * (t + 1.0) - 5.0 * A) * (t + 1.0) + 8.0 * A) * (t + 1.0) - 4.0 * A;
    let w1 = ((A + 2.0) * t - (A + 3.0)) * t * t + 1.0;
    let w2 = ((A + 2.0) * (1.0 - t) - (A + 3.0)) * (1.0 - t) * (1.0 - t) + 1.0;
    let w3 = 1.0 - w0 - w1 - w2;
    [w0, w1, w2, w3]
}

/// 3×3-Matrix, die die 4 Punkte `src` auf `dst` abbildet (cv2.getPerspectiveTransform).
pub fn perspective_transform(src: &[[f32; 2]; 4], dst: &[[f32; 2]; 4]) -> Option<[f64; 9]> {
    // 8 Unbekannte a..h, m22 = 1
    let mut m = [[0f64; 9]; 8];
    for i in 0..4 {
        let (x, y) = (src[i][0] as f64, src[i][1] as f64);
        let (u, v) = (dst[i][0] as f64, dst[i][1] as f64);
        m[i] = [x, y, 1.0, 0.0, 0.0, 0.0, -x * u, -y * u, u];
        m[i + 4] = [0.0, 0.0, 0.0, x, y, 1.0, -x * v, -y * v, v];
    }
    // Gauß mit Pivotsuche
    for col in 0..8 {
        let piv = (col..8).max_by(|&a, &b| m[a][col].abs().total_cmp(&m[b][col].abs()))?;
        if m[piv][col].abs() < 1e-12 {
            return None;
        }
        m.swap(col, piv);
        let pivot = m[col];
        for (r, row) in m.iter_mut().enumerate() {
            if r != col {
                let f = row[col] / pivot[col];
                for (v, p) in row.iter_mut().zip(pivot.iter()).skip(col) {
                    *v -= f * p;
                }
            }
        }
    }
    let s: Vec<f64> = (0..8).map(|i| m[i][8] / m[i][i]).collect();
    Some([s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], 1.0])
}

fn invert3(m: &[f64; 9]) -> Option<[f64; 9]> {
    let det = m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6])
        + m[2] * (m[3] * m[7] - m[4] * m[6]);
    if det.abs() < 1e-15 {
        return None;
    }
    let d = 1.0 / det;
    Some([
        (m[4] * m[8] - m[5] * m[7]) * d,
        (m[2] * m[7] - m[1] * m[8]) * d,
        (m[1] * m[5] - m[2] * m[4]) * d,
        (m[5] * m[6] - m[3] * m[8]) * d,
        (m[0] * m[8] - m[2] * m[6]) * d,
        (m[2] * m[3] - m[0] * m[5]) * d,
        (m[3] * m[7] - m[4] * m[6]) * d,
        (m[1] * m[6] - m[0] * m[7]) * d,
        (m[0] * m[4] - m[1] * m[3]) * d,
    ])
}

/// Schrägen Textbereich gerade ausschneiden (get_rotate_crop_image in RapidOCR).
/// Hohe, schmale Ausschnitte werden um 90° gedreht (senkrechte Schrift).
pub fn rotate_crop(img: &Img, pts: &[[f32; 2]; 4]) -> Img {
    let d = |a: [f32; 2], b: [f32; 2]| ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt();
    let cw = d(pts[0], pts[1]).max(d(pts[2], pts[3])) as usize;
    let ch = d(pts[0], pts[3]).max(d(pts[1], pts[2])) as usize;
    let (cw, ch) = (cw.max(1), ch.max(1));
    let dst = [[0.0, 0.0], [cw as f32, 0.0], [cw as f32, ch as f32], [0.0, ch as f32]];
    let Some(inv) = perspective_transform(pts, &dst).and_then(|m| invert3(&m)) else {
        return Img::new(cw, ch);
    };
    let mut out = Img::new(cw, ch);
    let clampi = |v: i64, max: usize| v.clamp(0, max as i64 - 1) as usize;
    for y in 0..ch {
        for x in 0..cw {
            let (xf, yf) = (x as f64, y as f64);
            let w = inv[6] * xf + inv[7] * yf + inv[8];
            let w = if w.abs() < 1e-12 { 1e-12 } else { w };
            let sx = ((inv[0] * xf + inv[1] * yf + inv[2]) / w) as f32;
            let sy = ((inv[3] * xf + inv[4] * yf + inv[5]) / w) as f32;
            let (x0, y0) = (sx.floor(), sy.floor());
            let wx = cubic_weights(sx - x0);
            let wy = cubic_weights(sy - y0);
            let mut acc = [0f32; 3];
            for (j, wyj) in wy.iter().enumerate() {
                let yy = clampi(y0 as i64 - 1 + j as i64, img.h);
                for (i, wxi) in wx.iter().enumerate() {
                    let xx = clampi(x0 as i64 - 1 + i as i64, img.w);
                    let p = img.px(xx, yy);
                    let wgt = wxi * wyj;
                    for (a, v) in acc.iter_mut().zip(p) {
                        *a += v as f32 * wgt;
                    }
                }
            }
            let o = (y * cw + x) * 3;
            for (d, a) in out.data[o..o + 3].iter_mut().zip(acc) {
                *d = a.round().clamp(0.0, 255.0) as u8;
            }
        }
    }
    if ch as f32 / cw as f32 >= 1.5 {
        out.rot90()
    } else {
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resize_keeps_flat_color() {
        let mut img = Img::new(4, 3);
        img.data.iter_mut().for_each(|v| *v = 77);
        let r = img.resize(9, 5);
        assert!(r.data.iter().all(|&v| v == 77));
    }

    #[test]
    fn rot90_counter_clockwise() {
        // 2x1: links rot(B=0,G=0,R=255), rechts blau → nach rot90 oben blau, unten rot
        let mut img = Img::new(2, 1);
        img.data = vec![0, 0, 255, 255, 0, 0];
        let r = img.rot90();
        assert_eq!((r.w, r.h), (1, 2));
        assert_eq!(r.px(0, 0), [255, 0, 0]);
        assert_eq!(r.px(0, 1), [0, 0, 255]);
    }

    #[test]
    fn perspective_identity() {
        let p = [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]];
        let m = perspective_transform(&p, &p).unwrap();
        for (a, b) in m.iter().zip([1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]) {
            assert!((a - b).abs() < 1e-9);
        }
    }
}
