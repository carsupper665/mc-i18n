"""JSON helpers for Minecraft lang files.

Lang files in the wild are usually UTF-8 objects of string keys. A few mods
ship a BOM, ``//`` comments, or a trailing comma. Extract accepts those and
writes strict JSON back out.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mc_i18n.errors import McI18nError

# printf tokens and {named} / {0} placeholders used by Minecraft and Forge.
_PLACEHOLDER = re.compile(
    r"%%"
    r"|%(?:\d+\$)?[+#\- 0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[A-Za-z]"
    r"|\{[A-Za-z0-9_.:+-]+\}"
)

_MODID = re.compile(r"[a-z0-9_.-]+")


def safe_modid(name: str) -> str | None:
    """Return a lowercase modid, or None when the name is not safe to use as a path."""
    candidate = name.strip().lower()
    if not candidate or candidate in {".", ".."}:
        return None
    if candidate.startswith(".") or candidate.endswith("."):
        return None
    if _MODID.fullmatch(candidate) is None:
        return None
    return candidate


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json_file(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise McI18nError(f"{path} is not UTF-8: {exc}") from exc
    except OSError as exc:
        raise McI18nError(f"Could not read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise McI18nError(f"{path} is not valid JSON: {exc}") from exc


def load_lang_file(path: Path) -> dict[str, Any]:
    try:
        return load_lang_bytes(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, OSError) as exc:
        raise McI18nError(f"{path}: {exc}") from exc


def load_lang_bytes(data: bytes) -> dict[str, Any]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig")
    return load_lang_text(text)


def load_lang_text(text: str) -> dict[str, Any]:
    text = text.lstrip("\ufeff")
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        cleaned = strip_trailing_commas(strip_json_comments(text))
        if not cleaned.strip():
            return {}
        parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("lang file must be a JSON object")
    return parsed


def strip_json_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        char = text[i]
        if in_string:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue
        if char == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            continue
        out.append(char)
        i += 1
    return "".join(out)


def strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        char = text[i]
        if in_string:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue
        if char == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(char)
        i += 1
    return "".join(out)


def collect_strings(obj: Any, prefix: str = "") -> dict[str, str]:
    """Map dotted paths to string leaves. Nested objects are walked; other types are skipped."""
    found: dict[str, str] = {}
    if not isinstance(obj, dict):
        return found
    for key, value in obj.items():
        if not isinstance(key, str):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, str):
            found[path] = value
        elif isinstance(value, dict):
            found.update(collect_strings(value, path))
    return found


def merge_lang(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two lang objects. ``overlay`` replaces ``base`` key by key."""
    result: dict[str, Any] = {}
    for key, value in base.items():
        result[key] = _copy_json(value)
    for key, value in overlay.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = merge_lang(current, value)
        else:
            result[key] = _copy_json(value)
    return result


def _copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    return value


def protect_placeholders(text: str, convert) -> str:
    """Run ``convert`` on the prose and leave printf / brace tokens unchanged."""
    parts = _PLACEHOLDER.split(text)
    holders = _PLACEHOLDER.findall(text)
    converted = [convert(part) if part else part for part in parts]
    pieces: list[str] = []
    for index, part in enumerate(converted):
        pieces.append(part)
        if index < len(holders):
            pieces.append(holders[index])
    return "".join(pieces)
