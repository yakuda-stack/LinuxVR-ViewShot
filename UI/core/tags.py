"""
core/tags.py – Bild-Erkennung: Ist im Foto Text zum Übersetzen, ein QR-Code
oder ist es ein normales Bild?

Tags pro Foto (mehrere möglich):
    "text"   📝  Text zum Übersetzen (Schild, Tafel, Chat …)
    "qr"     🔳  QR-Code
    "image"  🖼  normales Bild (weder Text noch QR)

Gemerkt in tags.json:
    { "ViewShot_….png": { "tags": ["text"], "manual": false } }
"manual": true = in der Galerie (Info) von Hand geändert → wird nie mehr
automatisch überschrieben.

VRChat-Namensschilder: Namen, Pronomen, Rang ("Trusted User") und Gruppen
sind auch Text – sollen aber NICHT als "Text zum Übersetzen" zählen.
Darum werden solche Zeilen vorher aussortiert (is_nameplate) und es zählt
nur, was danach noch nach echten Sätzen aussieht (has_real_text).
"""

import json
import logging
import queue
import re
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImageReader

from core import ocr, paths, qr, translation
from core.paths import CONFIG_DIR

TAGS_FILE = CONFIG_DIR / "tags.json"
ALL = ("text", "qr", "image")
ICONS = {"text": "📝", "qr": "🔳", "image": "🖼"}

_lock = threading.Lock()


# ----------------------------------------------------------------------
# Speichern / Laden
# ----------------------------------------------------------------------
def _load() -> dict:
    try:
        return json.loads(TAGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TAGS_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def get(photo: Path) -> dict | None:
    """{"tags": [...], "manual": bool} oder None (noch nicht erkannt)."""
    with _lock:
        return _load().get(photo.name)


def set_tags(photo: Path, tags: list[str], manual: bool) -> None:
    with _lock:
        data = _load()
        # automatisch erkannt, aber inzwischen von Hand geändert? → Hand gewinnt
        if not manual and data.get(photo.name, {}).get("manual"):
            return
        data[photo.name] = {"tags": [t for t in ALL if t in tags], "manual": manual}
        _save(data)


# ----------------------------------------------------------------------
# Namensschilder erkennen
# ----------------------------------------------------------------------
# he/him, she/her, they/them, er/ihm, sie/ihr, any/all … (auch "he / they")
PRONOUN = re.compile(
    r"^(he|him|his|she|her|they|them|it|its|any|all|xe|xem|ze|zir|fae|faer|"
    r"er|ihm|ihn|sie|ihr|es|dey|dem)(\s*/\s*[a-zäöü]+)+$", re.IGNORECASE)

# Vertrauens-Ränge unter dem Namen
RANKS = {"visitor", "new user", "user", "known user", "trusted user", "veteran user",
         "legendary user", "friend", "nuisance", "vrchat team", "moderator",
         "vrchat+", "supporter"}

WORD = re.compile(r"[^\W\d_]{2,}")  # ein "Wort" = mind. 2 Buchstaben am Stück
# Japanisch/Chinesisch/Koreanisch: keine Leerzeichen → Zeichen zählen statt Wörter
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def word_count(line: str) -> int:
    """Wörter in der Zeile – bei CJK zählen 2 Zeichen als ein Wort."""
    cjk = len(CJK.findall(line))
    latin = len(WORD.findall(CJK.sub(" ", line)))
    return latin + cjk // 2


def is_nameplate(line: str) -> bool:
    """True für Zeilen, die nach VRChat-Namensschild aussehen:
    Benutzername, Pronomen, Rang, kurzer Gruppenname."""
    text = line.strip()
    if not text:
        return True
    low = text.lower()
    # CJK-Satz (≥ 6 Zeichen) – Namen sind kürzer
    if len(CJK.findall(text)) >= 6:
        return False
    if low in RANKS or PRONOUN.match(text):
        return True
    words = text.split()
    # Benutzernamen sind EIN Wort (oft mit _ . Ziffern) – ein Wort allein
    # übersetzt man sowieso nicht
    if len(words) == 1:
        return True
    # Gruppen-Kürzel wie "[ABC]" / "『Group』" oder kaum echte Buchstaben
    if word_count(text) < 2:
        return True
    # 2 Wörter = typischer Name/Gruppenname ("Mystic Fox", "Club Nova")
    return len(words) <= 2


def has_real_text(lines: list[str]) -> bool:
    """Ist nach dem Aussortieren der Namensschilder noch "richtiger" Text übrig?
    Ja, wenn eine Zeile nach Satz aussieht (≥ 4 Wörter) oder zusammen
    mindestens 6 Wörter übrig sind."""
    rest = [line for line in lines if not is_nameplate(line)]
    counts = [word_count(line) for line in rest]
    return any(c >= 4 for c in counts) or sum(counts) >= 6


def vr_type(photo: Path) -> str | None:
    """Im manuellen Modus schreibt der Layer den in VR gewählten Typ ins PNG
    (Text-Chunk "ViewShot-Type"). None = nicht gesetzt (automatischer Modus)."""
    value = QImageReader(str(photo)).text("ViewShot-Type").strip()
    return value if value in ALL else None


def classify(photo: Path) -> list[str]:
    """Erkennt die Tags eines Fotos. BLOCKIERT (OCR ≈ 1–2 s) → nur im Thread!"""
    tags = []
    try:
        if ocr.available() and has_real_text(translation.ocr_text(photo).splitlines()):
            tags.append("text")
    except Exception as e:  # noqa: BLE001 – OCR kaputt? dann eben kein Text-Tag
        logging.warning("Tags/OCR %s: %s", photo.name, e)
    if qr.find_codes(photo):
        tags.append("qr")
    return tags or ["image"]


# ----------------------------------------------------------------------
# Hintergrund-Erkennung: arbeitet alle noch nicht erkannten Fotos ab
# ----------------------------------------------------------------------
class Tagger(QObject):
    """Ein Thread, eine Warteschlange – neueste Fotos zuerst.

        tagger = Tagger(parent)
        tagger.tagged.connect(...)    # (Foto-Pfad) – fertig erkannt
        tagger.scan(paths.list_photos())
    """

    tagged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = queue.Queue()
        self._pending = set()  # schon in der Warteschlange
        threading.Thread(target=self._work, daemon=True).start()

    def scan(self, photos: list[Path]) -> None:
        """Alle Fotos ohne Tags einreihen (Reihenfolge wie übergeben)."""
        with _lock:
            known = _load()
        for photo in photos:
            if photo.name not in known and photo not in self._pending:
                self._pending.add(photo)
                self._queue.put(photo)

    def redo(self, photo: Path) -> None:
        """Ein Foto neu erkennen lassen (Knopf in der Galerie)."""
        with _lock:
            data = _load()
            data.pop(photo.name, None)
            _save(data)
        self.scan([photo])

    def _work(self):  # Hintergrund – KEINE Widgets anfassen!
        while True:
            photo = self._queue.get()
            try:
                # frisch aus VR: warten, bis die Datei fertig geschrieben ist
                # (sonst: OCR findet nichts → falscher Tag bleibt hängen)
                for _ in range(40):                     # max. ~10 s
                    if not photo.is_file() or paths.photo_ready(photo):
                        break
                    time.sleep(0.25)
                if photo.is_file() and paths.photo_ready(photo):
                    chosen = vr_type(photo)
                    if chosen:
                        # in VR gewählt = wie von Hand → keine OCR nötig
                        set_tags(photo, [chosen], manual=True)
                    else:
                        set_tags(photo, classify(photo), manual=False)
                    self.tagged.emit(str(photo))
            except Exception as e:  # noqa: BLE001 – ein kaputtes Foto stoppt nicht alles
                logging.warning("Tags %s: %s", photo.name, e)
            finally:
                self._pending.discard(photo)
