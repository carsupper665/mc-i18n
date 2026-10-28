#!/usr/bin/env bash
# Extract and pack the committed fixture. Does not download CurseForge or Modrinth files.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if command -v python3 >/dev/null 2>&1; then
  py="python3"
else
  py="python"
fi

"$py" "$root/scripts/make_fixture.py"
rm -rf "$root/work" "$root/dist"

"$py" -m mc_i18n extract \
  --jars "$root/fixtures/jars" \
  --manifest "$root/fixtures/manifest.json" \
  --out "$root/work"

"$py" -m mc_i18n pack \
  --work "$root/work" \
  --translations "$root/fixtures/translations" \
  --out "$root/dist/Lunchtime-zh_tw.zip" \
  --description "Lunchtime fixture zh_tw" \
  --mrpack "$root/dist/Lunchtime-zh_tw.mrpack" \
  --mc-version 1.20.1 \
  --loader forge \
  --loader-version 47.3.0 \
  --name "Lunchtime zh_tw"

opencc_args=()
if "$py" -c "import opencc" >/dev/null 2>&1; then
  "$py" -m mc_i18n pack \
    --work "$root/work" \
    --translations "$root/fixtures/translations" \
    --out "$root/dist/Lunchtime-zh_tw-opencc.zip" \
    --description "Lunchtime fixture zh_tw" \
    --opencc
  opencc_args=(--opencc-zip "$root/dist/Lunchtime-zh_tw-opencc.zip")
else
  echo "opencc-python-reimplemented is not installed; skipped the --opencc pack"
fi

"$py" "$root/scripts/verify_fixture.py" \
  --work "$root/work" \
  --zip "$root/dist/Lunchtime-zh_tw.zip" \
  --mrpack "$root/dist/Lunchtime-zh_tw.mrpack" \
  "${opencc_args[@]}"

echo "smoke ok"
