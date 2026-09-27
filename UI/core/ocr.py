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


def _model_params() -> dict:
    """Wo liegen die OCR-Modelle?

    RapidOCR lädt sie beim ersten Mal in seinen eigenen Paketordner. In der
    AppImage (oder einem System-Paket) ist der schreibgeschützt. Liegen dort
    schon Modelle (build_appimage.sh lädt sie vorab), passt alles – sonst
    nach ~/.cache/linuxvr-viewshot/ocr-models ausweichen.

    Der Ordner wird IMMER als Text übergeben: setzt RapidOCR ihn selbst, ist
    es ein Path-Objekt – und neuere omegaconf-Versionen brechen dann mit
    "Value 'PosixPath' is not a supported primitive type" ab."""
    import os
    from pathlib import Path

    import rapidocr
    models = Path(rapidocr.__file__).resolve().parent / "models"
    if not (os.access(models, os.W_OK) or any(models.glob("*.onnx"))):
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        models = cache / "linuxvr-viewshot" / "ocr-models"
        models.mkdir(parents=True, exist_ok=True)
    return {"Global.model_root_dir": str(models)}


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
            _engine = RapidOCR(params=_model_params())
        result = _engine(str(path))
    lines = [t.strip() for t in (getattr(result, "txts", None) or ()) if t and t.strip()]
    return "\n".join(lines)
