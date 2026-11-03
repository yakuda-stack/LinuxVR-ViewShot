"""pytest: UI/ in den Suchpfad, damit "from core import …" klappt."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "UI"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Eigene Einstellungen für die Tests: Sie dürfen ui.json & Co. des Nutzers weder lesen noch ändern
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="viewshot-tests-")


@pytest.fixture(autouse=True)
def no_update_check(monkeypatch):
    """Tests fragen GitHub nicht nach der neuesten Version."""
    from core import app_update
    monkeypatch.setattr(app_update, "fetch_latest", lambda: "")
