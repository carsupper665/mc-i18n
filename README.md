# mc_i18n

A small Python CLI for Minecraft Forge and Fabric mod localization. It extracts `en_us`, `zh_cn`, and `zh_tw` language files from mod jars into a worktree, then packs a Traditional Chinese (`zh_tw`) resource pack. It was written for Lunchtime-style 1.20.1 Forge packs (Cozy Create, cooking mods, and the same kind of jar folder).

The pack copies strings that already exist. It can optionally convert Simplified Chinese with OpenCC `s2twp`. It leaves English keys out of the resource pack when nothing has translated them.

Requires Python 3.11+. The standard library is enough for extract and pack. OpenCC is optional.

## Setup

From this repository:

```bash
python -m mc_i18n --help
```

On systems where `python` is not installed, use `python3` in every command below.

OpenCC, only if you pass `--opencc`:

```bash
python -m pip install opencc-python-reimplemented
```

Editable install, with tests:

```bash
python -m pip install -e ".[dev]"
```

## Lunchtime (Minecraft 1.20.1, Forge)

Copy the instance `mods/*.jar` files into `./jars`. If you exported the CurseForge pack, keep its `manifest.json` beside the jars. Extract reads those local jars. A manifest entry whose `fileID` is not in a local filename stays listed in `work/index.json` as unmatched. This tool does not download CurseForge files.

`1.20.1` resource packs use `pack_format` 15. Later 1.20.x releases use a higher format; pass `--pack-format` for those. The Forge version in the mrpack is the number from the manifest loader id (`forge-47.3.0` → `47.3.0`). Use the version from your Lunchtime instance. `47.3.0` below is the fixture's example.

```bash
python -m mc_i18n extract \
  --jars ./jars \
  --manifest ./manifest.json \
  --out ./work

python -m mc_i18n pack \
  --work ./work \
  --translations ./translations \
  --out ./dist/Lunchtime-zh_tw.zip \
  --description "Lunchtime Cozy Create — 繁體中文 (zh_tw)" \
  --pack-format 15
```

Put `dist/Lunchtime-zh_tw.zip` in the instance `resourcepacks` folder and enable it in the resource pack screen. The zip root is `pack.mcmeta` plus `assets/<modid>/lang/zh_tw.json`.

To fill gaps from each mod's `zh_cn.json` with OpenCC `s2twp` (Simplified → Traditional Taiwan, phrase table), add `--opencc`:

```bash
python -m mc_i18n pack \
  --work ./work \
  --translations ./translations \
  --out ./dist/Lunchtime-zh_tw.zip \
  --description "Lunchtime Cozy Create — 繁體中文 (zh_tw)" \
  --pack-format 15 \
  --opencc
```

### Optional Modrinth mrpack

`--mrpack` wraps that same zip in a minimal Modrinth pack (`formatVersion` 1) for Minecraft 1.20.1 Forge. The resource pack is stored at `overrides/resourcepacks/<zip name>`. This mrpack is the translation addon. It is not a re-export of the Lunchtime mod list.

```bash
python -m mc_i18n pack \
  --work ./work \
  --translations ./translations \
  --out ./dist/Lunchtime-zh_tw.zip \
  --description "Lunchtime Cozy Create — 繁體中文 (zh_tw)" \
  --pack-format 15 \
  --opencc \
  --mrpack ./dist/Lunchtime-zh_tw.mrpack \
  --mc-version 1.20.1 \
  --loader forge \
  --loader-version 47.3.0 \
  --name "Lunchtime zh_tw" \
  --version-id 1.0.0 \
  --i18n-update-mod 3.7.0 \
  --mods-translation-pack cYkaQUzr
```

`--i18n-update-mod` and `--mods-translation-pack` are optional. When they are present, pack asks the Modrinth API for that version's filename, size, sha1, sha512, and download URL. It does not download the jar or the resource pack. The Modrinth app downloads them when the mrpack is imported.

- `i18nupdatemod` is a mod, so it is listed as `mods/<file>.jar` (client required, server unsupported).
- `modstranslationpack` is a resource pack, so it is listed as `resourcepacks/<file>.zip`.

`3.7.0` and `cYkaQUzr` are examples. `cYkaQUzr` is an 8-character Modrinth version id for a 1.20.x ModsTranslationPack file. That project reuses version numbers across game lines, so copy the version id from the Modrinth version page when you want a specific file. Any other project can be added with `--dep slug=version` (repeat the flag). Version flags require `--mrpack`.

Importing the mrpack in the Modrinth app creates an instance with the Forge version you passed, the optional projects above, and `Lunchtime-zh_tw.zip` already in `resourcepacks`. Enable the pack in game. Your Lunchtime content mods still come from the original pack.

## Extract

```bash
python -m mc_i18n extract --jars ./jars --out ./work
python -m mc_i18n extract --jars ./jars --manifest ./manifest.json --out ./work
```

`--jars` is a directory of `*.jar` files, or one jar. Subfolders are included only with `--recursive`. Namespaces are lowercased. A jar that is not a zip, or a lang file that is not JSON, is recorded under `errors` and extract continues.

Running extract again replaces `index.json` and mod folders inside a directory that already looks like a worktree. `--clean` deletes everything else in `--out` as well. A non-empty unrelated directory is left untouched unless you pass `--clean`.

```text
work/
  index.json
  <modid>/
    en_us.json
    zh_cn.json
    zh_tw.json
    meta.json
```

Missing lang files are written as `{}`. `meta.json` carries the mod name, description, version, authors, license, URL, loader (`forge`, `neoforge`, `fabric`, or `quilt`), and the `pack.mcmeta` description when the jar has one. Descriptions come from `META-INF/mods.toml`, `META-INF/neoforge.mods.toml`, `fabric.mod.json`, or `quilt.mod.json`. `declared_mods` lists every mod those files declare. When the asset namespace and the mod id differ and the jar declares exactly one mod, `name` and `description` still come from that mod.

`index.json` lists each namespace:

| field | meaning |
| --- | --- |
| `modid` | asset namespace |
| `jar` | last jar, in sorted filename order, that contributed this namespace |
| `jars` | every jar that contributed it |
| `key_counts` | string values in each lang file (nested objects count as dotted paths) |
| `missing_in_zh_tw` | keys present in `en_us` and absent in `zh_tw` |
| `missing_in_zh_cn` | keys present in `en_us` and absent in `zh_cn` |

Comment-style lang files (`//`, `/* */`, trailing commas, a UTF-8 BOM) are accepted and rewritten as strict JSON.

A CurseForge manifest is optional. Each `files[]` entry is matched when the jar filename contains `fileID` as a digit-bounded number of at least 6 digits. Short numbers such as `47` in `forge-47.3.0.jar` are ignored so version tokens are not treated as file ids. Unmatched jars are listed in `jars_not_in_manifest`.

## Pack

```bash
python -m mc_i18n pack \
  --work ./work \
  --translations ./translations \
  --out ./dist/Lunchtime-zh_tw.zip
```

`--translations` is optional. Each overlay is `translations/<modid>/zh_tw.json` and contains only the keys you want to add or replace. An overlay for a namespace that is not in the worktree is still packed.

Each output `assets/<modid>/lang/zh_tw.json` is built in three layers. A later layer replaces earlier values key by key:

1. `work/<modid>/zh_tw.json` (the mod's own Traditional Chinese)
2. With `--opencc` only: every string in `work/<modid>/zh_cn.json`, converted with OpenCC `s2twp`
3. `translations/<modid>/zh_tw.json`

Keys that are still missing after those layers are omitted. English text is not copied into the pack. A namespace with no strings after the merge is omitted. `pack.mcmeta` is always written.

`s2twp` is the Taiwan phrase profile, so wording changes (`默认软件` → `預設軟體`, `保存` → `儲存`, `服务器` → `伺服器`). Printf tokens (`%s`, `%1$s`, `%%`) and brace tokens (`{0}`, `{count}`) are kept. Put the wording you want to keep in the overlay: that layer wins, including over a conversion of the same key.

The fixture shows the layers with a cooking-mod sample:

| key | mod `zh_tw` | `zh_cn` via `s2twp` | overlay | packed | packed with `--opencc` |
| --- | --- | --- | --- | --- | --- |
| `block.kitchen.stove` | 爐灶 | 爐灶 | omitted | 爐灶 | 爐灶 |
| `item.kitchen.spoon` | 木匙 | 木勺 | omitted | 木匙 | 木勺 |
| `item.kitchen.bowl` | omitted | 飯碗 | 飯碗 | 飯碗 | 飯碗 |
| `block.cozy_example.oven` | omitted | 溫馨烤箱 | 暖心烤箱 | 暖心烤箱 | 暖心烤箱 |
| `item.cozy_example.broth` | omitted | 蔬菜高湯 | omitted | omitted | 蔬菜高湯 |
| `item.cozy_example.note` | omitted | 儲存 %1$s %% {count} | omitted | omitted | 儲存 %1$s %% {count} |
| `tooltip.cozy_example.quality` | omitted | 預設軟體 | omitted | omitted | 預設軟體 |

When two jars share a namespace, extract merges them in sorted filename order and the later jar wins on each key.

## mrpack shape

The `.mrpack` file is a zip. `formatVersion` 1:

```text
modrinth.index.json
overrides/resourcepacks/Lunchtime-zh_tw.zip
```

`overrides/` is copied into the instance directory, so the inner zip lands in `resourcepacks/`. It is not listed in `files`, because `files` is only for downloads.

```json
{
  "dependencies": {
    "forge": "47.3.0",
    "minecraft": "1.20.1"
  },
  "files": [
    {
      "downloads": [
        "https://cdn.modrinth.com/data/PWERr14M/versions/4ihDUjWs/I18nUpdateMod-3.7.0-all.jar"
      ],
      "env": {
        "client": "required",
        "server": "unsupported"
      },
      "fileSize": 49726,
      "hashes": {
        "sha1": "d9c217b569345ae30a5271baa5e9482080c2e41d",
        "sha512": "<128 hex chars from the Modrinth version API>"
      },
      "path": "mods/I18nUpdateMod-3.7.0-all.jar"
    },
    {
      "downloads": [
        "https://cdn.modrinth.com/data/<project>/versions/<version-id>/<file>"
      ],
      "env": {
        "client": "required",
        "server": "unsupported"
      },
      "fileSize": 2134122,
      "hashes": {
        "sha1": "<40 hex chars>",
        "sha512": "<128 hex chars>"
      },
      "path": "resourcepacks/ModsTranslationPack-1.20.x.zip"
    }
  ],
  "formatVersion": 1,
  "game": "minecraft",
  "name": "Lunchtime zh_tw",
  "summary": "Lunchtime zh_tw resource pack for Minecraft 1.20.1 (forge 47.3.0).",
  "versionId": "1.0.0"
}
```

`hashes`, `fileSize`, and `downloads` are copied from the version object returned by `GET /v2/version/{id}` or `GET /v2/project/{slug}/version/{number}`. The tool checks that sha1 is 40 hex chars and sha512 is 128. `env` comes from the project's `client_side` and `server_side` when those values are `required`, `optional`, or `unsupported`.

`dependencies.minecraft` is `--mc-version` (default `1.20.1`). `--loader-version` sets `forge`, `neoforge`, `fabric-loader`, or `quilt-loader` to match `--loader` (default `forge`). Without `--loader-version` the index still contains `minecraft` and pack prints a warning.

An mrpack with `"files": []` is valid. That is what you get when you pass `--mrpack` and no Modrinth versions. Smoke tests use that form so they stay offline.

## Fixture and tests

`fixtures/src/` is a tiny Forge jar (two namespaces, one partial `zh_tw`, comment-style JSON), a Fabric jar, and a jar with lang files and no mod metadata. `scripts/make_fixture.py` zips those trees into `fixtures/jars/`. `fixtures/manifest.json` is a CurseForge manifest whose file id `5550001` matches `cozy-example-5550001.jar`. `fixtures/translations/` is the overlay used by the smoke test.

```bash
pytest
./scripts/smoke.sh
```

`scripts/smoke.sh` rebuilds the fixture jars, runs extract and pack, and checks the zip and mrpack. It packs a second zip with `--opencc` when `opencc-python-reimplemented` is installed. It does not download CurseForge or Modrinth files.
