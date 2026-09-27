"""Schnelle Tests für die UI-Logik (ohne Fenster). Start: python3 -m pytest -q"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- Texte
def test_every_text_has_de_and_en():
    from core.i18n import TEXTS
    missing = [k for k, v in TEXTS.items() if not (v.get("de") and v.get("en"))]
    assert not missing, f"ohne de/en: {missing}"


def test_used_text_keys_exist():
    """Jeder tr("…")-Schlüssel im Code steht auch in i18n.py."""
    from core.i18n import TEXTS
    used = set()
    for py in (ROOT / "UI").rglob("*.py"):
        # nur ganze Schlüssel – tr("combo_" + c) wird erst zur Laufzeit zusammengesetzt
        used |= set(re.findall(r'\btr\("([a-z0-9_]+)"\s*[,)]', py.read_text(encoding="utf-8")))
    assert not used - set(TEXTS), f"fehlen in i18n.py: {sorted(used - set(TEXTS))}"


# ------------------------------------------------------ Namensschilder
@pytest.mark.parametrize("lines, expected", [
    (["dkw_cat", "Mýstico_o", "Minoric", "he/him", "lease to Drop"], False),
    (["xX_Fox_Xx", "she / they", "Trusted User", "[NOVA] Club Nova", "Mystic Fox"], False),
    (["Please do not touch", "the artwork"], True),
    (["このワールドへようこそ", "ルールを守ってください"], True),
    (["さくら", "猫丸"], False),
])
def test_nameplates_are_not_text(lines, expected):
    from core.tags import has_real_text
    assert has_real_text(lines) is expected


# --------------------------------------------------------- layer.json
def test_shutter_and_mode_button_never_equal(tmp_path, monkeypatch):
    from core import layer_config
    monkeypatch.setattr(layer_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(layer_config, "LAYER_FILE", tmp_path / "layer.json")
    cfg = layer_config.update("shutter", "left")   # Standard-Typ-Taste ist links
    assert cfg["shutter"] == "left" and cfg["mode_button"] != "left"
    cfg = layer_config.update("mode_button", "left")
    assert cfg["mode_button"] == "left" and cfg["shutter"] != "left"


# ------------------------------------------------------- WayVR-Knopf
def test_chat_button_is_replaced():
    from core import wayvr_theme
    xml = ('<div>\n<Button macro="button_style" _press="::OscSend /chatbox/input" _arg0="">\n'
           '  <sprite src="watch/chat.svg" />\n</Button>\n</div>')
    new, n = wayvr_theme.CHAT_BUTTON.subn(wayvr_theme.viewshot_button(Path("/x/open.sh")), xml)
    assert n == 1 and "::ShellExec '/x/open.sh'" in new and "OscSend" not in new


# ----------------------------------------------------------- Version
def test_version_everywhere_the_same():
    from core.version import VERSION
    cargo = (ROOT / "layer/Cargo.toml").read_text(encoding="utf-8")
    assert re.search(r'^version\s*=\s*"([^"]+)"', cargo, re.M).group(1) == VERSION
    pkgbuild = (ROOT / "packaging/aur/PKGBUILD").read_text(encoding="utf-8")
    assert re.search(r"^pkgver=(\S+)", pkgbuild, re.M).group(1) == VERSION.replace("-", "_")
