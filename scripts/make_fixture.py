#!/usr/bin/env python3
"""Rebuild fixtures/jars/*.jar from the readable trees in fixtures/src/."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "fixtures" / "src"
OUT = ROOT / "fixtures" / "jars"


def main() -> None:
    if not SRC.is_dir():
        raise SystemExit(f"missing fixture sources: {SRC}")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.jar"):
        old.unlink()
    folders = sorted(path for path in SRC.iterdir() if path.is_dir())
    if not folders:
        raise SystemExit(f"no fixture mods in {SRC}")
    for folder in folders:
        dest = OUT / f"{folder.name}.jar"
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            files = [path for path in folder.rglob("*") if path.is_file()]
            for path in sorted(files):
                archive.write(path, path.relative_to(folder).as_posix())
        print(dest.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
