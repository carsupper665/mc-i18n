import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart(session):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_fixture.py")], check=True, cwd=ROOT)
