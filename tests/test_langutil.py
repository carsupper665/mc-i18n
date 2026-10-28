import pytest

from mc_i18n.convert import convert_lang, open_converter
from mc_i18n.langutil import (
    collect_strings,
    load_lang_bytes,
    load_lang_text,
    merge_lang,
    protect_placeholders,
    safe_modid,
)


def test_comments_trailing_commas_and_urls():
    raw = """{
      "a": "see https://example.invalid/a", // keep the url
      "b": "has /* inside a string */",
      /* drop me */
      "c": "tail",
    }"""
    assert load_lang_text(raw) == {
        "a": "see https://example.invalid/a",
        "b": "has /* inside a string */",
        "c": "tail",
    }


def test_bom_and_utf16_and_empty():
    assert load_lang_bytes(b"\xef\xbb\xbf" + b'{"a": "b"}') == {"a": "b"}
    assert load_lang_bytes('{"a": "b"}'.encode("utf-16")) == {"a": "b"}
    assert load_lang_text("   ") == {}
    with pytest.raises(ValueError):
        load_lang_text("[1, 2]")


def test_collect_strings_walks_nested_objects():
    assert collect_strings({"a": {"b": "c"}, "d": 1, "e": "f"}) == {"a.b": "c", "e": "f"}


def test_lang_json_flattens_nested_objects_and_rejects_non_strings():
    assert load_lang_text('{"group": {"message": "Hello"}}') == {"group.message": "Hello"}
    with pytest.raises(ValueError, match=r"group\.count.*must be a string"):
        load_lang_text('{"group": {"count": 3}}')
    with pytest.raises(ValueError, match="duplicate flattened key"):
        load_lang_text('{"group.message": "one", "group": {"message": "two"}}')


def test_merge_lang_overlay_replaces_strings_and_merges_objects():
    merged = merge_lang({"a": "one", "nest": {"x": "1", "y": "2"}}, {"a": "two", "nest": {"y": "9"}})
    assert merged == {"a": "two", "nest": {"x": "1", "y": "9"}}


def test_safe_modid_lowercases_and_rejects_traversal():
    assert safe_modid("Cozy_Example") == "cozy_example"
    assert safe_modid("..") is None
    assert safe_modid("a/b") is None
    assert safe_modid(".hidden") is None


def test_placeholders_are_not_passed_to_the_converter():
    def hostile(text: str) -> str:
        return text.upper().replace("%", "X").replace("{", "").replace("}", "")

    assert protect_placeholders("save %1$s %% {count}", hostile) == "SAVE %1$s %% {count}"


def test_opencc_s2twp_converts_phrases_and_keeps_tokens():
    pytest.importorskip("opencc")
    convert = open_converter()
    assert convert("服务器") == "伺服器"
    converted = convert_lang(
        {"tooltip.demo.quality": "默认软件", "item.demo.note": "保存 %1$s %% {count}"},
        convert,
    )
    assert converted == {
        "tooltip.demo.quality": "預設軟體",
        "item.demo.note": "儲存 %1$s %% {count}",
    }
