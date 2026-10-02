import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "jev-questions"
sys.path.insert(0, str(ROOT))  # install.py
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "examples"))
