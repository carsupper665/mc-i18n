"""Optional Simplified-to-Traditional conversion via OpenCC s2twp."""

from __future__ import annotations

from typing import Any, Callable

from mc_i18n.errors import McI18nError
from mc_i18n.langutil import protect_placeholders

OPENCC_CONFIG = "s2twp"


def open_converter(config: str = OPENCC_CONFIG) -> Callable[[str], str]:
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise McI18nError(
            "OpenCC s2twp conversion needs the optional package "
            "opencc-python-reimplemented. Install it with: "
            "python -m pip install opencc-python-reimplemented"
        ) from exc
    converter = OpenCC(config)
    return converter.convert


def convert_lang(data: dict[str, Any], convert: Callable[[str], str]) -> dict[str, Any]:
    """Convert string values. Keys, placeholders, and non-strings stay as they are."""
    converted = _convert_value(data, convert)
    if not isinstance(converted, dict):
        return {}
    return converted


def _convert_value(value: Any, convert: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return protect_placeholders(value, convert)
    if isinstance(value, list):
        return [_convert_value(item, convert) for item in value]
    if isinstance(value, dict):
        return {key: _convert_value(item, convert) for key, item in value.items()}
    return value
