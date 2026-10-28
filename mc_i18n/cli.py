"""Command line for ``python -m mc_i18n``."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from mc_i18n import __version__
from mc_i18n.errors import McI18nError
from mc_i18n.extract import extract, format_extract_summary
from mc_i18n.pack import (
    DEFAULT_DESCRIPTION,
    DEFAULT_MC_VERSION,
    DEFAULT_PACK_FORMAT,
    MrpackOptions,
    emit_summary,
    format_pack_summary,
    pack,
)

_SLUG = re.compile(r"[a-z0-9_-]+")
_EPILOG = """\
examples:
  python -m mc_i18n extract --jars ./jars --out ./work
  python -m mc_i18n extract --jars ./jars --manifest ./manifest.json --out ./work
  python -m mc_i18n pack --work ./work --translations ./translations --out ./dist/Lunchtime-zh_tw.zip
  python -m mc_i18n pack --work ./work --translations ./translations \\
      --out ./dist/Lunchtime-zh_tw.zip --opencc \\
      --mrpack ./dist/Lunchtime-zh_tw.mrpack --loader-version 47.3.0
"""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            return _cmd_extract(args)
        if args.command == "pack":
            return _cmd_pack(args)
    except McI18nError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("error: unknown command", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mc_i18n",
        description="Extract Minecraft mod language files and pack a zh_tw resource pack.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument("--version", action="version", version=f"mc_i18n {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_parser = sub.add_parser("extract", help="Extract lang files from mod jars into a worktree")
    extract_parser.add_argument("--jars", required=True, type=Path, help="Directory of .jar mods (or one jar)")
    extract_parser.add_argument("--out", required=True, type=Path, help="Work directory to write")
    extract_parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional CurseForge manifest.json. Used to report which fileIDs match local jar names.",
    )
    extract_parser.add_argument(
        "--clean",
        action="store_true",
        help="Replace the output directory even when it is not an existing worktree",
    )
    extract_parser.add_argument(
        "--recursive",
        action="store_true",
        help="Also read jars in subfolders of --jars",
    )

    pack_parser = sub.add_parser("pack", help="Pack worktree langs into a zh_tw resource pack")
    pack_parser.add_argument("--work", required=True, type=Path, help="Work directory from extract")
    pack_parser.add_argument("--out", required=True, type=Path, help="Resource pack zip to write")
    pack_parser.add_argument(
        "--translations",
        type=Path,
        help="Overlay directory of translations/<modid>/zh_tw.json",
    )
    pack_parser.add_argument(
        "--opencc",
        action="store_true",
        help="Convert zh_cn values with OpenCC s2twp. This layer replaces existing zh_tw keys.",
    )
    pack_parser.add_argument("--pack-format", type=int, default=DEFAULT_PACK_FORMAT)
    pack_parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    pack_parser.add_argument("--mrpack", type=Path, help="Also write a Modrinth mrpack (formatVersion 1)")
    pack_parser.add_argument("--mc-version")
    pack_parser.add_argument("--loader", choices=("forge", "neoforge", "fabric", "quilt"))
    pack_parser.add_argument("--loader-version", help="Loader version recorded in the mrpack, such as 47.3.0")
    pack_parser.add_argument("--name", help="mrpack name. Defaults to the resource pack zip stem.")
    pack_parser.add_argument("--version-id", help="mrpack versionId (default: 1.0.0)")
    pack_parser.add_argument("--summary", help="mrpack summary")
    pack_parser.add_argument(
        "--i18n-update-mod",
        metavar="VERSION",
        help="Modrinth version id or version number for project i18nupdatemod",
    )
    pack_parser.add_argument(
        "--mods-translation-pack",
        metavar="VERSION",
        help="Modrinth version id or version number for project modstranslationpack",
    )
    pack_parser.add_argument(
        "--dep",
        action="append",
        type=_dep_pair,
        default=None,
        metavar="SLUG=VERSION",
        help="Extra Modrinth project to list in the mrpack. Repeat for more than one.",
    )
    return parser


def _cmd_extract(args: argparse.Namespace) -> int:
    index = extract(
        args.jars,
        args.out,
        manifest_path=args.manifest,
        clean=args.clean,
        recursive=args.recursive,
    )
    print(format_extract_summary(index, args.out))
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    deps: list[tuple[str, str]] = []
    if args.i18n_update_mod is not None:
        version = args.i18n_update_mod.strip()
        if not version:
            raise McI18nError("--i18n-update-mod needs a version id or version number")
        deps.append(("i18nupdatemod", version))
    if args.mods_translation_pack is not None:
        version = args.mods_translation_pack.strip()
        if not version:
            raise McI18nError("--mods-translation-pack needs a version id or version number")
        deps.append(("modstranslationpack", version))
    deps.extend(args.dep or [])
    mrpack_args = (
        args.mc_version,
        args.loader,
        args.loader_version,
        args.name,
        args.version_id,
        args.summary,
        *deps,
    )
    if args.mrpack is None and any(value is not None for value in mrpack_args):
        raise McI18nError("mrpack options require --mrpack")
    mrpack = None
    if args.mrpack is not None:
        mrpack = MrpackOptions(
            path=args.mrpack,
            mc_version=args.mc_version or DEFAULT_MC_VERSION,
            loader=args.loader or "forge",
            loader_version=args.loader_version,
            name=args.name,
            version_id=args.version_id or "1.0.0",
            summary=args.summary,
            deps=deps,
        )
    result = pack(
        args.work,
        args.out,
        translations_dir=args.translations,
        use_opencc=args.opencc,
        pack_format=args.pack_format,
        description=args.description,
        mrpack=mrpack,
    )
    emit_summary(format_pack_summary(result, args.out, args.mrpack))
    return 0


def _dep_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected slug=version")
    slug, version = value.split("=", 1)
    slug = slug.strip().lower()
    version = version.strip()
    if not slug or not version:
        raise argparse.ArgumentTypeError("expected slug=version")
    if _SLUG.fullmatch(slug) is None:
        raise argparse.ArgumentTypeError(f"invalid Modrinth slug: {slug}")
    return slug, version
