import json
import zipfile
from pathlib import Path

import pytest

from mc_i18n.errors import McI18nError
from mc_i18n.extract import extract, filename_has_file_id

ROOT = Path(__file__).resolve().parents[1]
JARS = ROOT / "fixtures" / "jars"
MANIFEST = ROOT / "fixtures" / "manifest.json"


def _write_jar(path: Path, files: dict[str, str | bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            payload = data.encode("utf-8") if isinstance(data, str) else data
            archive.writestr(name, payload)


def test_filename_file_id_ignores_short_version_numbers():
    assert filename_has_file_id("cozy-example-5550001.jar", "5550001")
    assert filename_has_file_id("mods/cozy-example-5550001.jar", "5550001")
    assert not filename_has_file_id("cozy-example-5550001.jar", "555")
    assert not filename_has_file_id("cozy-example-5550001.jar", "555000")
    assert not filename_has_file_id("forge-47.3.0.jar", "47")
    assert not filename_has_file_id("mod-1234567.jar", "123456")
    assert filename_has_file_id("mod-123456.jar", "123456")


def test_extract_fixture_worktree(tmp_path: Path):
    out = tmp_path / "work"
    index = extract(JARS, out, manifest_path=MANIFEST)

    assert [mod["modid"] for mod in index["mods"]] == [
        "bare_pot",
        "cozy_example",
        "fabric_snack",
        "kitchen",
    ]
    by_id = {mod["modid"]: mod for mod in index["mods"]}

    cozy = by_id["cozy_example"]
    assert cozy["jar"] == "cozy-example-5550001.jar"
    assert cozy["key_counts"] == {"en_us": 4, "zh_cn": 4, "zh_tw": 0}
    assert cozy["missing_in_zh_tw"] == [
        "block.cozy_example.oven",
        "item.cozy_example.broth",
        "item.cozy_example.note",
        "tooltip.cozy_example.quality",
    ]
    assert cozy["missing_in_zh_cn"] == []
    assert "lang_errors" not in cozy
    assert json.loads((out / "cozy_example" / "zh_tw.json").read_text(encoding="utf-8")) == {}

    kitchen = by_id["kitchen"]
    assert kitchen["key_counts"] == {"en_us": 3, "zh_cn": 3, "zh_tw": 2}
    assert kitchen["missing_in_zh_tw"] == ["item.kitchen.bowl"]
    assert kitchen["missing_in_zh_cn"] == []
    assert json.loads((out / "kitchen" / "en_us.json").read_text(encoding="utf-8"))["item.kitchen.spoon"] == (
        "Wooden Spoon"
    )
    assert json.loads((out / "kitchen" / "zh_tw.json").read_text(encoding="utf-8")) == {
        "block.kitchen.stove": "爐灶",
        "item.kitchen.spoon": "木匙",
    }

    fabric = by_id["fabric_snack"]
    assert fabric["missing_in_zh_cn"] == ["item.fabric_snack.tea"]
    assert fabric["missing_in_zh_tw"] == ["item.fabric_snack.bun", "item.fabric_snack.tea"]
    assert by_id["bare_pot"]["key_counts"] == {"en_us": 1, "zh_cn": 0, "zh_tw": 0}

    cozy_meta = json.loads((out / "cozy_example" / "meta.json").read_text(encoding="utf-8"))
    assert cozy_meta["loader"] == "forge"
    assert cozy_meta["name"] == "Cozy Example"
    assert cozy_meta["description"] == "A tiny oven and broth mod used to smoke-test Lunchtime localization."
    assert cozy_meta["version"] == "1.2.0"
    assert cozy_meta["authors"] == ["Lunchtime"]
    assert cozy_meta["license"] == "MIT"
    assert cozy_meta["url"] == "https://example.invalid/cozy"
    assert cozy_meta["pack_mcmeta_description"] == "Cozy example built-in resources"
    assert [mod["modid"] for mod in cozy_meta["declared_mods"]] == ["cozy_example", "kitchen"]

    kitchen_meta = json.loads((out / "kitchen" / "meta.json").read_text(encoding="utf-8"))
    assert kitchen_meta["name"] == "Kitchen"
    assert kitchen_meta["description"] == "Extra cooking blocks that ship a partial zh_tw."
    assert kitchen_meta["authors"] == ["Lunchtime", "Fixture"]

    fabric_meta = json.loads((out / "fabric_snack" / "meta.json").read_text(encoding="utf-8"))
    assert fabric_meta["loader"] == "fabric"
    assert fabric_meta["name"] == "Fabric Snack"
    assert fabric_meta["description"] == "A small Fabric-side snack used in the Lunchtime fixture."
    assert fabric_meta["url"] == "https://example.invalid/fabric-snack"
    assert fabric_meta["pack_mcmeta_description"] is None

    bare_meta = json.loads((out / "bare_pot" / "meta.json").read_text(encoding="utf-8"))
    assert bare_meta["loader"] is None
    assert bare_meta["name"] is None
    assert bare_meta["declared_mods"] == []

    manifest = index["manifest"]
    assert manifest["name"] == "Lunchtime Fixture"
    assert manifest["minecraft"] == "1.20.1"
    assert manifest["mod_loader"] == "forge-47.3.0"
    assert manifest["files"][0]["jars"] == ["cozy-example-5550001.jar"]
    assert manifest["files"][1]["jars"] == []
    assert manifest["jars_not_in_manifest"] == ["bare-pot.jar", "fabric-snack.jar"]
    assert index["errors"] == []
    assert index["jars_without_lang"] == []
    assert (out / "index.json").is_file()


def test_extract_replaces_stale_mods_and_refuses_unrelated_dirs(tmp_path: Path):
    jars = tmp_path / "jars"
    _write_jar(
        jars / "alpha.jar",
        {"assets/alpha/lang/en_us.json": '{"a": "A"}'},
    )
    _write_jar(
        jars / "beta.jar",
        {"assets/beta/lang/en_us.json": '{"b": "B"}'},
    )
    out = tmp_path / "work"
    extract(jars, out)
    assert (out / "beta").is_dir()

    only_alpha = tmp_path / "only"
    _write_jar(only_alpha / "alpha.jar", {"assets/alpha/lang/en_us.json": '{"a": "A2"}'})
    extract(only_alpha, out)
    assert not (out / "beta").exists()
    assert json.loads((out / "alpha" / "en_us.json").read_text(encoding="utf-8")) == {"a": "A2"}

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    (blocked / "notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(McI18nError):
        extract(only_alpha, blocked)
    assert (blocked / "notes.txt").is_file()
    extract(only_alpha, blocked, clean=True)
    assert not (blocked / "notes.txt").exists()
    assert (blocked / "alpha" / "meta.json").is_file()


def test_extract_records_bad_jars_unsafe_names_and_broken_toml(tmp_path: Path):
    jars = tmp_path / "jars"
    jars.mkdir()
    (jars / "broken.jar").write_bytes(b"not a jar")
    _write_jar(
        jars / "odd.jar",
        {
            "assets/../lang/en_us.json": '{"no": "pe"}',
            "assets/Foo/lang/en_us.json": '{"block.foo.one": "One"}',
            "assets/foo/lang/zh_cn.json": '{"block.foo.one": "一"}',
            "META-INF/mods.toml": "this is not toml [[[",
            "assets/kept/lang/en_us.json": '{"item.kept.cup": "Cup"}',
        },
    )
    nested = jars / "nested"
    _write_jar(nested / "deep.jar", {"assets/deep_pot/lang/en_us.json": '{"block.deep_pot.lid": "Lid"}'})

    out = tmp_path / "work"
    index = extract(jars, out, recursive=True)
    by_id = {mod["modid"]: mod for mod in index["mods"]}
    assert set(by_id) == {"foo", "kept", "deep_pot"}
    assert by_id["foo"]["key_counts"] == {"en_us": 1, "zh_cn": 1, "zh_tw": 0}
    assert json.loads((out / "foo" / "zh_cn.json").read_text(encoding="utf-8"))["block.foo.one"] == "一"
    reasons = {item["jar"]: item["reason"] for item in index["jars_without_lang"]}
    assert reasons["broken.jar"] == "not a zip"
    assert any(error["message"].startswith("skipped unsafe namespace") for error in index["errors"])
    assert any(error["path"].lower().endswith("mods.toml") for error in index["errors"])
    assert by_id["deep_pot"]["jar"] == "nested/deep.jar"

    single = tmp_path / "one.jar"
    _write_jar(single, {"assets/solo/lang/en_us.json": '{"a": "b"}'})
    solo_out = tmp_path / "solo"
    solo = extract(single, solo_out)
    assert solo["mods"][0]["modid"] == "solo"


def test_single_declared_mod_describes_a_different_namespace(tmp_path: Path):
    jars = tmp_path / "jars"
    _write_jar(
        jars / "lib.jar",
        {
            "META-INF/mods.toml": (
                'modLoader="javafml"\nloaderVersion="[47,)"\nlicense="MIT"\n'
                '[[mods]]\nmodId="real_mod"\ndisplayName="Real Mod"\n'
                'description="Shared library with a differently named asset namespace."\n'
                'version="9"\nauthors="Ada"\n'
            ),
            "assets/other_ns/lang/en_us.json": '{"block.other_ns.gear": "Gear"}',
        },
    )
    out = tmp_path / "work"
    extract(jars, out)
    meta = json.loads((out / "other_ns" / "meta.json").read_text(encoding="utf-8"))
    assert meta["name"] == "Real Mod"
    assert meta["loader"] == "forge"
    assert meta["description"] == "Shared library with a differently named asset namespace."
    assert meta["declared_mods"][0]["modid"] == "real_mod"
