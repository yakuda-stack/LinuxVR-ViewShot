"""
ui/pages/main_live.py – Main-Seite: 🔁 Lens (Live-Übersetzung).

In VR: Typ-Taste bis 🔁, dann Auslöser. Der Layer fotografiert dann denselben
Bereich immer wieder und überschreibt live/live.png im Foto-Ordner (nicht in der
Galerie). Hier schauen wir jede Sekunde, ob das Bild neu ist → Text lesen → übersetzen.
Gleicher Text wie beim letzten Mal = nicht nochmal übersetzen (spart Zeit + Anfragen).

Lens aus = der Layer löscht live.png (neuer Rahmen). Stürzt das Spiel ab, kommen
einfach keine neuen Bilder mehr → nach einer Weile zurück zum normalen Foto.
"""

import threading
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QImageReader

from core import layer_config, ocr, overlay, paths, translation
from core import llm_translator as llm
from core.i18n import tr

LIVE_CHECK_MS = 1000  # so oft nach einem neuen Live-Bild schauen
STALE_MIN_S = 10      # so lange ohne neues Bild (mind.) → Lens gilt als beendet


def live_file() -> Path:
    return paths.photo_dir() / "live" / "live.png"


class LiveMixin:
    """Teil von MainPage (wird dort mit eingemischt).
    Braucht die Signale _live_done / _live_progress von MainPage."""

    def setup_live(self):
        self.live_mtime = self.live_file_mtime()  # altes Live-Bild von früher nicht zeigen
        self.live_shown = False      # zeigt die Seite gerade ein Live-Bild?
        self.live_busy = False       # liest/übersetzt gerade
        self.live_text = ""          # zuletzt erkannter Text …
        self.live_result = ("", "")  # … und seine Übersetzung (Text, Dienst)
        self.live_lines = []         # Zeilen mit Position (für die Nummern im 🪟 VR-Panel)
        self._live_done.connect(self.on_live_done)
        self._live_progress.connect(self.on_live_progress)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.check_live)
        self.live_timer.start(LIVE_CHECK_MS)

    @staticmethod
    def live_file_mtime() -> float:
        try:
            return live_file().stat().st_mtime
        except OSError:
            return 0.0  # (noch) kein Live-Bild

    def check_live(self):
        mtime = self.live_file_mtime()
        if self.live_shown and not self.live_busy:
            interval = float(layer_config.load().get("live_interval_s") or 3)
            gone = mtime == 0.0                                        # Layer hat Lens beendet
            stale = time.time() - mtime > max(3 * interval, STALE_MIN_S)  # Spiel zu / abgestürzt
            if gone or stale:
                self.stop_live_view()
                return
        if self.live_busy or self.translating is not None:
            return  # läuft noch / normales Foto wird gerade übersetzt – später
        if mtime <= self.live_mtime:
            return
        path = live_file()
        self.live_mtime = mtime
        self.live_shown = True
        self.live_busy = True
        self.photo_label.set_photo(path)
        self.photo_title.setText("🔁  " + tr("live_title"))
        cfg = translation.task_cfg(self.cfg)  # 🤖 Auto / gewählte Aufgabe
        last_text, last_result = self.live_text, self.live_result

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                lines = ocr.read_lines(path, priority=True)
                self.live_lines = lines
                text = "\n".join(line["text"] for line in lines)
                vision = cfg.get("tr_method") == llm.METHOD_VISION  # liest notfalls selbst
                if not text and not vision:
                    self._live_done.emit("", "", "", "")
                    return
                if text and text == last_text and last_result[0]:
                    translated, used = last_result  # schon übersetzt
                else:
                    translated, used = translation.translate_text_used(
                        text, cfg, progress=lambda step, arg="": self._live_progress.emit(step, arg),
                        image=path)
                self._live_done.emit(text, translated, "", used)
                # 🥽 in VR über den Text im blauen Rahmen legen (Positionen jedes Mal neu –
                # der Rahmen hängt am Kopf, der Text wandert also im Bild)
                if overlay.enabled():
                    size = QImageReader(str(path)).size()
                    overlay.write(overlay.LIVE, (size.width(), size.height()), lines, translated)
            except Exception as e:  # noqa: BLE001
                self._live_done.emit("", "", str(e), "")

        threading.Thread(target=work, daemon=True).start()

    def stop_live_view(self):
        """Lens beendet → wieder das normale (neueste) Foto zeigen."""
        self.live_shown = False
        self.live_text, self.live_result = "", ("", "")
        self.last_photo = None  # refresh() lädt Foto + Übersetzung neu
        self.refresh()

    def on_live_progress(self, step: str, arg: str):
        if step == "auto":
            self.auto_task = arg  # 🤖 so hat Auto entschieden (für „Letzte KI“)
        if step == "partial" and self.live_busy:
            self.tr_text.setPlainText(arg)  # KI schreibt noch

    def on_live_done(self, text: str, translated: str, error: str, used: str):
        self.live_busy = False
        if not self.live_shown:
            return
        now = datetime.now().strftime("%H:%M:%S")
        if error:
            self.tr_status.setText(f"🔁  {tr('tr_failed')}: {error}")
            return
        if not text and not translated:
            self.tr_status.setText(f"🔁  {tr('live_status')} · {now} · {tr('no_text')}")
            return
        if (text, translated) != (self.live_text, self.live_result[0]):  # neu gefragt
            self.set_last_ai(used, self.last_task(used))
        self.auto_task = ""
        self.live_text, self.live_result = text, (translated, used)
        self.history_entry = None
        self.show_translation(text, translated)
        self.tr_status.setText(f"🔁  {tr('live_status')} · {now}")
