"""Read Forge ``mods.toml`` and Fabric ``fabric.mod.json`` description fields."""

from __future__ import annotations

import json
import tomllib
from typing import Any

_LOADER_PREFERENCE = ("neoforge", "forge", "fabric", "quilt")


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def description_text(value: Any) -> str | None:
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return clean_text(value["text"])
    return None


def clean_version(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def normalize_authors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                raw = item.get("name") or item.get("email") or ""
                text = raw.strip() if isinstance(raw, str) else str(raw).strip()
            else:
                text = str(item).strip()
            if text:
                names.append(text)
        return names
    return [str(value)]


def parse_mods_toml(text: str, loader: str) -> dict[str, Any]:
    data = tomllib.loads(text)
    if not isinstance(data, dict):
        raise ValueError("mods.toml must be a table")
    license_text = clean_text(data.get("license"))
    issue_url = clean_text(data.get("issueTrackerURL"))
    declared: list[dict[str, Any]] = []
    mods = data.get("mods") or []
    if isinstance(mods, list):
        for mod in mods:
            if not isinstance(mod, dict):
                continue
            modid = mod.get("modId") or mod.get("modid")
            if not isinstance(modid, str) or not modid.strip():
                continue
            modid = modid.strip()
            declared.append(
                {
                    "modid": modid,
                    "loader": loader,
                    "name": clean_text(mod.get("displayName")) or modid,
                    "description": description_text(mod.get("description")),
                    "version": clean_version(mod.get("version")),
                    "authors": normalize_authors(mod.get("authors", mod.get("author"))),
                    "url": clean_text(mod.get("displayURL")),
                }
            )
    return {
        "loader": loader,
        "license": license_text,
        "url": issue_url,
        "declared_mods": declared,
    }


def parse_fabric_mod(data: dict[str, Any], loader: str = "fabric") -> dict[str, Any]:
    contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
    url = None
    for key in ("homepage", "issues", "sources"):
        url = clean_text(contact.get(key))
        if url:
            break
    declared: list[dict[str, Any]] = []
    modid = data.get("id")
    if isinstance(modid, str) and modid.strip():
        modid = modid.strip()
        declared.append(
            {
                "modid": modid,
                "loader": loader,
                "name": clean_text(data.get("name")) or modid,
                "description": description_text(data.get("description")),
                "version": clean_version(data.get("version")),
                "authors": normalize_authors(data.get("authors")),
                "url": url,
            }
        )
    return {
        "loader": loader,
        "license": clean_text(data.get("license")),
        "url": url,
        "declared_mods": declared,
    }


def parse_pack_mcmeta(data: dict[str, Any]) -> str | None:
    pack = data.get("pack")
    if not isinstance(pack, dict):
        return None
    return description_text(pack.get("description"))


def empty_jar_meta() -> dict[str, Any]:
    return {
        "license": None,
        "url": None,
        "pack_mcmeta_description": None,
        "declared_mods": [],
    }


def combine_jar_meta(parts: list[dict[str, Any]], pack_description: str | None) -> dict[str, Any]:
    combined = empty_jar_meta()
    combined["pack_mcmeta_description"] = pack_description
    for part in parts:
        if combined["license"] is None and part.get("license"):
            combined["license"] = part["license"]
        if combined["url"] is None and part.get("url"):
            combined["url"] = part["url"]
        combined["declared_mods"].extend(part.get("declared_mods") or [])
    return combined


def decode_json_object(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8-sig")
    parsed = json.loads(text.lstrip("\ufeff"))
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def build_mod_meta(
    modid: str,
    jars: list[str],
    jar_metas: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fold per-jar metadata into the ``meta.json`` written for one namespace."""
    license_text = None
    jar_url = None
    pack_description = None
    declared: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for meta in jar_metas:
        if license_text is None and meta.get("license"):
            license_text = meta["license"]
        if jar_url is None and meta.get("url"):
            jar_url = meta["url"]
        if pack_description is None and meta.get("pack_mcmeta_description"):
            pack_description = meta["pack_mcmeta_description"]
        for mod in meta.get("declared_mods") or []:
            key = (str(mod.get("loader")), str(mod.get("modid")))
            if key in seen:
                continue
            seen.add(key)
            declared.append(mod)
    declared.sort(key=lambda mod: (str(mod.get("loader")), str(mod.get("modid"))))
    matched = pick_declared_mod(modid, declared)
    matched_url = matched.get("url") if matched else None
    return {
        "modid": modid,
        "jar": jars[-1] if jars else None,
        "jars": list(jars),
        "loader": None if matched is None else matched.get("loader"),
        "name": None if matched is None else matched.get("name"),
        "description": None if matched is None else matched.get("description"),
        "version": None if matched is None else matched.get("version"),
        "authors": [] if matched is None else list(matched.get("authors") or []),
        "license": license_text,
        "url": matched_url or jar_url,
        "pack_mcmeta_description": pack_description,
        "declared_mods": declared,
    }


def pick_declared_mod(modid: str, declared: list[dict[str, Any]]) -> dict[str, Any] | None:
    hits = [mod for mod in declared if mod.get("modid") == modid]
    if not hits and len(declared) == 1:
        return declared[0]
    if not hits:
        return None
    for loader in _LOADER_PREFERENCE:
        for hit in hits:
            if hit.get("loader") == loader:
                return hit
    return hits[0]
