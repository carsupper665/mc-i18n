import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from mc_i18n.cli import main

ROOT = Path(__file__).resolve().parents[1]
JARS = ROOT / "fixtures" / "jars"
MANIFEST = ROOT / "fixtures" / "manifest.json"
TRANSLATIONS = ROOT / "fixtures" / "translations"


def test_help_and_missing_args():
    completed = subprocess.run(
        [sys.executable, "-m", "mc_i18n", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "extract" in completed.stdout
    assert "pack" in completed.stdout
    with pytest.raises(SystemExit) as exc:
        main(["extract"])
    assert exc.value.code == 2


def test_module_extract_and_pack(tmp_path: Path):
    work = tmp_path / "work"
    out = tmp_path / "dist" / "Lunchtime-zh_tw.zip"
    mrpack = tmp_path / "dist" / "Lunchtime-zh_tw.mrpack"
    assert (
        main(
            [
                "extract",
                "--jars",
                str(JARS),
                "--manifest",
                str(MANIFEST),
                "--out",
                str(work),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "pack",
                "--work",
                str(work),
                "--translations",
                str(TRANSLATIONS),
                "--out",
                str(out),
                "--description",
                "Lunchtime fixture zh_tw",
                "--mrpack",
                str(mrpack),
                "--mc-version",
                "1.20.1",
                "--loader",
                "forge",
                "--loader-version",
                "47.3.0",
                "--name",
                "Lunchtime zh_tw",
            ]
        )
        == 0
    )
    with zipfile.ZipFile(out) as zf:
        kitchen = json.loads(zf.read("assets/kitchen/lang/zh_tw.json"))
    assert kitchen["item.kitchen.spoon"] == "木匙"
    with zipfile.ZipFile(mrpack) as zf:
        index = json.loads(zf.read("modrinth.index.json"))
    assert index["formatVersion"] == 1
    assert index["dependencies"]["minecraft"] == "1.20.1"


def test_opencc_missing_tells_you_the_package(monkeypatch, tmp_path: Path):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "opencc" or name.startswith("opencc."):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "opencc", raising=False)
    monkeypatch.setattr("builtins.__import__", blocked)
    work = tmp_path / "work"
    work.mkdir()
    code = main(
        [
            "pack",
            "--work",
            str(work),
            "--out",
            str(tmp_path / "out.zip"),
            "--opencc",
        ]
    )
    assert code == 1
