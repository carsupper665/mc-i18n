import json
import zipfile
from pathlib import Path

import pytest

from mc_i18n.errors import McI18nError
from mc_i18n.extract import extract
from mc_i18n.pack import MrpackOptions, pack

ROOT = Path(__file__).resolve().parents[1]
JARS = ROOT / "fixtures" / "jars"
TRANSLATIONS = ROOT / "fixtures" / "translations"


def _read(archive: Path, name: str):
    with zipfile.ZipFile(archive) as zf:
        return json.loads(zf.read(name))


def _names(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as zf:
        return zf.namelist()


def _pack_fixture(tmp_path: Path, *, opencc: bool = False, translations: Path | None = TRANSLATIONS):
    work = tmp_path / "work"
    extract(JARS, work)
    out = tmp_path / "dist" / "Lunchtime-zh_tw.zip"
    mrpack = tmp_path / "dist" / "Lunchtime-zh_tw.mrpack"
    result = pack(
        work,
        out,
        translations,
        use_opencc=opencc,
        description="Lunchtime fixture zh_tw",
        mrpack=MrpackOptions(
            path=mrpack,
            mc_version="1.20.1",
            loader="forge",
            loader_version="47.3.0",
            name="Lunchtime zh_tw",
            version_id="1.0.0",
        ),
    )
    return work, out, mrpack, result


def test_pack_without_opencc_keeps_mod_zh_tw_and_overlay(tmp_path: Path):
    _work, out, mrpack, result = _pack_fixture(tmp_path)
    assert result["lang_files"] == [
        "assets/cozy_example/lang/zh_tw.json",
        "assets/kitchen/lang/zh_tw.json",
    ]
    names = _names(out)
    assert names[0] == "pack.mcmeta"
    assert all(name == "pack.mcmeta" or name.endswith("/lang/zh_tw.json") for name in names)
    meta = _read(out, "pack.mcmeta")
    assert meta["pack"]["pack_format"] == 15
    assert meta["pack"]["description"] == "Lunchtime fixture zh_tw"

    cozy = _read(out, "assets/cozy_example/lang/zh_tw.json")
    assert cozy == {"block.cozy_example.oven": "暖心烤箱"}
    kitchen = _read(out, "assets/kitchen/lang/zh_tw.json")
    assert kitchen == {
        "block.kitchen.stove": "爐灶",
        "item.kitchen.bowl": "飯碗",
        "item.kitchen.spoon": "木匙",
    }
    blob = out.read_bytes()
    assert "Cozy Oven".encode() not in blob
    assert "默认软件".encode() not in blob

    with zipfile.ZipFile(mrpack) as zf:
        assert zf.namelist() == [
            "modrinth.index.json",
            "overrides/resourcepacks/Lunchtime-zh_tw.zip",
        ]
        index = json.loads(zf.read("modrinth.index.json"))
        inner = zf.read("overrides/resourcepacks/Lunchtime-zh_tw.zip")
    assert index["formatVersion"] == 1
    assert index["game"] == "minecraft"
    assert index["versionId"] == "1.0.0"
    assert index["name"] == "Lunchtime zh_tw"
    assert index["files"] == []
    assert index["dependencies"] == {"forge": "47.3.0", "minecraft": "1.20.1"}
    assert inner == out.read_bytes()


def test_pack_opencc_layer_replaces_zh_tw_and_overlay_still_wins(tmp_path: Path):
    pytest.importorskip("opencc")
    _work, out, _mrpack, result = _pack_fixture(tmp_path, opencc=True)
    assert "assets/fabric_snack/lang/zh_tw.json" in result["lang_files"]
    assert "assets/bare_pot/lang/zh_tw.json" not in result["lang_files"]

    cozy = _read(out, "assets/cozy_example/lang/zh_tw.json")
    assert cozy == {
        "block.cozy_example.oven": "暖心烤箱",
        "item.cozy_example.broth": "蔬菜高湯",
        "item.cozy_example.note": "儲存 %1$s %% {count}",
        "tooltip.cozy_example.quality": "預設軟體",
    }
    kitchen = _read(out, "assets/kitchen/lang/zh_tw.json")
    assert kitchen["item.kitchen.spoon"] == "木勺"
    assert kitchen["item.kitchen.bowl"] == "飯碗"
    assert kitchen["block.kitchen.stove"] == "爐灶"
    assert _read(out, "assets/fabric_snack/lang/zh_tw.json") == {"item.fabric_snack.bun": "饅頭"}

    overlay = tmp_path / "translations"
    (overlay / "kitchen").mkdir(parents=True)
    (overlay / "kitchen" / "zh_tw.json").write_text(
        json.dumps({"item.kitchen.spoon": "自家木匙"}, ensure_ascii=False),
        encoding="utf-8",
    )
    custom = tmp_path / "custom.zip"
    pack(tmp_path / "work", custom, overlay, use_opencc=True)
    assert _read(custom, "assets/kitchen/lang/zh_tw.json")["item.kitchen.spoon"] == "自家木匙"


def test_overlay_for_unknown_modid_is_packed(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    translations = tmp_path / "translations" / "extra_pot"
    translations.mkdir(parents=True)
    (translations / "zh_tw.json").write_text('{"block.extra_pot.lid": "鍋蓋"}\n', encoding="utf-8")
    out = tmp_path / "extra.zip"
    result = pack(work, out, tmp_path / "translations", pack_format=18, description="extra")
    assert result["lang_files"] == ["assets/extra_pot/lang/zh_tw.json"]
    assert _read(out, "pack.mcmeta")["pack"]["pack_format"] == 18
    assert _read(out, "assets/extra_pot/lang/zh_tw.json") == {"block.extra_pot.lid": "鍋蓋"}


def test_overlay_must_preserve_source_placeholders(tmp_path: Path):
    work = tmp_path / "work" / "demo"
    work.mkdir(parents=True)
    (work / "en_us.json").write_text(
        '{"demo.message": "Hello %1$s %% {count}"}\n', encoding="utf-8"
    )
    translations = tmp_path / "translations" / "demo"
    translations.mkdir(parents=True)
    (translations / "zh_tw.json").write_text('{"demo.message": "你好"}\n', encoding="utf-8")

    with pytest.raises(McI18nError, match=r"demo\.message.*placeholder"):
        pack(tmp_path / "work", tmp_path / "out.zip", tmp_path / "translations")
