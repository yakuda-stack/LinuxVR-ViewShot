"""
core/qr.py – QR-Codes in einem Foto finden (OpenCV).

OpenCV kommt mit RapidOCR mit (opencv-python). Fehlt es, liefert
find_codes() einfach nichts – der Rest der App läuft trotzdem.

Aufrufe dauern bei großen Fotos ≈ 0,1–1 s → im Hintergrund-Thread benutzen.
"""

import importlib.util
import logging


def available() -> bool:
    return importlib.util.find_spec("cv2") is not None


def find_codes(path) -> list[str]:
    """Inhalt aller QR-Codes im Bild (ohne Doppelte, in Fundreihenfolge)."""
    if not available():
        return []
    import cv2
    import numpy as np

    # np.fromfile + imdecode statt imread: klappt auch mit Umlauten im Pfad
    try:
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    except (OSError, ValueError):
        return []
    if image is None:
        return []

    found = []
    # In VR sind QR-Codes oft klein → zur Not auf doppelte Größe hochrechnen.
    # Zwei Erkenner: der normale und der "Aruco"-Erkenner (findet schräge Codes besser).
    for scale in (1, 2):
        img = image if scale == 1 else cv2.resize(image, None, fx=2, fy=2,
                                                  interpolation=cv2.INTER_CUBIC)
        for make in (cv2.QRCodeDetector, getattr(cv2, "QRCodeDetectorAruco", None)):
            if make is None:
                continue
            try:
                ok, texts, _points, _ = make().detectAndDecodeMulti(img)
            except cv2.error as e:
                logging.debug("QR: %s", e)
                continue
            if ok:
                for text in texts:
                    if text and text not in found:
                        found.append(text)
        if found:
            break  # schon was gefunden → nicht noch langsam hochrechnen
    return found


def is_link(text: str) -> bool:
    return text.lower().startswith(("http://", "https://", "www."))
