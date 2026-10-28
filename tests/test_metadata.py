from mc_i18n.metadata import (
    parse_fabric_mod,
    parse_mods_toml,
    parse_quilt_mod,
    pick_declared_mod,
)


def test_mods_toml_authors_and_description():
    parsed = parse_mods_toml(
        """
        license = "MIT"
        issueTrackerURL = "https://example.invalid/issues"

        [[mods]]
        modId = "only_one"
        version = "1.0.0"
        displayName = "Only One"
        authors = "A, B"
        description = "Hello there"
        """,
        "forge",
    )
    mod = parsed["declared_mods"][0]
    assert parsed["license"] == "MIT"
    assert parsed["url"] == "https://example.invalid/issues"
    assert mod["authors"] == ["A", "B"]
    assert mod["name"] == "Only One"
    assert mod["description"] == "Hello there"
    assert mod["loader"] == "forge"


def test_fabric_author_objects_and_component_description():
    parsed = parse_fabric_mod(
        {
            "id": "snack",
            "name": "Snack",
            "description": {"text": "Hi"},
            "authors": [{"name": "Lunchtime"}],
            "version": 3,
            "license": "MIT",
            "contact": {"homepage": "https://example.invalid/snack"},
        }
    )
    mod = parsed["declared_mods"][0]
    assert mod["authors"] == ["Lunchtime"]
    assert mod["description"] == "Hi"
    assert mod["version"] == "3"
    assert mod["url"] == "https://example.invalid/snack"


def test_pick_declared_mod_falls_back_only_when_one_mod_is_declared():
    only = [{"modid": "real", "loader": "forge", "name": "Real"}]
    assert pick_declared_mod("other", only)["name"] == "Real"
    assert pick_declared_mod("real", only)["modid"] == "real"
    two = only + [{"modid": "second", "loader": "forge", "name": "Second"}]
    assert pick_declared_mod("missing", two) is None
    assert pick_declared_mod("second", two)["name"] == "Second"


def test_quilt_metadata_uses_quilt_loader_schema():
    parsed = parse_quilt_mod(
        {
            "schema_version": 1,
            "quilt_loader": {
                "id": "quilt_snack",
                "version": "2.4.0",
                "metadata": {
                    "name": "Quilt Snack",
                    "description": "A Quilt mod",
                    "contributors": {"Ada": "Developer", "Lin": "Translator"},
                    "contact": {"homepage": "https://example.invalid/quilt-snack"},
                    "license": "MIT",
                },
            },
        }
    )
    mod = parsed["declared_mods"][0]
    assert mod == {
        "modid": "quilt_snack",
        "loader": "quilt",
        "name": "Quilt Snack",
        "description": "A Quilt mod",
        "version": "2.4.0",
        "authors": ["Ada", "Lin"],
        "url": "https://example.invalid/quilt-snack",
    }
    assert parsed["license"] == "MIT"
    assert parsed["url"] == "https://example.invalid/quilt-snack"
