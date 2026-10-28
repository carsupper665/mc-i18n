"""Merge worktree langs into a Minecraft resource pack and optional mrpack."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mc_i18n.convert import convert_lang, open_converter
from mc_i18n.errors import McI18nError
from mc_i18n.extract import LANG_CODES, LANG_FILENAMES
from mc_i18n.langutil import (
    collect_strings,
    dump_json,
    load_lang_file,
    merge_lang,
    placeholder_counts,
    safe_modid,
)
from mc_i18n.mrpack import build_mrpack, print_warning, resolve_dependency
from mc_i18n.zipio import zip_bytes

DEFAULT_PACK_FORMAT = 15
DEFAULT_DESCRIPTION = "Traditional Chinese (zh_tw) translations"
DEFAULT_MC_VERSION = "1.20.1"


@dataclass
class MrpackOptions:
    path: Path
    mc_version: str = DEFAULT_MC_VERSION
    loader: str = "forge"
    loader_version: str | None = None
    name: str | None = None
    version_id: str = "1.0.0"
    summary: str | None = None
    deps: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ModSources:
    path: Path
    langs: dict[str, dict[str, Any]]
    overlay: dict[str, Any] = field(default_factory=dict)


def pack(
    work_dir: Path,
    out_zip: Path,
    translations_dir: Path | None = None,
    *,
    use_opencc: bool = False,
    pack_format: int = DEFAULT_PACK_FORMAT,
    description: str = DEFAULT_DESCRIPTION,
    mrpack: MrpackOptions | None = None,
) -> dict[str, Any]:
    if pack_format < 1:
        raise McI18nError("--pack-format must be a positive integer")
    if not work_dir.is_dir():
        raise McI18nError(f"Work directory not found: {work_dir}")
    if translations_dir is not None and not translations_dir.is_dir():
        raise McI18nError(f"Translations directory not found: {translations_dir}")
    if mrpack is not None:
        _reject_duplicate_deps(mrpack.deps)
        if out_zip.resolve() == mrpack.path.resolve():
            raise McI18nError("Resource pack --out and --mrpack must be different paths")

    converter = open_converter() if use_opencc else None
    sources = _collect_sources(work_dir, translations_dir)
    lang_files: list[tuple[str, bytes]] = []
    for modid in sorted(sources):
        _validate_overlay_placeholders(modid, sources[modid])
        merged = _merge_mod(sources[modid], converter)
        if not collect_strings(merged):
            continue
        arcname = f"assets/{modid}/lang/zh_tw.json"
        lang_files.append((arcname, dump_json(merged).encode("utf-8")))

    pack_mcmeta = {
        "pack": {
            "description": description,
            "pack_format": pack_format,
        }
    }
    files = [("pack.mcmeta", dump_json(pack_mcmeta).encode("utf-8")), *lang_files]
    payload = zip_bytes(files)

    resolved: list[dict[str, Any]] = []
    mrpack_bytes = None
    if mrpack is not None:
        if mrpack.loader_version is None:
            print_warning(
                "mrpack dependencies list Minecraft only. "
                "Pass --loader-version to pin the Forge (or other loader) version."
            )
        for slug, version in mrpack.deps:
            resolved.append(resolve_dependency(slug, version, mrpack.mc_version, mrpack.loader))
            item = resolved[-1]
            games = item.get("game_versions") or []
            if mrpack.mc_version not in games:
                print_warning(
                    f"{item['slug']} {item['version_id']} ({item['version_number']}) "
                    f"does not list Minecraft {mrpack.mc_version}. The mrpack still records that file."
                )
        pack_name = mrpack.name or out_zip.stem
        pack_summary = mrpack.summary or _default_summary(
            pack_name,
            mrpack.mc_version,
            mrpack.loader,
            mrpack.loader_version,
        )
        mrpack_bytes = build_mrpack(
            resource_pack_name=out_zip.name,
            resource_pack_bytes=payload,
            name=pack_name,
            version_id=mrpack.version_id,
            summary=pack_summary,
            mc_version=mrpack.mc_version,
            loader=mrpack.loader,
            loader_version=mrpack.loader_version,
            resolved=resolved,
        )

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    out_zip.write_bytes(payload)
    if mrpack is not None and mrpack_bytes is not None:
        mrpack.path.parent.mkdir(parents=True, exist_ok=True)
        mrpack.path.write_bytes(mrpack_bytes)

    return {
        "lang_files": [name for name, _data in lang_files],
        "resolved": [
            {
                "slug": item["slug"],
                "version_id": item["version_id"],
                "version_number": item["version_number"],
                "path": item["path"],
            }
            for item in resolved
        ],
    }


def format_pack_summary(result: dict[str, Any], out_zip: Path, mrpack_path: Path | None) -> str:
    lines = [f"packed {len(result['lang_files'])} lang files -> {out_zip}"]
    for item in result["resolved"]:
        lines.append(
            f"modrinth {item['slug']}@{item['version_number']} ({item['version_id']}) -> {item['path']}"
        )
    if mrpack_path is not None:
        lines.append(f"mrpack -> {mrpack_path} ({len(result['resolved'])} modrinth files)")
    return "\n".join(lines)


def _collect_sources(work_dir: Path, translations_dir: Path | None) -> dict[str, ModSources]:
    sources: dict[str, ModSources] = {}
    for child in work_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        modid = safe_modid(child.name)
        if modid is None:
            raise McI18nError(f"Work directory name is not a safe modid: {child.name}")
        if modid in sources:
            raise McI18nError(f"Modid collision between {sources[modid].path.name} and {child.name}")
        langs = {}
        for code in LANG_CODES:
            path = child / LANG_FILENAMES[code]
            langs[code] = load_lang_file(path) if path.is_file() else {}
        sources[modid] = ModSources(path=child, langs=langs)
    if translations_dir is None:
        return sources
    for child in translations_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        overlay_path = child / "zh_tw.json"
        if not overlay_path.is_file():
            continue
        modid = safe_modid(child.name)
        if modid is None:
            raise McI18nError(f"Translations directory name is not a safe modid: {child.name}")
        overlay = load_lang_file(overlay_path)
        slot = sources.setdefault(
            modid,
            ModSources(path=child, langs={code: {} for code in LANG_CODES}),
        )
        if slot.overlay:
            raise McI18nError(f"Modid collision in translations for {modid}")
        slot.overlay = overlay
    return sources


def _merge_mod(slot: ModSources, converter) -> dict[str, Any]:
    """Apply layers: existing zh_tw, then OpenCC(zh_cn), then the translator overlay."""
    merged = merge_lang({}, slot.langs.get("zh_tw") or {})
    if converter is not None:
        converted = convert_lang(slot.langs.get("zh_cn") or {}, converter)
        merged = merge_lang(merged, converted)
    if slot.overlay:
        merged = merge_lang(merged, slot.overlay)
    return merged


def _validate_overlay_placeholders(modid: str, slot: ModSources) -> None:
    english = collect_strings(slot.langs.get("en_us") or {})
    overlay = collect_strings(slot.overlay)
    for key in sorted(set(english) & set(overlay)):
        expected = placeholder_counts(english[key])
        actual = placeholder_counts(overlay[key])
        if expected != actual:
            raise McI18nError(
                f"{modid}.{key} placeholder mismatch: expected {dict(expected)}, got {dict(actual)}"
            )


def _default_summary(name: str, mc_version: str, loader: str, loader_version: str | None) -> str:
    loader_text = f"{loader} {loader_version}" if loader_version else loader
    return f"{name} resource pack for Minecraft {mc_version} ({loader_text})."


def _reject_duplicate_deps(deps: list[tuple[str, str]]) -> None:
    seen: dict[str, str] = {}
    for slug, version in deps:
        if slug in seen:
            raise McI18nError(
                f"Modrinth project {slug} was passed more than once ({seen[slug]} and {version})"
            )
        seen[slug] = version


def emit_summary(text: str) -> None:
    print(text, file=sys.stdout)
