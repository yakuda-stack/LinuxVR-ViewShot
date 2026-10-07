"""
core/overlay.py – Übersetzung als Bild für das VR-Overlay.

Die App malt über jede erkannte Textzeile ein graues Kästchen mit der
Übersetzung – der Rest des Bildes ist durchsichtig. Der Layer legt dieses Bild
in VR genau über den fotografierten Bereich:
    Foto → bleibt an der Stelle im Raum, wo fotografiert wurde
    🔁 Lens → im blauen Rahmen vor dem Kopf

Datei: <Foto-Ordner>/overlay/overlay.png  (PNG-Text "ViewShot-For" = Fotoname
oder "live" – so weiß der Layer, wo es hingehört). Später kann das der
Rust-Layer selbst zeichnen; bis dahin macht es Qt (kann Japanisch usw. schon).

Passt die Anzahl übersetzter Zeilen nicht zu den erkannten (z. B. KI-Antwort),
gibt es EIN großes Kästchen über dem ganzen Text.
"""

import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QTransform

from core import layer_config, paths

MAX_SIZE = 1024                  # längste Seite des Overlay-Bilds (Pixel)
BACKGROUND = QColor(30, 32, 40, 225)
TEXT = QColor(255, 255, 255)
LIVE = "live"                    # "ViewShot-For" im Lens-Modus
MIN_ROLL_DEG = 2.0               # darunter wird ein schräges Live-Bild nicht gedreht


def overlay_file() -> Path:
    return paths.photo_dir() / "overlay" / "overlay.png"


def pair_lines(lines: list[dict], translated: str) -> list[tuple[list, str]] | None:
    """Übersetzte Zeilen den erkannten Zeilen zuordnen → [(box, übersetzung)].
    None = Anzahl passt nicht (dann ein großes Kästchen)."""
    boxed = [line for line in lines if line.get("box")]
    tr_lines = [t.strip() for t in translated.splitlines() if t.strip()]
    if not boxed or len(tr_lines) != len(boxed) or len(boxed) != len(lines):
        return None
    return [(line["box"], t) for line, t in zip(boxed, tr_lines)]


def union_box(lines: list[dict], size: tuple[int, int]) -> list[int]:
    """Rechteck um alle Zeilen (ohne Positionen: das ganze Bild)."""
    boxes = [line["box"] for line in lines if line.get("box")]
    if not boxes:
        return [0, 0, size[0], size[1]]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _fit_font(text: str, rect: QRectF, start: float, minimum: float) -> tuple[QFont, QRectF]:
    """Größte Schrift, mit der `text` (umbrochen) in rect passt – Breite UND Höhe
    (lange deutsche Wörter!). Klappt das nicht: kleinste Schrift, Höhe wächst."""
    font = QFont()
    font.setBold(True)
    size = max(start, minimum)
    flags = int(Qt.TextFlag.TextWordWrap)
    while True:
        font.setPixelSize(max(1, round(size)))
        need = QFontMetricsF(font).boundingRect(rect, flags, text)
        fits = need.width() <= rect.width() * 1.02 and need.height() <= rect.height() * 1.05
        if fits or size <= minimum:
            return font, need
        size = max(minimum, size * 0.9)


def render(size: tuple[int, int], lines: list[dict], translated: str) -> QImage:
    """Durchsichtiges Bild in Fotogröße (max. MAX_SIZE) mit den Übersetzungs-Kästchen."""
    w, h = size
    scale = min(1.0, MAX_SIZE / max(w, h, 1))
    img = QImage(max(1, round(w * scale)), max(1, round(h * scale)), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    if not translated.strip():
        return img
    pairs = pair_lines(lines, translated)
    if pairs is None:  # ein großes Kästchen über dem ganzen Text
        pairs = [(union_box(lines, size), translated.strip())]
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    # kleinste Schrift: lieber klein als über den Rand / das halbe Bild zudecken
    minimum = max(7.0, img.height() / 90)
    for box, text in pairs:
        x0, y0, x1, y1 = (v * scale for v in box)
        line_h = max(8.0, y1 - y0)
        pad = min(8.0, max(2.0, line_h * 0.12))
        # Kästchen genau über dem Originaltext (nicht breiter) – zu langer Text → kleinere Schrift
        ax, ay = max(0.0, x0 - pad), max(0.0, y0 - pad)
        width = min(img.width() - ax, max(x1 - x0, line_h * 2) + 2 * pad)
        area = QRectF(ax, ay, width, min(img.height() - ay, (y1 - y0) + 2 * pad))
        text_area = area.adjusted(pad, pad * 0.5, -pad, -pad * 0.5)
        font, need = _fit_font(text, text_area, start=line_h * 0.8, minimum=minimum)
        # passt es selbst mit kleinster Schrift nicht: Kästchen wächst nach unten (bleibt im Bild)
        area.setHeight(min(img.height() - ay, max(area.height(), need.height() + pad)))
        path = QPainterPath()
        path.addRoundedRect(area, pad, pad)
        painter.fillPath(path, BACKGROUND)
        painter.setFont(font)
        painter.setPen(TEXT)
        top = ay + max(pad * 0.5, (area.height() - need.height()) / 2)  # senkrecht mittig
        painter.drawText(QRectF(ax + pad, top, width - 2 * pad, need.height() + 1),
                         int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft), text)
    painter.end()
    return img


def upright_snapshot(path: Path) -> tuple[Path, tuple[int, int], str, str]:
    """🔁 Lens / 📌 Pin: live.png EINMAL lesen (wird ständig neu geschrieben) → eigene Datei.
    War der Kopf schräg ("ViewShot-Roll" in Grad), wird das Bild gedreht, bis der Text
    waagerecht liegt (Fläche wächst, Ecken schwarz). → (Datei, Größe, Nummer, Drehung)"""
    img = QImage.fromData(Path(path).read_bytes(), "PNG")
    if img.isNull():
        raise OSError(f"Live-Bild nicht lesbar: {path}")
    seq = img.text("ViewShot-Seq")
    try:
        roll = float(img.text("ViewShot-Roll") or 0)
    except ValueError:
        roll = 0.0
    if abs(roll) >= MIN_ROLL_DEG:
        # Qt: positiver Winkel = im Uhrzeigersinn → minus = gegen den Uhrzeigersinn
        turned = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied).transformed(
            QTransform().rotate(-roll), Qt.TransformationMode.SmoothTransformation)
        img = QImage(turned.size(), QImage.Format.Format_RGB32)
        img.fill(Qt.GlobalColor.black)
        p = QPainter(img)
        p.drawImage(0, 0, turned)
        p.end()
    else:
        roll = 0.0
    snap = Path(tempfile.gettempdir()) / "linuxvr-viewshot-live-app.png"
    if not img.save(str(snap), "PNG"):
        raise OSError(f"Kann nicht speichern: {snap}")
    return snap, (img.width(), img.height()), seq, f"{roll:.2f}"


def write(for_name: str, size: tuple[int, int], lines: list[dict], translated: str, seq: str = "",
          roll: str = "") -> Path:
    """Overlay-Bild für ein Foto (Dateiname) bzw. LIVE schreiben. Erst in eine
    Hilfsdatei, dann umbenennen → der Layer liest nie ein halbes Bild.
    seq = Nummer des Live-Bilds ("ViewShot-Seq") → Layer legt es fest in die Welt.
    roll = so weit wurde das Bild geradegedreht (Grad) → Layer dreht das Quad zurück."""
    img = render(size, lines, translated)
    img.setText("ViewShot-For", for_name)
    if seq:
        img.setText("ViewShot-Seq", seq)
    if roll:
        img.setText("ViewShot-Roll", roll)
    target = overlay_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(".overlay.png.part")
    if not img.save(str(tmp), "PNG"):
        raise OSError(f"Overlay kann nicht gespeichert werden: {tmp}")
    os.replace(tmp, target)
    return target


def enabled() -> bool:
    """Optionen → Shot → „Übersetzung in VR über dem Original“."""
    return bool(layer_config.load().get("overlay", True))


def for_photo(photo: Path, translated: str) -> None:
    """Overlay fürs gerade übersetzte Foto schreiben. BLOCKIERT (evtl. OCR) → nur im Thread!"""
    if not enabled() or not translated.strip():
        return
    from PyQt6.QtGui import QImageReader

    from core import translation
    size = QImageReader(str(photo)).size()
    if size.isEmpty():
        return
    write(photo.name, (size.width(), size.height()), translation.ocr_lines(photo, priority=True), translated)


def clear() -> None:
    """Overlay weg (z. B. Overlay in den Optionen ausgeschaltet)."""
    try:
        overlay_file().unlink()
    except OSError:
        pass
