#!/usr/bin/env python3
"""Check the fixture worktree, resource pack, and mrpack produced by smoke.sh."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--mrpack", type=Path, required=True)
    parser.add_argument("--opencc-zip", type=Path)
    parser.add_argument("--loader-version", default="47.3.0")
    parser.add_argument("--description", default="Lunchtime fixture zh_tw")
    args = parser.parse_args()

    index = json.loads((args.work / "index.json").read_text(encoding="utf-8"))
    by_id = {mod["modid"]: mod for mod in index["mods"]}
    expect_mods = ["bare_pot", "cozy_example", "fabric_snack", "kitchen"]
    if list(by_id) != expect_mods:
        fail(f"mod list {list(by_id)} != {expect_mods}")
    if by_id["kitchen"]["missing_in_zh_tw"] != ["item.kitchen.bowl"]:
        fail("kitchen missing_in_zh_tw")
    if by_id["cozy_example"]["key_counts"]["zh_tw"] != 0:
        fail("cozy_example should not ship zh_tw")
    cozy_meta = json.loads((args.work / "cozy_example" / "meta.json").read_text(encoding="utf-8"))
    if "oven" not in cozy_meta["description"]:
        fail("cozy_example description missing")
    fabric_meta = json.loads((args.work / "fabric_snack" / "meta.json").read_text(encoding="utf-8"))
    if fabric_meta["loader"] != "fabric":
        fail("fabric_snack loader")
    if json.loads((args.work / "cozy_example" / "zh_tw.json").read_text(encoding="utf-8")) != {}:
        fail("missing zh_tw should be an empty object")

    with zipfile.ZipFile(args.zip) as zf:
        meta = json.loads(zf.read("pack.mcmeta"))
        names = zf.namelist()
        kitchen = json.loads(zf.read("assets/kitchen/lang/zh_tw.json"))
        cozy = json.loads(zf.read("assets/cozy_example/lang/zh_tw.json"))
    if meta["pack"]["pack_format"] != 15 or meta["pack"]["description"] != args.description:
        fail(f"pack.mcmeta {meta}")
    if any(name.endswith("en_us.json") or name.endswith("zh_cn.json") for name in names):
        fail(f"resource pack contains source langs: {names}")
    if "assets/fabric_snack/lang/zh_tw.json" in names or "assets/bare_pot/lang/zh_tw.json" in names:
        fail("untranslated namespaces were packed")
    if kitchen.get("item.kitchen.spoon") != "木匙" or kitchen.get("item.kitchen.bowl") != "飯碗":
        fail(f"kitchen merge {kitchen}")
    if cozy != {"block.cozy_example.oven": "暖心烤箱"}:
        fail(f"cozy merge {cozy}")

    with zipfile.ZipFile(args.mrpack) as zf:
        mr_index = json.loads(zf.read("modrinth.index.json"))
        inner_name = "overrides/resourcepacks/" + args.zip.name
        inner = zf.read(inner_name)
    if mr_index.get("formatVersion") != 1 or mr_index.get("game") != "minecraft":
        fail(f"mrpack index {mr_index}")
    deps = mr_index.get("dependencies") or {}
    if deps.get("minecraft") != "1.20.1" or deps.get("forge") != args.loader_version:
        fail(f"dependencies {deps}")
    if inner != args.zip.read_bytes():
        fail("mrpack resource pack bytes differ from --zip")

    if args.opencc_zip:
        with zipfile.ZipFile(args.opencc_zip) as zf:
            cozy_tw = json.loads(zf.read("assets/cozy_example/lang/zh_tw.json"))
            kitchen_tw = json.loads(zf.read("assets/kitchen/lang/zh_tw.json"))
            fabric = json.loads(zf.read("assets/fabric_snack/lang/zh_tw.json"))
            opencc_names = zf.namelist()
        if "assets/bare_pot/lang/zh_tw.json" in opencc_names:
            fail("opencc packed an english-only namespace")
        if cozy_tw.get("block.cozy_example.oven") != "暖心烤箱":
            fail("overlay lost to opencc")
        if cozy_tw.get("tooltip.cozy_example.quality") != "預設軟體":
            fail(f"expected s2twp phrase conversion, got {cozy_tw}")
        if cozy_tw.get("item.cozy_example.note") != "儲存 %1$s %% {count}":
            fail(f"placeholder conversion {cozy_tw.get('item.cozy_example.note')}")
        if kitchen_tw.get("item.kitchen.spoon") != "木勺":
            fail("opencc did not replace existing zh_tw")
        if fabric != {"item.fabric_snack.bun": "饅頭"}:
            fail(f"fabric conversion {fabric}")
    print("fixture ok")
    return 0


def fail(message: str) -> None:
    print(f"verify failed: {message}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
