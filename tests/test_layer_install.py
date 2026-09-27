"""Layer aus AppImage / AUR-Paket nach ~/.local kopieren (UI/core/layer_install.py).

Alles in einem Test-Ordner – das echte ~/.local wird nicht angefasst.
"""
import json

import pytest

ROOT_MANIFEST = "manifest/linuxvr_viewshot.json.in"


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Tut so, als liefe die App aus einem Paket: fertige .so + Vorlage da,
    kein scripts/-Ordner. ~/.local liegt im Test-Ordner."""
    from pathlib import Path

    from core import paths
    project = tmp_path / "usr/share/linuxvr-viewshot"
    (project / "manifest").mkdir(parents=True)
    template = Path(__file__).resolve().parent.parent / ROOT_MANIFEST
    (project / "manifest/linuxvr_viewshot.json.in").write_text(template.read_text())
    so = tmp_path / "usr/lib/linuxvr-viewshot" / paths.LAYER_NAME
    so.parent.mkdir(parents=True)
    so.write_bytes(b"\x7fELF-neu")

    home = tmp_path / "home"
    user_lib = home / ".local/lib/linuxvr-viewshot" / paths.LAYER_NAME
    monkeypatch.setattr(paths, "INSTALL_SCRIPT", project / "scripts/install-layer.sh")
    monkeypatch.setattr(paths, "APPIMAGE_LAYER", project / "lib" / paths.LAYER_NAME)
    monkeypatch.setattr(paths, "PACKAGE_LAYER", so)
    monkeypatch.setattr(paths, "MANIFEST_TEMPLATE", project / "manifest/linuxvr_viewshot.json.in")
    monkeypatch.setattr(paths, "USER_LIB", user_lib)
    monkeypatch.setattr(paths, "LAYER_VERSION_FILE", user_lib.parent / "VERSION")
    monkeypatch.setattr(paths, "MANIFEST", home / ".local/share/openxr/1/api_layers/implicit.d/x.json")
    monkeypatch.setattr(paths, "photo_dir", lambda: home / "Bilder/LinuxVR-ViewShot")
    return paths, so


def test_package_mode_copies_instead_of_building(fake):
    paths, _so = fake
    assert paths.mode() == "package"
    assert paths.copies_layer()
    assert not paths.layer_installed()


def test_install_writes_home_manifest(fake):
    from core import layer_install
    from core.version import VERSION
    paths, so = fake
    layer_install.install_bundled()
    assert paths.USER_LIB.read_bytes() == so.read_bytes()
    manifest = json.loads(paths.MANIFEST.read_text())
    # der Pfad zeigt nach ~/.local – NICHT nach /usr (Proton sieht /usr nicht)
    assert manifest["api_layer"]["library_path"] == str(paths.USER_LIB)
    assert layer_install.installed_version() == VERSION
    assert paths.layer_installed() and not layer_install.needs_update()


def test_update_after_new_version(fake):
    from core import layer_install
    paths, so = fake
    layer_install.install_bundled()
    paths.LAYER_VERSION_FILE.write_text("0.0.1\n")    # alte Version liegt in ~/.local
    so.write_bytes(b"\x7fELF-noch-neuer")
    assert layer_install.needs_update()
    layer_install.install_bundled()
    assert not layer_install.needs_update()
    assert paths.USER_LIB.read_bytes() == b"\x7fELF-noch-neuer"


def test_replace_keeps_running_game_safe(fake):
    """Ein laufendes Spiel hält die alte .so offen – die Datei wird ersetzt,
    nicht überschrieben (sonst würde das Spiel abstürzen)."""
    from core import layer_install
    paths, _so = fake
    layer_install.install_bundled()
    with open(paths.USER_LIB, "rb") as running:
        old_inode = paths.USER_LIB.stat().st_ino
        layer_install.install_bundled()
        assert running.read() == b"\x7fELF-neu"          # alte Datei noch lesbar
    assert paths.USER_LIB.stat().st_ino != old_inode       # neue Datei, kein Überschreiben


def test_remove_then_install_again(fake):
    from core import layer_install
    paths, _so = fake
    layer_install.install_bundled()
    paths.uninstall_user_layer()
    assert not paths.layer_installed() and not paths.USER_LIB.exists()
    layer_install.install_bundled()                        # geht danach wieder
    assert paths.layer_installed()
