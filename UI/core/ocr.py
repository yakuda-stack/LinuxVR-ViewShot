"""
core/ocr.py – Text aus einem Foto lesen (RapidOCR, PP-OCRv6 – wie in VR-FrameCapture).

Optional: Ist RapidOCR nicht installiert, läuft der Rest der App trotzdem.
Installieren:   pip install rapidocr onnxruntime

Das Modell wird beim ersten Aufruf geladen (≈ 0,5 s) und dann behalten.
Aufrufe sind langsam (≈ 1–2 s) → nur im Hintergrund-Thread benutzen!
"""

import importlib.util
import logging
import threading

INSTALL_HINT = "pip install rapidocr onnxruntime"

_engine = None
_lock = threading.Lock()  # RapidOCR ist nicht für parallele Aufrufe gedacht


class OcrUnavailable(Exception):
    pass


def available() -> bool:
    """Ist RapidOCR installiert? (ohne es zu laden – das dauert)"""
    return importlib.util.find_spec("rapidocr") is not None


def read_text(path) -> str:
    """Erkannter Text, eine Zeile pro Textblock ("" = kein Text gefunden)."""
    global _engine
    with _lock:
        if _engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as e:
                raise OcrUnavailable(INSTALL_HINT) from e
            # RapidOCR schreibt sonst viele INFO-Zeilen ins Terminal
            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
            _engine = RapidOCR()
        result = _engine(str(path))
    lines = [t.strip() for t in (getattr(result, "txts", None) or ()) if t and t.strip()]
    return "\n".join(lines)
