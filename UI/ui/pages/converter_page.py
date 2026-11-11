"""
ui/pages/converter_page.py – 🔄 Converter / Compression.

🎬 Video → GIF: beliebiges Video wählen, Bilder/s, Größe und Länge einstellen,
   auf Wunsch gleich unter die Discord-Grenze bringen (core/convert.py, ffmpeg).
🗜 GIF komprimieren: ein oder mehrere GIFs auf eine Zielgröße bringen
   (core/gifshrink.py, macht der Rust-Dienst).

Beides läuft im Hintergrund-Thread – Ergebnisse kommen per Signal zurück.
"""

import threading
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QVBoxLayout, QWidget)

from core import config, convert, gifshrink, paths
from core.i18n import tr
from ui.widgets import make_card, open_path, page_title


class Signals(QObject):
    """Brücke vom Hintergrund-Thread zur UI (Widgets NUR im Haupt-Thread anfassen)."""
    converted = pyqtSignal(dict)
    convert_failed = pyqtSignal(str)
    shrink_progress = pyqtSignal(int, int)  # gerade Nummer i von n
    shrunk = pyqtSignal(dict)               # {"n", "old", "new", "small"}
    shrink_failed = pyqtSignal(str)


class ConverterPage(QWidget):
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.video: Path | None = None
        self.gifs: list[Path] = []
        self.signals = Signals()
        self.signals.converted.connect(self.on_converted)
        self.signals.convert_failed.connect(self.on_convert_failed)
        self.signals.shrink_progress.connect(self.on_shrink_progress)
        self.signals.shrunk.connect(self.on_shrunk)
        self.signals.shrink_failed.connect(self.on_shrink_failed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(page_title(tr("conv_title")))
        layout.addWidget(self.build_video_card())
        layout.addWidget(self.build_gif_card())

        foot = QHBoxLayout()
        hint = QLabel(tr("conv_hint"))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        foot.addWidget(hint, 1)
        folder_btn = QPushButton("📁  " + tr("open_folder"))
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_btn.clicked.connect(lambda: open_path(paths.convert_dir()))
        foot.addWidget(folder_btn)
        layout.addLayout(foot)
        layout.addStretch()
        self.sync_ffmpeg()

    # ------------------------------------------------------------------ 🎬 Video → GIF
    def build_video_card(self) -> QWidget:
        card, box = make_card(tr("conv_video_card"))
        row = QHBoxLayout()
        pick = QPushButton(tr("conv_pick_video"))
        pick.setCursor(Qt.CursorShape.PointingHandCursor)
        pick.clicked.connect(self.pick_video)
        row.addWidget(pick)
        self.video_label = QLabel(tr("conv_none"))
        self.video_label.setObjectName("dim")
        row.addWidget(self.video_label, 1)
        box.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.fps_combo = self.number_combo(convert.FPS_CHOICES, "conv_fps", "")
        grid.addWidget(QLabel(tr("conv_fps")), 0, 0)
        grid.addWidget(self.fps_combo, 0, 1)
        self.side_combo = self.number_combo(convert.SIDE_CHOICES, "conv_side", " px")
        grid.addWidget(QLabel(tr("conv_side")), 1, 0)
        grid.addWidget(self.side_combo, 1, 1)
        self.max_spin = QSpinBox()
        self.max_spin.setRange(1, 120)
        self.max_spin.setSuffix(" s")
        self.max_spin.setValue(int(self.cfg.get("conv_max_s", 15)))
        self.max_spin.valueChanged.connect(lambda v: self.save("conv_max_s", v))
        grid.addWidget(QLabel(tr("conv_max")), 2, 0)
        grid.addWidget(self.max_spin, 2, 1)
        grid.setColumnStretch(2, 1)
        box.addLayout(grid)

        row = QHBoxLayout()
        self.shrink_check = QCheckBox(tr("conv_shrink"))
        self.shrink_check.setChecked(bool(self.cfg.get("conv_shrink", True)))
        self.shrink_check.toggled.connect(lambda on: self.save("conv_shrink", on))
        row.addWidget(self.shrink_check)
        self.shrink_combo = self.number_combo(convert.TARGET_MB_CHOICES, "conv_target_mb", " MB")
        self.shrink_combo.setEnabled(self.shrink_check.isChecked())
        self.shrink_check.toggled.connect(self.shrink_combo.setEnabled)
        row.addWidget(self.shrink_combo)
        row.addStretch()
        box.addLayout(row)

        row = QHBoxLayout()
        self.convert_btn = QPushButton(tr("conv_start"))
        self.convert_btn.setObjectName("sendbtn")
        self.convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.convert_btn.setMinimumHeight(36)
        self.convert_btn.clicked.connect(self.start_convert)
        row.addWidget(self.convert_btn)
        self.convert_status = QLabel()
        self.convert_status.setWordWrap(True)
        self.convert_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.convert_status, 1)
        box.addLayout(row)
        return card

    def number_combo(self, choices, key: str, suffix: str) -> QComboBox:
        combo = QComboBox()
        for v in choices:
            combo.addItem(f"{v}{suffix}", v)
        i = combo.findData(int(self.cfg.get(key, choices[0])))
        combo.setCurrentIndex(max(i, 0))
        combo.currentIndexChanged.connect(lambda _: self.save(key, combo.currentData()))
        return combo

    def sync_ffmpeg(self):
        """Ohne ffmpeg geht nur 🗜 – Hinweis mit Installationsbefehl."""
        ok = convert.ffmpeg() is not None
        self.convert_btn.setEnabled(ok and self.video is not None)
        if not ok:
            self.convert_status.setText(tr("conv_no_ffmpeg"))

    def pick_video(self):
        patterns = " ".join("*" + e for e in convert.VIDEO_EXTS)
        file, _ = QFileDialog.getOpenFileName(self, tr("conv_pick_video"), str(paths.photo_dir()),
                                              f"{tr('conv_video_files')} ({patterns})")
        if not file:
            return
        self.video = Path(file)
        self.video_label.setText(self.video.name)
        self.convert_status.clear()
        self.sync_ffmpeg()

    def start_convert(self):
        if self.video is None or not self.video.is_file():
            return
        src = self.video
        fps, side = int(self.fps_combo.currentData()), int(self.side_combo.currentData())
        max_s = self.max_spin.value()
        shrink = int(self.shrink_combo.currentData()) if self.shrink_check.isChecked() else None
        self.convert_btn.setEnabled(False)
        self.convert_status.setText(tr("conv_busy"))

        def work():  # Hintergrund – KEINE Widgets anfassen!
            try:
                self.signals.converted.emit(convert.video_to_gif(src, fps, side, max_s, shrink))
            except Exception as e:  # noqa: BLE001
                self.signals.convert_failed.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_converted(self, res: dict):
        self.convert_status.setText(tr("conv_done", name=Path(res["path"]).name, mb=f"{res['size'] / 1e6:.1f}"))
        self.sync_ffmpeg()

    def on_convert_failed(self, error: str):
        if error == "ffmpeg":
            text = tr("conv_no_ffmpeg")
        elif error == "viewshot-daemon":
            text = tr("gif_no_tool")
        else:
            text = f"{tr('conv_failed')}: {error}"
        self.convert_status.setText(text)
        self.sync_ffmpeg()

    # ------------------------------------------------------------------ 🗜 GIF komprimieren
    def build_gif_card(self) -> QWidget:
        card, box = make_card(tr("conv_gif_card"))
        row = QHBoxLayout()
        pick = QPushButton(tr("conv_pick_gifs"))
        pick.setCursor(Qt.CursorShape.PointingHandCursor)
        pick.clicked.connect(self.pick_gifs)
        row.addWidget(pick)
        self.gifs_label = QLabel(tr("conv_no_gifs"))
        self.gifs_label.setObjectName("dim")
        self.gifs_label.setWordWrap(True)
        row.addWidget(self.gifs_label, 1)
        box.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.target_combo = self.number_combo(convert.TARGET_MB_CHOICES, "conv_target_mb", " MB")
        grid.addWidget(QLabel(tr("conv_target")), 0, 0)
        grid.addWidget(self.target_combo, 0, 1)
        grid.setColumnStretch(2, 1)
        box.addLayout(grid)
        self.backup_check = QCheckBox(tr("conv_backup"))
        self.backup_check.setChecked(bool(self.cfg.get("conv_backup", True)))
        self.backup_check.toggled.connect(lambda on: self.save("conv_backup", on))
        box.addWidget(self.backup_check)

        row = QHBoxLayout()
        self.compress_btn = QPushButton(tr("conv_compress_start"))
        self.compress_btn.setObjectName("sendbtn")
        self.compress_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.compress_btn.setMinimumHeight(36)
        self.compress_btn.setEnabled(False)
        self.compress_btn.clicked.connect(self.start_compress)
        row.addWidget(self.compress_btn)
        self.compress_status = QLabel()
        self.compress_status.setWordWrap(True)
        row.addWidget(self.compress_status, 1)
        box.addLayout(row)
        return card

    def pick_gifs(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("conv_pick_gifs"), str(paths.photo_dir()),
                                                f"{tr('conv_gif_files')} (*.gif)")
        if not files:
            return
        self.gifs = [Path(f) for f in files]
        names = ", ".join(p.name for p in self.gifs[:3]) + (" …" if len(self.gifs) > 3 else "")
        self.gifs_label.setText(tr("conv_gifs_chosen", n=len(self.gifs)) + ":  " + names)
        self.compress_status.clear()
        self.compress_btn.setEnabled(True)

    def start_compress(self):
        gifs = [g for g in self.gifs if g.is_file()]
        if not gifs:
            return
        if gifshrink.binary() is None:
            self.compress_status.setText(tr("gif_no_tool"))
            return
        target = convert.target_bytes(int(self.target_combo.currentData()))
        keep = self.backup_check.isChecked()
        self.compress_btn.setEnabled(False)

        def work():  # Hintergrund – KEINE Widgets anfassen!
            old = new = small = 0
            try:
                for i, gif in enumerate(gifs, 1):
                    self.signals.shrink_progress.emit(i, len(gifs))
                    size = gif.stat().st_size
                    if size <= target:
                        small += 1
                        continue
                    res = gifshrink.compress(gif, keep, target)
                    old, new = old + res["old"], new + res["new"]
                self.signals.shrunk.emit({"n": len(gifs) - small, "old": old, "new": new, "small": small})
            except Exception as e:  # noqa: BLE001
                self.signals.shrink_failed.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def on_shrink_progress(self, i: int, n: int):
        self.compress_status.setText(tr("conv_compress_busy", i=i, n=n))

    def on_shrunk(self, res: dict):
        parts = []
        if res["n"]:
            parts.append(tr("conv_compress_done", n=res["n"], old=f"{res['old'] / 1e6:.1f}",
                            new=f"{res['new'] / 1e6:.1f}"))
        if res["small"]:
            parts.append(tr("conv_already_small", n=res["small"]))
        self.compress_status.setText("  ·  ".join(parts))
        self.compress_btn.setEnabled(True)

    def on_shrink_failed(self, error: str):
        text = tr("gif_no_tool") if error == "viewshot-daemon" else f"{tr('gif_compress_failed')}: {error}"
        self.compress_status.setText(text)
        self.compress_btn.setEnabled(True)

    # ------------------------------------------------------------------
    def save(self, key: str, value):
        self.cfg[key] = value
        config.save(self.cfg)
