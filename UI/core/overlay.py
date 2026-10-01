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
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath

from core import layer_config, paths

MAX_SIZE = 1024                  # längste Seite des Overlay-Bilds (Pixel)
BACKGROUND = QColor(30, 32, 40, 225)
TEXT = QColor(255, 255, 255)
LIVE = "live"                    # "ViewShot-For" im Lens-Modus


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
    """Größte Schrift, mit der `text` (umbrochen) in die Breite von `rect` passt und
    höchstens so hoch wird wie rect. Klappt das nicht: kleinste Schrift, Höhe wächst."""
    font = QFont()
    font.setBold(True)
    size = start
    flags = int(Qt.TextFlag.TextWordWrap)
    while True:
        font.setPixelSize(max(1, round(size)))
        need = QFontMetricsF(font).boundingRect(rect, flags, text)
        if need.height() <= rect.height() * 1.05 or size <= minimum:
            return font, need
        size *= 0.9


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
    for box, text in pairs:
        x0, y0, x1, y1 = (v * scale for v in box)
        line_h = max(8.0, y1 - y0)
        pad = max(3.0, line_h * 0.15)
        # etwas breiter erlauben – Übersetzungen sind oft länger als das Original
        width = min(img.width() - (x0 - pad), max(x1 - x0, line_h * 4) * 1.25 + 2 * pad)
        area = QRectF(x0 - pad, y0 - pad, width, (y1 - y0) + 2 * pad)
        text_area = area.adjusted(pad, pad * 0.5, -pad, -pad * 0.5)
        font, need = _fit_font(text, text_area, start=line_h * 0.8, minimum=max(9.0, img.height() / 40))
        # Kästchen an den Text anpassen (wächst nach unten, bleibt im Bild)
        area.setHeight(min(img.height() - area.top(), need.height() + pad * 1.5))
        path = QPainterPath()
        path.addRoundedRect(area, pad, pad)
        painter.fillPath(path, BACKGROUND)
        painter.setFont(font)
        painter.setPen(TEXT)
        painter.drawText(area.adjusted(pad, pad * 0.5, -pad, 0),
                         int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft), text)
    painter.end()
    return img


def write(for_name: str, size: tuple[int, int], lines: list[dict], translated: str) -> Path:
    """Overlay-Bild für ein Foto (Dateiname) bzw. LIVE schreiben. Erst in eine
    Hilfsdatei, dann umbenennen → der Layer liest nie ein halbes Bild."""
    img = render(size, lines, translated)
    img.setText("ViewShot-For", for_name)
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
