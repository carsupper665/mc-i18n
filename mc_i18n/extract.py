"""Pull en_us / zh_cn / zh_tw lang files and mod descriptions out of jars."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mc_i18n import __version__
from mc_i18n.errors import McI18nError
from mc_i18n.langutil import collect_strings, dump_json, load_json_file, load_lang_bytes, merge_lang, safe_modid
from mc_i18n.metadata import (
    build_mod_meta,
    combine_jar_meta,
    decode_json_object,
    empty_jar_meta,
    parse_fabric_mod,
    parse_mods_toml,
    parse_pack_mcmeta,
)

LANG_CODES = ("en_us", "zh_cn", "zh_tw")
LANG_FILENAMES = {code: f"{code}.json" for code in LANG_CODES}
_LANG_PATH = re.compile(
    r"^assets/(?P<ns>[^/]+)/lang/(?P<lang>en_us|zh_cn|zh_tw)\.json$",
    re.IGNORECASE,
)
_METADATA_NAMES = {
    "meta-inf/neoforge.mods.toml": "neoforge",
    "meta-inf/mods.toml": "forge",
    "fabric.mod.json": "fabric",
    "quilt.mod.json": "quilt",
}
_PACK_MCMETA = "pack.mcmeta"
# CurseForge file IDs are long. Short numbers collide with version tokens like 47.3.0.
_MIN_FILE_ID_DIGITS = 6
_MAX_ENTRY_BYTES = 20 * 1024 * 1024
_MARKERS = set(LANG_FILENAMES.values()) | {"meta.json"}


@dataclass
class NamespacePayload:
    langs: dict[str, dict[str, Any]] = field(default_factory=dict)
    lang_errors: dict[str, str] = field(default_factory=dict)


@dataclass
class JarReport:
    label: str
    namespaces: dict[str, NamespacePayload] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=empty_jar_meta)
    errors: list[dict[str, str]] = field(default_factory=list)
    without_lang_reason: str | None = None


def extract(
    jars_path: Path,
    out_dir: Path,
    manifest_path: Path | None = None,
    clean: bool = False,
    recursive: bool = False,
) -> dict[str, Any]:
    jars = discover_jars(jars_path, recursive)
    if not jars:
        raise McI18nError(f"No .jar files found in {jars_path}")
    manifest = _load_manifest(manifest_path) if manifest_path else None
    reports = [_read_jar(label, path) for label, path in jars]
    prepare_out(out_dir, clean)

    acc: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    jars_without_lang: list[dict[str, str]] = []
    for report in reports:
        errors.extend(report.errors)
        if report.without_lang_reason:
            jars_without_lang.append({"jar": report.label, "reason": report.without_lang_reason})
        for modid, payload in report.namespaces.items():
            slot = acc.setdefault(
                modid,
                {"jars": [], "langs": {code: {} for code in LANG_CODES}, "lang_errors": {}, "metas": []},
            )
            if report.label not in slot["jars"]:
                slot["jars"].append(report.label)
            for code in LANG_CODES:
                if code in payload.langs:
                    slot["langs"][code] = merge_lang(slot["langs"][code], payload.langs[code])
            slot["lang_errors"].update(payload.lang_errors)
            slot["metas"].append(report.meta)

    mods_index: list[dict[str, Any]] = []
    for modid in sorted(acc):
        slot = acc[modid]
        mod_dir = out_dir / modid
        mod_dir.mkdir(parents=True, exist_ok=True)
        for code in LANG_CODES:
            (mod_dir / LANG_FILENAMES[code]).write_text(dump_json(slot["langs"][code]), encoding="utf-8")
        meta = build_mod_meta(modid, slot["jars"], slot["metas"])
        (mod_dir / "meta.json").write_text(dump_json(meta), encoding="utf-8")
        counts = {code: len(collect_strings(slot["langs"][code])) for code in LANG_CODES}
        english = collect_strings(slot["langs"]["en_us"])
        entry: dict[str, Any] = {
            "modid": modid,
            "jar": slot["jars"][-1] if slot["jars"] else None,
            "jars": list(slot["jars"]),
            "key_counts": counts,
            "missing_in_zh_tw": sorted(set(english) - set(collect_strings(slot["langs"]["zh_tw"]))),
            "missing_in_zh_cn": sorted(set(english) - set(collect_strings(slot["langs"]["zh_cn"]))),
        }
        if slot["lang_errors"]:
            entry["lang_errors"] = dict(sorted(slot["lang_errors"].items()))
        mods_index.append(entry)

    index: dict[str, Any] = {
        "tool": "mc_i18n",
        "tool_version": __version__,
        "mods": mods_index,
        "jars_without_lang": jars_without_lang,
        "errors": sorted(errors, key=lambda item: (item.get("jar", ""), item.get("path", ""), item.get("message", ""))),
        "manifest": summarize_manifest(manifest, [label for label, _path in jars]) if manifest is not None else None,
    }
    (out_dir / "index.json").write_text(dump_json(index), encoding="utf-8")
    return index


def discover_jars(jars_path: Path, recursive: bool) -> list[tuple[str, Path]]:
    if jars_path.is_file():
        if jars_path.suffix.lower() != ".jar":
            raise McI18nError(f"Not a .jar file: {jars_path}")
        return [(jars_path.name, jars_path)]
    if not jars_path.is_dir():
        raise McI18nError(f"Jars path not found: {jars_path}")
    if recursive:
        found = [path for path in jars_path.rglob("*") if path.is_file() and path.suffix.lower() == ".jar"]
    else:
        found = [path for path in jars_path.iterdir() if path.is_file() and path.suffix.lower() == ".jar"]
    found.sort(key=lambda path: path.relative_to(jars_path).as_posix().lower())
    labeled: list[tuple[str, Path]] = []
    for path in found:
        relative = path.relative_to(jars_path).as_posix()
        labeled.append((relative if recursive else path.name, path))
    return labeled


def filename_has_file_id(filename: str, file_id: str) -> bool:
    if len(file_id) < _MIN_FILE_ID_DIGITS or not file_id.isdigit():
        return False
    return re.search(rf"(?<!\d){re.escape(file_id)}(?!\d)", filename) is not None


def summarize_manifest(manifest: dict[str, Any], jar_labels: list[str]) -> dict[str, Any]:
    minecraft = manifest.get("minecraft") if isinstance(manifest.get("minecraft"), dict) else {}
    loaders = minecraft.get("modLoaders") if isinstance(minecraft.get("modLoaders"), list) else []
    primary = None
    for loader in loaders:
        if isinstance(loader, dict) and loader.get("primary") and isinstance(loader.get("id"), str):
            primary = loader["id"]
            break
    if primary is None:
        for loader in loaders:
            if isinstance(loader, dict) and isinstance(loader.get("id"), str):
                primary = loader["id"]
                break
    matched: set[str] = set()
    files_out: list[dict[str, Any]] = []
    entries = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        file_id = entry.get("fileID")
        file_id_text = str(file_id) if isinstance(file_id, int) and not isinstance(file_id, bool) else ""
        if isinstance(file_id, str) and file_id.isdigit():
            file_id_text = file_id
        hits = [label for label in jar_labels if filename_has_file_id(label, file_id_text)]
        matched.update(hits)
        required = entry.get("required")
        files_out.append(
            {
                "projectID": entry.get("projectID"),
                "fileID": entry.get("fileID"),
                "required": True if required is None else bool(required),
                "jars": hits,
            }
        )
    return {
        "name": manifest.get("name") if isinstance(manifest.get("name"), str) else None,
        "version": manifest.get("version") if isinstance(manifest.get("version"), str) else None,
        "minecraft": minecraft.get("version") if isinstance(minecraft.get("version"), str) else None,
        "mod_loader": primary,
        "files": files_out,
        "jars_not_in_manifest": sorted(set(jar_labels) - matched),
    }


def prepare_out(out_dir: Path, clean: bool) -> None:
    if out_dir.exists() and not out_dir.is_dir():
        raise McI18nError(f"--out is not a directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = [child for child in out_dir.iterdir() if not child.name.startswith(".")]
    if not entries:
        return
    if clean or _looks_like_worktree(entries):
        _reset_out(out_dir, clean)
        return
    raise McI18nError(
        f"{out_dir} is not empty and is not a previous mc_i18n work directory. "
        "Pass --clean to replace it, or choose an empty directory."
    )


def format_extract_summary(index: dict[str, Any], out_dir: Path) -> str:
    lines = []
    for mod in index["mods"]:
        counts = mod["key_counts"]
        lines.append(
            f"{mod['modid']}: en_us={counts['en_us']} zh_cn={counts['zh_cn']} zh_tw={counts['zh_tw']} "
            f"missing_zh_tw={len(mod['missing_in_zh_tw'])} missing_zh_cn={len(mod['missing_in_zh_cn'])} "
            f"jar={mod['jar']}"
        )
    lines.append(f"wrote {len(index['mods'])} mods -> {out_dir / 'index.json'}")
    if index["errors"]:
        lines.append(f"warnings: {len(index['errors'])} (listed in index.json errors)")
    return "\n".join(lines)


def _looks_like_worktree(entries: list[Path]) -> bool:
    saw_index = False
    for entry in entries:
        if entry.name == "index.json" and entry.is_file():
            saw_index = True
            continue
        if entry.is_dir() and _is_mod_dir(entry):
            continue
        return False
    return saw_index or bool(entries)


def _is_mod_dir(path: Path) -> bool:
    try:
        names = {child.name for child in path.iterdir()}
    except OSError:
        return False
    return bool(names & _MARKERS)


def _reset_out(out_dir: Path, clean: bool) -> None:
    for child in list(out_dir.iterdir()):
        if child.name.startswith(".") and not clean:
            continue
        remove = clean or child.name == "index.json" or (child.is_dir() and _is_mod_dir(child))
        if not remove:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise McI18nError(f"Manifest not found: {path}")
    parsed = load_json_file(path)
    if not isinstance(parsed, dict):
        raise McI18nError(f"{path} is not a JSON object")
    return parsed


def _read_jar(label: str, path: Path) -> JarReport:
    report = JarReport(label=label)
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        report.errors.append({"jar": label, "path": "", "message": f"not a zip: {exc}"})
        report.without_lang_reason = "not a zip"
        return report
    with archive:
        names = {info.filename.replace("\\", "/"): info for info in archive.infolist() if not info.is_dir()}
        for info_name, info in names.items():
            match = _LANG_PATH.match(info_name)
            if match is None:
                continue
            modid = safe_modid(match.group("ns"))
            lang = match.group("lang").lower()
            if modid is None:
                report.errors.append(
                    {
                        "jar": label,
                        "path": info_name,
                        "message": f"skipped unsafe namespace {match.group('ns')!r}",
                    }
                )
                continue
            if info.file_size > _MAX_ENTRY_BYTES:
                report.errors.append(
                    {"jar": label, "path": info_name, "message": "lang file exceeds 20MB and was skipped"}
                )
                continue
            payload = report.namespaces.setdefault(modid, NamespacePayload())
            try:
                loaded = load_lang_bytes(archive.read(info))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                payload.lang_errors[lang] = str(exc)
                report.errors.append({"jar": label, "path": info_name, "message": str(exc)})
                loaded = {}
            if lang in payload.langs:
                payload.langs[lang] = merge_lang(payload.langs[lang], loaded)
            else:
                payload.langs[lang] = loaded
        report.meta = _read_jar_meta(archive, names, label, report.errors)
    if not report.namespaces:
        report.without_lang_reason = "no en_us/zh_cn/zh_tw json under assets/"
    return report


def _read_jar_meta(
    archive: zipfile.ZipFile,
    names: dict[str, zipfile.ZipInfo],
    label: str,
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    lower_map = {name.lower(): name for name in names}
    for lowered, loader in _METADATA_NAMES.items():
        actual = lower_map.get(lowered)
        if actual is None:
            continue
        info = names[actual]
        if info.file_size > _MAX_ENTRY_BYTES:
            errors.append({"jar": label, "path": actual, "message": "metadata file exceeds 20MB and was skipped"})
            continue
        raw = archive.read(info)
        try:
            if loader in {"forge", "neoforge"}:
                parts.append(parse_mods_toml(raw.decode("utf-8-sig"), loader))
            else:
                parts.append(parse_fabric_mod(decode_json_object(raw), loader))
        except (UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError, ValueError) as exc:
            errors.append({"jar": label, "path": actual, "message": str(exc)})
    pack_description = None
    pack_name = lower_map.get(_PACK_MCMETA)
    if pack_name is not None:
        info = names[pack_name]
        if info.file_size <= _MAX_ENTRY_BYTES:
            try:
                pack_description = parse_pack_mcmeta(decode_json_object(archive.read(info)))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append({"jar": label, "path": pack_name, "message": str(exc)})
    return combine_jar_meta(parts, pack_description)

