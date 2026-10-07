//! Rechnet aus den Handpositionen den Bildausschnitt (Rechteck in Pixeln).
//!
//! Idee: Beide Hände werden ins Bild projiziert.
//! Linke Hand = eine Ecke, rechte Hand = gegenüberliegende Ecke.
//! Danach rücken die Ecken um `inset_m` (Meter an der Hand) nach innen,
//! damit die Finger NICHT mit im Foto sind – wie beim roten Rahmen im Vorbild.

use openxr_sys as xr;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}

/// Eine projizierte Hand: Bildkoordinate 0..1 und Entfernung zum Auge (Meter)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Projected {
    pub u: f32,
    pub v: f32,
    pub depth: f32,
}

/// Dreht Vektor `v` mit der INVERSEN von Quaternion `q`.
fn rotate_inv(q: xr::Quaternionf, v: [f32; 3]) -> [f32; 3] {
    // Inverse eines Einheitsquaternions = (-x, -y, -z, w)
    let (ux, uy, uz, w) = (-q.x, -q.y, -q.z, q.w);
    // v' = v + 2w(u×v) + 2u×(u×v)
    let cx = uy * v[2] - uz * v[1];
    let cy = uz * v[0] - ux * v[2];
    let cz = ux * v[1] - uy * v[0];
    let ccx = uy * cz - uz * cy;
    let ccy = uz * cx - ux * cz;
    let ccz = ux * cy - uy * cx;
    [
        v[0] + 2.0 * (w * cx + ccx),
        v[1] + 2.0 * (w * cy + ccy),
        v[2] + 2.0 * (w * cz + ccz),
    ]
}

/// Dreht Vektor `v` mit Quaternion `q` (Auge → Welt).
fn rotate(q: xr::Quaternionf, v: [f32; 3]) -> [f32; 3] {
    let inv = xr::Quaternionf { x: -q.x, y: -q.y, z: -q.z, w: q.w };
    rotate_inv(inv, v)
}

/// Eine Linie des sichtbaren Rahmens: Mitte/Ausrichtung + Breite/Höhe in Metern
#[derive(Clone, Copy, Debug)]
pub struct EdgeQuad {
    pub pose: xr::Posef,
    pub width: f32,
    pub height: f32,
}

/// Baut aus dem Pixel-Ausschnitt 4 Linien (oben, unten, links, rechts),
/// die im Raum in Tiefe `depth` vor dem Auge schweben – genau dort,
/// wo man den Ausschnitt sieht. `thickness` = Linienstärke in Metern.
pub fn edge_quads(eye: &xr::Posef, fov: &xr::Fovf, img: Rect, rect: Rect, depth: f32, thickness: f32) -> [EdgeQuad; 4] {
    let (l, r) = (fov.angle_left.tan(), fov.angle_right.tan());
    let (up, dn) = (fov.angle_up.tan(), fov.angle_down.tan());
    // Pixel → Position im Auge-Koordinatensystem (in Tiefe `depth`)
    let ex = |px: i32| (l + (px - img.x) as f32 / img.w as f32 * (r - l)) * depth;
    let ey = |py: i32| (up - (py - img.y) as f32 / img.h as f32 * (up - dn)) * depth;
    let (x0, x1) = (ex(rect.x), ex(rect.x + rect.w));
    let (y0, y1) = (ey(rect.y), ey(rect.y + rect.h)); // y0 = oben
    let (cx, cy) = ((x0 + x1) * 0.5, (y0 + y1) * 0.5);
    let (w, h) = (x1 - x0, y0 - y1);

    let quad = |x: f32, y: f32, width: f32, height: f32| {
        let off = rotate(eye.orientation, [x, y, -depth]);
        EdgeQuad {
            pose: xr::Posef {
                orientation: eye.orientation, // schaut zum Auge
                position: xr::Vector3f {
                    x: eye.position.x + off[0],
                    y: eye.position.y + off[1],
                    z: eye.position.z + off[2],
                },
            },
            width,
            height,
        }
    };
    [
        quad(cx, y0, w + thickness, thickness), // oben
        quad(cx, y1, w + thickness, thickness), // unten
        quad(x0, cy, thickness, h + thickness), // links
        quad(x1, cy, thickness, h + thickness), // rechts
    ]
}

/// Der ganze Ausschnitt als EIN Quad (für das 🥽 Overlay): Mitte + Breite/Höhe
/// in Tiefe `depth` vor dem Auge – genau dort, wo man den Ausschnitt sieht.
pub fn rect_quad(eye: &xr::Posef, fov: &xr::Fovf, img: Rect, rect: Rect, depth: f32) -> EdgeQuad {
    let (l, r) = (fov.angle_left.tan(), fov.angle_right.tan());
    let (up, dn) = (fov.angle_up.tan(), fov.angle_down.tan());
    let ex = |px: i32| (l + (px - img.x) as f32 / img.w as f32 * (r - l)) * depth;
    let ey = |py: i32| (up - (py - img.y) as f32 / img.h as f32 * (up - dn)) * depth;
    let (x0, x1) = (ex(rect.x), ex(rect.x + rect.w));
    let (y0, y1) = (ey(rect.y), ey(rect.y + rect.h));
    let off = rotate(eye.orientation, [(x0 + x1) * 0.5, (y0 + y1) * 0.5, -depth]);
    EdgeQuad {
        pose: xr::Posef {
            orientation: eye.orientation,
            position: xr::Vector3f {
                x: eye.position.x + off[0],
                y: eye.position.y + off[1],
                z: eye.position.z + off[2],
            },
        },
        width: x1 - x0,
        height: y0 - y1,
    }
}

/// 📌 Pin: Wo ist ein fest in der Welt stehender Rahmen GERADE im Bild?
/// Der Rahmen = `rect` so wie von `eye0`/`fov0` aus in Tiefe `depth` gesehen. Seine 4 Ecken
/// werden ins aktuelle Auge projiziert → umschließendes Rechteck (aufs Bild begrenzt).
/// None = man schaut nicht hinein (Ecke hinter dem Kopf, weniger als die Hälfte im Bild, zu klein).
#[allow(clippy::too_many_arguments)]
pub fn world_rect(
    eye0: &xr::Posef,
    fov0: &xr::Fovf,
    img0: Rect,
    rect: Rect,
    depth: f32,
    eye: &xr::Posef,
    fov: &xr::Fovf,
    img: Rect,
) -> Option<Rect> {
    let (l, r) = (fov0.angle_left.tan(), fov0.angle_right.tan());
    let (up, dn) = (fov0.angle_up.tan(), fov0.angle_down.tan());
    let ex = |px: i32| (l + (px - img0.x) as f32 / img0.w as f32 * (r - l)) * depth;
    let ey = |py: i32| (up - (py - img0.y) as f32 / img0.h as f32 * (up - dn)) * depth;
    let (x0, x1) = (ex(rect.x), ex(rect.x + rect.w));
    let (y0, y1) = (ey(rect.y), ey(rect.y + rect.h));
    let (mut u0, mut v0, mut u1, mut v1) = (f32::MAX, f32::MAX, f32::MIN, f32::MIN);
    for (x, y) in [(x0, y0), (x1, y0), (x0, y1), (x1, y1)] {
        let off = rotate(eye0.orientation, [x, y, -depth]);
        let p = xr::Vector3f { x: eye0.position.x + off[0], y: eye0.position.y + off[1], z: eye0.position.z + off[2] };
        let pr = project(eye, fov, p)?;
        let (px, py) = (img.x as f32 + pr.u * img.w as f32, img.y as f32 + pr.v * img.h as f32);
        (u0, v0, u1, v1) = (u0.min(px), v0.min(py), u1.max(px), v1.max(py));
    }
    let full = (u1 - u0) * (v1 - v0);
    let (ix1, iy1) = ((img.x + img.w) as f32, (img.y + img.h) as f32);
    let (cx0, cy0) = (u0.clamp(img.x as f32, ix1), v0.clamp(img.y as f32, iy1));
    let (cx1, cy1) = (u1.clamp(img.x as f32, ix1), v1.clamp(img.y as f32, iy1));
    let seen = (cx1 - cx0) * (cy1 - cy0);
    if full <= 0.0 || seen < full * 0.5 {
        return None;
    }
    let out = Rect {
        x: cx0.floor() as i32,
        y: cy0.floor() as i32,
        w: (cx1.ceil() - cx0.floor()) as i32,
        h: (cy1.ceil() - cy0.floor()) as i32,
    };
    (out.w >= 32 && out.h >= 32).then_some(out)
}

/// Wie schräg ist der Kopf (Rollen um die Blickrichtung)? Radiant, + = Welt-Oben liegt im
/// Bild nach RECHTS gekippt (Kopf nach links geneigt). Senkrecht hoch/runter schauen → 0.
pub fn roll(q: xr::Quaternionf) -> f32 {
    let (r, u, f) = (rotate(q, [1.0, 0.0, 0.0]), rotate(q, [0.0, 1.0, 0.0]), rotate(q, [0.0, 0.0, -1.0]));
    if f[1].abs() > 0.94 {
        return 0.0;
    }
    r[1].atan2(u[1])
}

fn quat_mul(a: xr::Quaternionf, b: xr::Quaternionf) -> xr::Quaternionf {
    xr::Quaternionf {
        w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
        x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
        y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
        z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    }
}

/// 🥽 Overlay mit geradegerücktem Bild: Der Dienst hat das Live-Bild um `roll` gedreht (Text
/// waagerecht) – das Quad wird gleich weit zurückgedreht und um die gedrehte (größere)
/// Fläche vergrößert. So liegt der Text auch bei schrägem Kopf genau über dem Original.
pub fn rolled_quad(base: EdgeQuad, rect: Rect, roll: f32) -> EdgeQuad {
    if roll == 0.0 || rect.w <= 0 || rect.h <= 0 {
        return base;
    }
    let (mx, my) = (base.width / rect.w as f32, base.height / rect.h as f32);
    let (c, s) = (roll.cos().abs(), roll.sin().abs());
    let (w, h) = (rect.w as f32, rect.h as f32);
    let half = -roll * 0.5;
    let rot_z = xr::Quaternionf { x: 0.0, y: 0.0, z: half.sin(), w: half.cos() };
    EdgeQuad {
        pose: xr::Posef { orientation: quat_mul(base.pose.orientation, rot_z), position: base.pose.position },
        width: (w * c + h * s) * mx,
        height: (w * s + h * c) * my,
    }
}

/// Quadrat für das Typ-Symbol: INNEN in einer Ecke des Rahmens (`corner`).
/// `size` = Kantenlänge in Metern (in Tiefe `depth`), `gap` = Abstand zu den Linien.
#[allow(clippy::too_many_arguments)]
pub fn corner_quad(
    eye: &xr::Posef,
    fov: &xr::Fovf,
    img: Rect,
    rect: Rect,
    depth: f32,
    size: f32,
    gap: f32,
    corner: crate::config::IconPosition,
) -> EdgeQuad {
    let (l, r) = (fov.angle_left.tan(), fov.angle_right.tan());
    let (up, dn) = (fov.angle_up.tan(), fov.angle_down.tan());
    let ex = |px: i32| (l + (px - img.x) as f32 / img.w as f32 * (r - l)) * depth;
    let ey = |py: i32| (up - (py - img.y) as f32 / img.h as f32 * (up - dn)) * depth;
    let (x0, x1) = (ex(rect.x), ex(rect.x + rect.w)); // linker / rechter Rand
    let (y0, y1) = (ey(rect.y), ey(rect.y + rect.h)); // oberer / unterer Rand
    let d = gap + size * 0.5; // Mitte des Symbols: so weit von beiden Linien weg
    let x = if corner.is_left() { x0 + d } else { x1 - d };
    let y = if corner.is_top() { y0 - d } else { y1 + d };
    let off = rotate(eye.orientation, [x, y, -depth]);
    EdgeQuad {
        pose: xr::Posef {
            orientation: eye.orientation,
            position: xr::Vector3f {
                x: eye.position.x + off[0],
                y: eye.position.y + off[1],
                z: eye.position.z + off[2],
            },
        },
        width: size,
        height: size,
    }
}

/// "Mittelauge": Position genau zwischen beiden Augen, Blickrichtung vom
/// linken Auge. Damit passt der Ausschnitt zu dem, was man mit BEIDEN
/// Augen sieht – projiziert wird trotzdem ins Bild des linken Auges.
#[cfg(test)]
pub fn center_eye(left: &xr::Posef, right: &xr::Posef) -> xr::Posef {
    blend_eye(left, right, 0.5, left.orientation)
}

/// Blickpunkt zwischen den Augen: t = 0 → linkes Auge, t = 1 → rechtes Auge.
/// `orientation` = Blickrichtung des Auges, aus dessen Bild fotografiert wird.
pub fn blend_eye(left: &xr::Posef, right: &xr::Posef, t: f32, orientation: xr::Quaternionf) -> xr::Posef {
    let l = |a: f32, b: f32| a + (b - a) * t;
    xr::Posef {
        orientation,
        position: xr::Vector3f {
            x: l(left.position.x, right.position.x),
            y: l(left.position.y, right.position.y),
            z: l(left.position.z, right.position.z),
        },
    }
}

/// Punkt (im gleichen Space wie `eye`) → Bildkoordinate (x rechts, y unten).
/// `None`, wenn der Punkt hinter der Kamera liegt.
pub fn project(eye: &xr::Posef, fov: &xr::Fovf, p: xr::Vector3f) -> Option<Projected> {
    let d = [p.x - eye.position.x, p.y - eye.position.y, p.z - eye.position.z];
    let v = rotate_inv(eye.orientation, d);
    // OpenXR: Kamera schaut Richtung -Z
    if v[2] > -0.05 {
        return None;
    }
    let depth = -v[2];
    let tx = v[0] / depth;
    let ty = v[1] / depth;
    let (l, r) = (fov.angle_left.tan(), fov.angle_right.tan());
    let (u, dn) = (fov.angle_up.tan(), fov.angle_down.tan());
    Some(Projected { u: (tx - l) / (r - l), v: (u - ty) / (u - dn), depth })
}

/// 📐 Rechteck auf ein Seitenverhältnis (Breite/Höhe) bringen: so groß wie möglich
/// INNERHALB von x0..x1 / y0..y1, mittig – wie der Sucher einer Kamera.
fn fit_aspect((x0, y0, x1, y1): (f32, f32, f32, f32), ratio: f32) -> (f32, f32, f32, f32) {
    let (w, h) = (x1 - x0, y1 - y0);
    if w <= 0.0 || h <= 0.0 || ratio <= 0.0 {
        return (x0, y0, x1, y1);
    }
    let (cx, cy) = ((x0 + x1) * 0.5, (y0 + y1) * 0.5);
    let (w, h) = if w / h > ratio { (h * ratio, h) } else { (w, w / ratio) };
    (cx - w * 0.5, cy - h * 0.5, cx + w * 0.5, cy + h * 0.5)
}

/// Rechteck aus zwei Handpunkten, begrenzt auf das Bild `img`.
/// `inset_m`: so viele Meter rücken die Ecken nach innen.
/// `aspect`: festes Seitenverhältnis (Breite/Höhe), None = frei.
/// Zu klein oder ungültig → ganzes Bild.
pub fn crop_rect(
    img: Rect,
    fov: &xr::Fovf,
    a: Option<Projected>,
    b: Option<Projected>,
    inset_m: f32,
    aspect: Option<f32>,
) -> Rect {
    let (Some(a), Some(b)) = (a, b) else { return img };

    // Pixel pro Meter in Handentfernung (Brennweite / Tiefe)
    let focal_x = img.w as f32 / (fov.angle_right.tan() - fov.angle_left.tan());
    let focal_y = img.h as f32 / (fov.angle_up.tan() - fov.angle_down.tan());
    let to_px = |p: Projected| {
        (
            img.x as f32 + p.u * img.w as f32,
            img.y as f32 + p.v * img.h as f32,
            inset_m * focal_x / p.depth,
            inset_m * focal_y / p.depth,
        )
    };
    let (ax, ay, aix, aiy) = to_px(a);
    let (bx, by, bix, biy) = to_px(b);

    // Jede Ecke Richtung Mitte schieben
    let (mut x0, mut x1) = if ax < bx { (ax + aix, bx - bix) } else { (bx + bix, ax - aix) };
    let (mut y0, mut y1) = if ay < by { (ay + aiy, by - biy) } else { (by + biy, ay - aiy) };

    // Aufs Bild begrenzen
    let (ix0, iy0) = (img.x as f32, img.y as f32);
    let (ix1, iy1) = ((img.x + img.w) as f32, (img.y + img.h) as f32);
    x0 = x0.clamp(ix0, ix1);
    x1 = x1.clamp(ix0, ix1);
    y0 = y0.clamp(iy0, iy1);
    y1 = y1.clamp(iy0, iy1);
    if let Some(ratio) = aspect {
        (x0, y0, x1, y1) = fit_aspect((x0, y0, x1, y1), ratio);
    }

    let r = Rect {
        x: x0.floor() as i32,
        y: y0.floor() as i32,
        w: (x1.ceil() - x0.floor()) as i32,
        h: (y1.ceil() - y0.floor()) as i32,
    };
    if r.w < 32 || r.h < 32 {
        img
    } else {
        r
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::IconPosition;

    fn pose(x: f32) -> xr::Posef {
        xr::Posef {
            orientation: xr::Quaternionf { x: 0.0, y: 0.0, z: 0.0, w: 1.0 },
            position: xr::Vector3f { x, y: 0.0, z: 0.0 },
        }
    }
    fn fov() -> xr::Fovf {
        let a = std::f32::consts::FRAC_PI_4;
        xr::Fovf { angle_left: -a, angle_right: a, angle_up: a, angle_down: -a }
    }
    fn p(u: f32, v: f32, depth: f32) -> Option<Projected> {
        Some(Projected { u, v, depth })
    }

    #[test]
    fn center_is_middle() {
        let r = project(&pose(0.0), &fov(), xr::Vector3f { x: 0.0, y: 0.0, z: -1.0 }).unwrap();
        assert!((r.u - 0.5).abs() < 1e-5 && (r.v - 0.5).abs() < 1e-5 && (r.depth - 1.0).abs() < 1e-5);
    }

    #[test]
    fn up_left_is_top_left() {
        let r = project(&pose(0.0), &fov(), xr::Vector3f { x: -0.5, y: 0.5, z: -1.0 }).unwrap();
        assert!((r.u - 0.25).abs() < 1e-5 && (r.v - 0.25).abs() < 1e-5);
    }

    #[test]
    fn behind_is_none() {
        assert!(project(&pose(0.0), &fov(), xr::Vector3f { x: 0.0, y: 0.0, z: 1.0 }).is_none());
    }

    #[test]
    fn center_eye_removes_left_shift() {
        // Punkt genau vor der Nase: vom linken Auge (x=-0.032) aus rechts der Mitte,
        // vom Mittelauge aus genau in der Mitte
        let left = pose(-0.032);
        let right = pose(0.032);
        let pt = xr::Vector3f { x: 0.0, y: 0.0, z: -0.5 };
        let from_left = project(&left, &fov(), pt).unwrap();
        let from_center = project(&center_eye(&left, &right), &fov(), pt).unwrap();
        assert!(from_left.u > 0.52);
        assert!((from_center.u - 0.5).abs() < 1e-5);
    }

    #[test]
    fn blend_eye_ends_are_the_eyes() {
        let (l, r) = (pose(-0.032), pose(0.032));
        let q = l.orientation;
        assert!((blend_eye(&l, &r, 0.0, q).position.x + 0.032).abs() < 1e-6);
        assert!((blend_eye(&l, &r, 1.0, q).position.x - 0.032).abs() < 1e-6);
        assert!(blend_eye(&l, &r, 0.5, q).position.x.abs() < 1e-6);
    }

    #[test]
    fn rect_without_inset() {
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let r = crop_rect(img, &fov(), p(0.75, 0.25, 0.5), p(0.25, 0.75, 0.5), 0.0, None);
        assert_eq!(r, Rect { x: 250, y: 250, w: 500, h: 500 });
        assert_eq!(crop_rect(img, &fov(), None, p(0.1, 0.1, 0.5), 0.0, None), img);
    }

    #[test]
    fn inset_shrinks_rect() {
        // FOV 90° → Brennweite 500 px; 5 cm bei 0,5 m Tiefe = 50 px pro Seite
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let r = crop_rect(img, &fov(), p(0.75, 0.25, 0.5), p(0.25, 0.75, 0.5), 0.05, None);
        assert_eq!(r, Rect { x: 300, y: 300, w: 400, h: 400 });
    }

    #[test]
    fn edges_match_rect() {
        // FOV 90°, 1000 px: Ausschnitt 250..750 = tan -0,5..0,5 → bei 1 m Tiefe ±0,5 m
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let rect = Rect { x: 250, y: 250, w: 500, h: 500 };
        let q = edge_quads(&pose(0.0), &fov(), img, rect, 1.0, 0.01);
        assert!((q[0].pose.position.y - 0.5).abs() < 1e-5); // oben
        assert!((q[1].pose.position.y + 0.5).abs() < 1e-5); // unten
        assert!((q[2].pose.position.x + 0.5).abs() < 1e-5); // links
        assert!((q[3].pose.position.x - 0.5).abs() < 1e-5); // rechts
        assert!((q[0].width - 1.01).abs() < 1e-5 && (q[0].pose.position.z + 1.0).abs() < 1e-5);
    }

    #[test]
    fn edges_follow_head_rotation() {
        // Kopf 90° nach links gedreht (um Y): "vorne" ist jetzt -X
        let s = std::f32::consts::FRAC_1_SQRT_2;
        let eye = xr::Posef {
            orientation: xr::Quaternionf { x: 0.0, y: s, z: 0.0, w: s },
            position: xr::Vector3f { x: 0.0, y: 0.0, z: 0.0 },
        };
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let rect = Rect { x: 250, y: 250, w: 500, h: 500 };
        let q = edge_quads(&eye, &fov(), img, rect, 1.0, 0.01);
        assert!((q[0].pose.position.x + 1.0).abs() < 1e-4, "{:?}", q[0].pose.position);
    }

    #[test]
    fn corner_is_inside_bottom_right() {
        // Ausschnitt ±0,5 m bei 1 m Tiefe → Symbol 0,1 m, 0,02 m Abstand
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let rect = Rect { x: 250, y: 250, w: 500, h: 500 };
        let q = corner_quad(&pose(0.0), &fov(), img, rect, 1.0, 0.1, 0.02, IconPosition::BottomRight);
        assert!((q.pose.position.x - 0.43).abs() < 1e-5, "{:?}", q.pose.position);
        assert!((q.pose.position.y + 0.43).abs() < 1e-5);
        assert!((q.pose.position.z + 1.0).abs() < 1e-5);
        assert_eq!((q.width, q.height), (0.1, 0.1));
    }

    #[test]
    fn rect_quad_covers_the_crop() {
        // Ausschnitt rechts oben: x 500..900, y 100..300 von 1000 → bei ±45° und 1 m Tiefe
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let rect = Rect { x: 500, y: 100, w: 400, h: 200 };
        let q = rect_quad(&pose(0.0), &fov(), img, rect, 1.0);
        assert!((q.pose.position.x - 0.4).abs() < 1e-5, "{:?}", q.pose.position);
        assert!((q.pose.position.y - 0.6).abs() < 1e-5);
        assert!((q.pose.position.z + 1.0).abs() < 1e-5);
        assert!((q.width - 0.8).abs() < 1e-5 && (q.height - 0.4).abs() < 1e-5);
    }

    #[test]
    fn corner_follows_icon_position() {
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let rect = Rect { x: 250, y: 250, w: 500, h: 500 };
        let at = |c| {
            let q = corner_quad(&pose(0.0), &fov(), img, rect, 1.0, 0.1, 0.02, c);
            (q.pose.position.x, q.pose.position.y)
        };
        let near = |(x, y): (f32, f32), (ex, ey): (f32, f32)| (x - ex).abs() < 1e-5 && (y - ey).abs() < 1e-5;
        assert!(near(at(IconPosition::BottomLeft), (-0.43, -0.43)));
        assert!(near(at(IconPosition::TopLeft), (-0.43, 0.43)));
        assert!(near(at(IconPosition::TopRight), (0.43, 0.43)));
    }

    #[test]
    fn aspect_fits_inside_and_stays_centered() {
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        // Hände spannen 600 × 400 px auf (Mitte 500/500)
        let (a, b) = (p(0.2, 0.3, 0.5), p(0.8, 0.7, 0.5));
        // 1:1 → 400 × 400, mittig
        assert_eq!(crop_rect(img, &fov(), a, b, 0.0, Some(1.0)), Rect { x: 300, y: 300, w: 400, h: 400 });
        // 16:9 → volle Breite 600, Höhe 337,5
        let r = crop_rect(img, &fov(), a, b, 0.0, Some(16.0 / 9.0));
        assert_eq!((r.w, r.x), (600, 200));
        assert!((r.h - 338).abs() <= 1, "{r:?}");
        assert!(((r.y + r.h / 2) - 500).abs() <= 1);
        // hochkant aufgespannt → 16:9 nimmt die Breite, Höhe schrumpft
        let r = crop_rect(img, &fov(), p(0.4, 0.2, 0.5), p(0.6, 0.8, 0.5), 0.0, Some(16.0 / 9.0));
        assert_eq!(r.w, 200);
        assert!((r.h - 113).abs() <= 1, "{r:?}");
    }

    #[test]
    fn inset_too_big_gives_full_image() {
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let r = crop_rect(img, &fov(), p(0.52, 0.48, 0.5), p(0.48, 0.52, 0.5), 0.07, None);
        assert_eq!(r, img);
    }

    #[test]
    fn world_rect_same_view_is_same_rect() {
        let eye = xr::Posef {
            orientation: xr::Quaternionf { x: 0.0, y: 0.0, z: 0.0, w: 1.0 },
            position: xr::Vector3f { x: 0.0, y: 1.6, z: 0.0 },
        };
        let fov = xr::Fovf { angle_left: -0.8, angle_right: 0.8, angle_up: 0.8, angle_down: -0.8 };
        let img = Rect { x: 0, y: 0, w: 1000, h: 1000 };
        let rect = Rect { x: 300, y: 400, w: 200, h: 100 };
        let r = world_rect(&eye, &fov, img, rect, 0.6, &eye, &fov, img).unwrap();
        assert!((r.x - 300).abs() <= 1 && (r.y - 400).abs() <= 1 && (r.w - 200).abs() <= 2 && (r.h - 100).abs() <= 2, "{r:?}");
        // Kopf umgedreht → Rahmen hinter einem → None
        let back = xr::Posef { orientation: xr::Quaternionf { x: 0.0, y: 1.0, z: 0.0, w: 0.0 }, ..eye };
        assert!(world_rect(&eye, &fov, img, rect, 0.6, &back, &fov, img).is_none());
        // Kopf nach links gedreht → Rahmen wandert im Bild nach rechts
        let a = 0.2f32;
        let left = xr::Posef { orientation: xr::Quaternionf { x: 0.0, y: (a / 2.0).sin(), z: 0.0, w: (a / 2.0).cos() }, ..eye };
        let r2 = world_rect(&eye, &fov, img, rect, 0.6, &left, &fov, img).unwrap();
        assert!(r2.x > r.x, "{r2:?}");
    }

    #[test]
    fn roll_of_tilted_head() {
        let level = xr::Quaternionf { x: 0.0, y: 0.0, z: 0.0, w: 1.0 };
        assert!(roll(level).abs() < 1e-5);
        // Kopf nach links geneigt (gegen den Uhrzeigersinn um die Blickrichtung, +Z zum Betrachter)
        let a = 0.3f32;
        let left = xr::Quaternionf { x: 0.0, y: 0.0, z: (a / 2.0).sin(), w: (a / 2.0).cos() };
        assert!((roll(left) - a).abs() < 1e-4, "{}", roll(left));
        // Quad wird zurückgedreht → seine Oben-Richtung zeigt wieder nach Welt-Oben
        let base = EdgeQuad {
            pose: xr::Posef { orientation: left, position: xr::Vector3f { x: 0.0, y: 0.0, z: -1.0 } },
            width: 0.4,
            height: 0.2,
        };
        let q = rolled_quad(base, Rect { x: 0, y: 0, w: 400, h: 200 }, roll(left));
        let up = rotate(q.pose.orientation, [0.0, 1.0, 0.0]);
        assert!(up[0].abs() < 1e-4 && (up[1] - 1.0).abs() < 1e-4, "{up:?}");
        assert!(q.width > 0.4 && q.height > 0.2);
    }
}
