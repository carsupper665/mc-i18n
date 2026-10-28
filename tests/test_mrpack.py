import json
import zipfile
from pathlib import Path

import pytest

from mc_i18n.errors import McI18nError
from mc_i18n.mrpack import _choose_file, resolve_dependency
from mc_i18n.pack import MrpackOptions, pack

I18N_FILE = {
    "filename": "I18nUpdateMod-3.7.0-all.jar",
    "primary": True,
    "size": 49726,
    "file_type": None,
    "hashes": {
        "sha1": "D9C217B569345AE30A5271BAA5E9482080C2E41D",
        "sha512": "ebfe770ef3e84e8ba83a9aecf5d29262720cc5c19b71a6f3727895407c52e1b1" + "4" * 64,
    },
    "url": "https://cdn.modrinth.com/data/PWERr14M/versions/4ihDUjWs/I18nUpdateMod-3.7.0-all.jar",
}
PACK_FILE = {
    "filename": "ModsTranslationPack-1.20.x.zip",
    "primary": True,
    "size": 2134122,
    "hashes": {"sha1": "a" * 40, "sha512": "b" * 128},
    "url": "https://cdn.modrinth.com/data/cF5VXmkW/versions/cYkaQUzr/ModsTranslationPack-1.20.x.zip",
}


def _projects():
    return {
        "i18nupdatemod": {
            "id": "PWERr14M",
            "slug": "i18nupdatemod",
            "project_type": "mod",
            "client_side": "required",
            "server_side": "unsupported",
        },
        "modstranslationpack": {
            "id": "cF5VXmkW",
            "slug": "modstranslationpack",
            "project_type": "resourcepack",
            "client_side": "required",
            "server_side": "unsupported",
        },
    }


def _versions():
    return {
        "4ihDUjWs": {
            "id": "4ihDUjWs",
            "project_id": "PWERr14M",
            "version_number": "3.7.0",
            "game_versions": ["1.20.1"],
            "loaders": ["forge", "fabric"],
            "files": [I18N_FILE],
        },
        "cYkaQUzr": {
            "id": "cYkaQUzr",
            "project_id": "cF5VXmkW",
            "version_number": "git-9898f04",
            "game_versions": ["1.20", "1.20.1"],
            "loaders": ["minecraft"],
            "files": [PACK_FILE],
        },
    }


def _fake_get(path: str):
    projects = _projects()
    versions = _versions()
    if path == "/v2/project/i18nupdatemod":
        return projects["i18nupdatemod"]
    if path == "/v2/project/modstranslationpack":
        return projects["modstranslationpack"]
    if path == "/v2/version/4ihDUjWs":
        return versions["4ihDUjWs"]
    if path == "/v2/version/cYkaQUzr":
        return versions["cYkaQUzr"]
    if path.startswith("/v2/project/i18nupdatemod/version"):
        return [versions["4ihDUjWs"]]
    if path.startswith("/v2/project/modstranslationpack/version"):
        return [versions["cYkaQUzr"]]
    raise AssertionError(path)


def test_choose_file_prefers_the_game_version_name():
    chosen = _choose_file(
        [
            {"filename": "A-sources.jar", "primary": False, "file_type": "source"},
            {"filename": "A-1.19.jar", "primary": True},
            {"filename": "A-1.20.1.jar", "primary": False},
        ],
        "1.20.1",
    )
    assert chosen["filename"] == "A-1.20.1.jar"


def test_pack_mrpack_records_modrinth_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("mc_i18n.mrpack.modrinth_get", _fake_get)
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "dist" / "Lunchtime-zh_tw.zip"
    mrpack = tmp_path / "dist" / "Lunchtime-zh_tw.mrpack"
    result = pack(
        work,
        out,
        mrpack=MrpackOptions(
            path=mrpack,
            mc_version="1.20.1",
            loader="forge",
            loader_version="47.3.0",
            name="Lunchtime zh_tw",
            deps=[("i18nupdatemod", "4ihDUjWs"), ("modstranslationpack", "cYkaQUzr")],
        ),
    )
    assert [item["path"] for item in result["resolved"]] == [
        "mods/I18nUpdateMod-3.7.0-all.jar",
        "resourcepacks/ModsTranslationPack-1.20.x.zip",
    ]
    with zipfile.ZipFile(mrpack) as zf:
        index = json.loads(zf.read("modrinth.index.json"))
    files = {item["path"]: item for item in index["files"]}
    mod = files["mods/I18nUpdateMod-3.7.0-all.jar"]
    assert mod["fileSize"] == 49726
    assert mod["hashes"]["sha1"] == "d9c217b569345ae30a5271baa5e9482080c2e41d"
    assert len(mod["hashes"]["sha512"]) == 128
    assert mod["downloads"] == [I18N_FILE["url"]]
    assert mod["env"] == {"client": "required", "server": "unsupported"}
    pack_file = files["resourcepacks/ModsTranslationPack-1.20.x.zip"]
    assert pack_file["downloads"] == [PACK_FILE["url"]]
    assert index["dependencies"]["minecraft"] == "1.20.1"
    assert index["dependencies"]["forge"] == "47.3.0"


def test_version_number_lookup_and_errors(monkeypatch):
    monkeypatch.setattr("mc_i18n.mrpack.modrinth_get", _fake_get)
    resolved = resolve_dependency("i18nupdatemod", "3.7.0", "1.20.1", "forge")
    assert resolved["version_id"] == "4ihDUjWs"
    assert resolved["path"].startswith("mods/")

    def missing(path: str):
        if path == "/v2/project/missing-pack":
            return None
        raise AssertionError(path)

    monkeypatch.setattr("mc_i18n.mrpack.modrinth_get", missing)
    with pytest.raises(McI18nError, match="not found"):
        resolve_dependency("missing-pack", "1.0.0", "1.20.1", "forge")

    def wrong_game(path: str):
        if path == "/v2/project/i18nupdatemod":
            return _projects()["i18nupdatemod"]
        if path.startswith("/v2/project/i18nupdatemod/version"):
            if "game_versions" in path:
                return []
            return [
                {
                    "id": "zzzzzzzz",
                    "project_id": "PWERr14M",
                    "version_number": "0.1.0",
                    "game_versions": ["1.19.2"],
                    "loaders": ["forge"],
                    "files": [I18N_FILE],
                }
            ]
        raise AssertionError(path)

    monkeypatch.setattr("mc_i18n.mrpack.modrinth_get", wrong_game)
    with pytest.raises(McI18nError, match="not published"):
        resolve_dependency("i18nupdatemod", "0.1.0", "1.20.1", "forge")


def test_duplicate_dependency_is_rejected(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(McI18nError, match="more than once"):
        pack(
            work,
            tmp_path / "out.zip",
            mrpack=MrpackOptions(
                path=tmp_path / "out.mrpack",
                deps=[("i18nupdatemod", "1"), ("i18nupdatemod", "2")],
            ),
        )
