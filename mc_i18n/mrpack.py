"""Build a formatVersion 1 Modrinth mrpack and resolve optional Modrinth files."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from mc_i18n import __version__
from mc_i18n.errors import McI18nError
from mc_i18n.langutil import dump_json
from mc_i18n.zipio import zip_bytes

API_ROOT = "https://api.modrinth.com"
_VERSION_ID = re.compile(r"[A-Za-z0-9]{8}")
_LOADER_DEPENDENCY = {
    "forge": "forge",
    "neoforge": "neoforge",
    "fabric": "fabric-loader",
    "quilt": "quilt-loader",
}
_INSTALL_DIR = {
    "mod": "mods",
    "resourcepack": "resourcepacks",
    "shader": "shaderpacks",
    "datapack": "datapacks",
}
_ENV_VALUES = {"required", "optional", "unsupported"}


def modrinth_get(path: str) -> Any:
    """GET a Modrinth API path. Returns None on HTTP 404."""
    url = path if path.startswith("https://") else API_ROOT + path
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"mc-i18n/{__version__} (minecraft localization toolkit)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        if exc.code == 404:
            return None
        raise McI18nError(f"Modrinth API HTTP {exc.code} for {path}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise McI18nError(f"Could not reach the Modrinth API: {exc.reason}") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise McI18nError(f"Modrinth API returned non-JSON for {path}") from exc


def resolve_dependency(slug: str, version: str, mc_version: str, loader: str) -> dict[str, Any]:
    """Resolve one Modrinth project version into an mrpack ``files[]`` entry plus log fields."""
    slug = slug.strip().lower()
    version = version.strip()
    project = modrinth_get(f"/v2/project/{quote(slug, safe='')}")
    if not isinstance(project, dict):
        raise McI18nError(f"Modrinth project {slug!r} was not found")
    project_type = project.get("project_type") or "mod"
    chosen = _version_by_id(project, version)
    if chosen is None:
        chosen = _version_by_number(slug, version, mc_version, loader, project_type)
    file_info = _choose_file(chosen.get("files") or [], mc_version)
    entry = _file_entry(project, project_type, file_info)
    return {
        "entry": entry,
        "slug": slug,
        "version_id": chosen.get("id"),
        "version_number": chosen.get("version_number"),
        "path": entry["path"],
        "game_versions": list(chosen.get("game_versions") or []),
    }


def build_mrpack(
    *,
    resource_pack_name: str,
    resource_pack_bytes: bytes,
    name: str,
    version_id: str,
    summary: str,
    mc_version: str,
    loader: str,
    loader_version: str | None,
    resolved: list[dict[str, Any]],
) -> bytes:
    dependencies: dict[str, str] = {"minecraft": mc_version}
    if loader_version:
        dep_key = _LOADER_DEPENDENCY.get(loader)
        if dep_key is None:
            raise McI18nError(f"Unknown loader {loader!r}")
        dependencies[dep_key] = loader_version
    files = [item["entry"] for item in resolved]
    files.sort(key=lambda item: item["path"])
    index = {
        "dependencies": dependencies,
        "files": files,
        "formatVersion": 1,
        "game": "minecraft",
        "name": name,
        "summary": summary,
        "versionId": version_id,
    }
    arcname = f"overrides/resourcepacks/{Path(resource_pack_name).name}"
    return zip_bytes(
        [
            ("modrinth.index.json", dump_json(index).encode("utf-8")),
            (arcname, resource_pack_bytes),
        ]
    )


def _version_by_id(project: dict[str, Any], version: str) -> dict[str, Any] | None:
    if _VERSION_ID.fullmatch(version) is None:
        return None
    got = modrinth_get(f"/v2/version/{quote(version, safe='')}")
    if got is None:
        return None
    if not isinstance(got, dict):
        raise McI18nError(f"Modrinth version {version} was not an object")
    if got.get("project_id") != project.get("id"):
        raise McI18nError(
            f"Version {version} belongs to project {got.get('project_id')}, "
            f"not {project.get('slug')} ({project.get('id')})"
        )
    return got


def _version_by_number(
    slug: str,
    version: str,
    mc_version: str,
    loader: str,
    project_type: str,
) -> dict[str, Any]:
    filtered = _list_versions(slug, mc_version, loader if project_type == "mod" else None)
    exact = [item for item in filtered if item.get("version_number") == version or item.get("id") == version]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        chosen = exact[0]
        others = ", ".join(f"{item.get('id')} ({_file_hint(item)})" for item in exact[:6])
        print_warning(
            f"Modrinth project {slug} has {len(exact)} versions named {version!r} "
            f"for Minecraft {mc_version}. Using {chosen.get('id')} ({_file_hint(chosen)}). "
            f"Pass a version id to pin one. Candidates: {others}"
        )
        return chosen
    everything = _list_versions(slug, None, None)
    named = [item for item in everything if item.get("version_number") == version or item.get("id") == version]
    if not named:
        raise McI18nError(f"No Modrinth version {version!r} on project {slug}")
    preview = "\n".join(
        f"  {item.get('id')}  {item.get('version_number')}  "
        f"loaders={','.join(item.get('loaders') or [])}  "
        f"games={','.join((item.get('game_versions') or [])[:6])}  file={_file_hint(item)}"
        for item in named[:8]
    )
    loader_note = f" loader {loader}" if project_type == "mod" else ""
    raise McI18nError(
        f"Version {version!r} of {slug} is not published for Minecraft {mc_version}{loader_note}. "
        f"Pass an 8-character Modrinth version id to pin a file.\n{preview}"
    )


def _list_versions(slug: str, mc_version: str | None, loader: str | None) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = []
    if mc_version:
        params.append(("game_versions", json.dumps([mc_version], separators=(",", ":"))))
    if loader:
        params.append(("loaders", json.dumps([loader], separators=(",", ":"))))
    query = f"?{urlencode(params)}" if params else ""
    payload = modrinth_get(f"/v2/project/{quote(slug, safe='')}/version{query}")
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise McI18nError(f"Modrinth version list for {slug} was not a list")
    return [item for item in payload if isinstance(item, dict)]


def _choose_file(files: list[dict[str, Any]], mc_version: str) -> dict[str, Any]:
    usable = [
        item
        for item in files
        if item.get("file_type") != "source"
        and not str(item.get("filename") or "").endswith("-sources.jar")
    ]
    if not usable:
        usable = [item for item in files if isinstance(item, dict)]
    if not usable:
        raise McI18nError("Modrinth version has no files")
    exact = [item for item in usable if mc_version and mc_version in str(item.get("filename") or "")]
    pool = exact or usable
    primary = [item for item in pool if item.get("primary")]
    return (primary or pool)[0]


def _file_entry(project: dict[str, Any], project_type: str, file_info: dict[str, Any]) -> dict[str, Any]:
    filename = Path(str(file_info.get("filename") or "")).name
    if not filename:
        raise McI18nError(f"Modrinth file for {project.get('slug')} has no filename")
    hashes = file_info.get("hashes") if isinstance(file_info.get("hashes"), dict) else {}
    sha1 = _hex_hash(hashes.get("sha1"), 40, filename, "sha1")
    sha512 = _hex_hash(hashes.get("sha512"), 128, filename, "sha512")
    url = file_info.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise McI18nError(f"Modrinth file {filename} has no https download url")
    size = file_info.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise McI18nError(f"Modrinth file {filename} has no file size")
    directory = _INSTALL_DIR.get(str(project_type), "mods")
    entry: dict[str, Any] = {
        "downloads": [url],
        "env": _env_from_project(project),
        "fileSize": size,
        "hashes": {"sha1": sha1, "sha512": sha512},
        "path": f"{directory}/{filename}",
    }
    if entry["env"] is None:
        del entry["env"]
    return entry


def _env_from_project(project: dict[str, Any]) -> dict[str, str] | None:
    env: dict[str, str] = {}
    for source, dest in (("client_side", "client"), ("server_side", "server")):
        value = project.get(source)
        if value in _ENV_VALUES:
            env[dest] = value
    return env or None


def _hex_hash(value: Any, length: int, filename: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise McI18nError(f"Modrinth file {filename} is missing a {label} hash")
    if any(char not in "0123456789abcdefABCDEF" for char in value):
        raise McI18nError(f"Modrinth file {filename} has a non-hex {label} hash")
    return value.lower()


def _file_hint(version: dict[str, Any]) -> str:
    files = version.get("files") or []
    for item in files:
        if isinstance(item, dict) and item.get("primary"):
            return str(item.get("filename"))
    if files and isinstance(files[0], dict):
        return str(files[0].get("filename"))
    return "?"


def print_warning(message: str) -> None:
    import sys

    print(f"warning: {message}", file=sys.stderr)
