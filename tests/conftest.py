"""pytest: UI/ in den Suchpfad, damit "from core import …" klappt."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "UI"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
