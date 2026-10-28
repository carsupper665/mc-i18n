"""Small deterministic zip writer shared by the resource pack and the mrpack."""

from __future__ import annotations

import io
import zipfile

from mc_i18n.errors import McI18nError


def zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for name, payload in files:
            info = zipfile.ZipInfo(filename=_check_arcname(name), date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            # Mark filenames as UTF-8.
            info.flag_bits |= 0x800
            archive.writestr(info, payload)
    return buffer.getvalue()


def _check_arcname(name: str) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise McI18nError(f"Unsafe zip path: {name}")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise McI18nError(f"Unsafe zip path: {name}")
    return "/".join(parts)
