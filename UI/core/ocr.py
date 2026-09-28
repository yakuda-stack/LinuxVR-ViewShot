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
import time
from pathlib import Path

INSTALL_HINT = "pip install rapidocr onnxruntime"

_engine = None
_lock = threading.Lock()  # RapidOCR ist nicht für parallele Aufrufe gedacht
# Vorrang: Die Übersetzung auf der Main-Seite (priority=True) darf nicht warten,
# bis die Bild-Erkennung im Hintergrund ALLE Fotos durch hat. Solange eine
# Vorrang-Anfrage wartet, lässt der Hintergrund dem Vortritt.
_turn = threading.Condition()
_priority_waiting = 0


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


def busy() -> bool:
    """Liest gerade jemand (z. B. die Bild-Erkennung im Hintergrund)?"""
    return _lock.locked()


def read_text(path, priority: bool = False) -> str:
    """Erkannter Text, eine Zeile pro Textblock ("" = kein Text gefunden).
    priority=True: für die Übersetzung – kommt vor der Hintergrund-Erkennung dran."""
    global _priority_waiting
    start = time.monotonic()
    with _turn:
        if priority:
            _priority_waiting += 1
        else:
            # Hintergrund: warten, bis keine Vorrang-Anfrage mehr ansteht
            _turn.wait_for(lambda: _priority_waiting == 0)
    try:
        text = _read(path, start)
        logging.info("OCR %s %s: %.1f s gesamt, %d Zeichen", "Main" if priority else "Hintergrund",
                     Path(str(path)).name, time.monotonic() - start, len(text))
        return text
    finally:
        if priority:
            with _turn:
                _priority_waiting -= 1
                _turn.notify_all()


def _read(path, start: float) -> str:
    global _engine
    with _lock:
        waited = time.monotonic() - start
        if waited > 1:
            logging.info("OCR: %.1f s auf die Texterkennung gewartet", waited)
        if _engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as e:
                raise OcrUnavailable(INSTALL_HINT) from e
            # RapidOCR schreibt sonst viele INFO-Zeilen ins Terminal
            logging.getLogger("RapidOCR").setLevel(logging.WARNING)
            t = time.monotonic()
            _engine = RapidOCR(params=_model_params())
            logging.info("OCR: Modell geladen in %.1f s", time.monotonic() - t)
        result = _engine(str(path))
    lines = [t.strip() for t in (getattr(result, "txts", None) or ()) if t and t.strip()]
    return "\n".join(lines)
