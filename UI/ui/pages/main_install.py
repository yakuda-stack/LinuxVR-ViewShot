"""
ui/pages/main_install.py – Main-Seite: Layer bauen/installieren/entfernen
(Status-Knöpfe + Ausgabe des Skripts mit ✕).
"""

import os

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt
from PyQt6.QtWidgets import QMessageBox, QPushButton

from core import layer_install, paths
from core.i18n import tr
from core.version import VERSION
from ui.widgets import open_path


class InstallMixin:
    """Teil von MainPage (wird dort mit eingemischt) – braucht self.cfg, self.refresh() …"""

    def make_status_btn(self, text: str, slot, style: str = "linkbtn") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(style)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(40)
        btn.clicked.connect(slot)
        return btn

    def run_uninstall(self):
        """Layer aus ~/.local entfernen (vorher fragen). App + Fotos bleiben."""
        if self.process is not None:
            return
        box = QMessageBox(self)
        box.setWindowTitle(tr("uninstall"))
        box.setText(tr("uninstall_question"))
        yes = box.addButton(tr("yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(tr("no"), QMessageBox.ButtonRole.NoRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self.install_log.hide()
        try:
            paths.uninstall_user_layer()
            ok = True
        except OSError:
            ok = False
        self.install_result.setText(tr("uninstall_ok") if ok else tr("uninstall_failed"))
        self.install_result.setObjectName("ok" if ok else "bad")
        self.install_result.style().polish(self.install_result)
        self.install_result.show()
        self.install_panel.show()
        self.refresh()

    def open_folder(self):
        folder = paths.photo_dir()
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    # ------------------------------------------------------------------
    # Layer bauen + installieren (scripts/install-layer.sh)
    # ------------------------------------------------------------------
    def install_bundled(self, updated: bool = False):
        """AppImage: mitgelieferten Layer nach ~/.local kopieren (dauert < 1 s)."""
        self.install_log.hide()
        try:
            layer_install.install_bundled()
            ok = True
        except OSError:
            ok = False
        if not ok:
            text = tr("install_failed_copy")
        elif updated:
            text = tr("layer_updated", v=VERSION)
        else:
            text = tr("install_ok")
        self.install_result.setText(text)
        self.install_result.setObjectName("ok" if ok else "bad")
        self.install_result.style().polish(self.install_result)
        self.install_result.show()
        self.install_panel.show()
        self.refresh()

    def run_install(self):
        if self.process is not None:
            return
        if paths.copies_layer():
            self.install_bundled()
            return
        self.install_log.clear()
        self.install_log.show()
        self.install_panel.show()
        self.install_result.hide()
        self.install_btn.setEnabled(False)
        self.install_btn.setText("⏳  " + tr("installing"))

        # QProcess läuft im Hintergrund – die UI friert nicht ein
        self.process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        # rustup legt cargo nach ~/.cargo/bin – beim Start aus dem Menü fehlt das oft im PATH
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        env.insert("PATH", cargo_bin + ":" + env.value("PATH", "/usr/bin:/bin"))
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(paths.PROJECT_DIR))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_install_output)
        self.process.finished.connect(self.on_install_finished)
        self.process.start("bash", [str(paths.INSTALL_SCRIPT)])

    def on_install_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        self.install_log.insertPlainText(text)
        self.install_log.ensureCursorVisible()  # immer ans Ende scrollen

    def on_install_finished(self, exit_code: int, _status):
        ok = exit_code == 0
        self.install_result.setText(tr("install_ok") if ok else tr("install_failed"))
        self.install_result.setObjectName("ok" if ok else "bad")
        self.install_result.style().polish(self.install_result)
        self.install_result.show()
        self.install_panel.show()
        self.process = None
        self.refresh()
