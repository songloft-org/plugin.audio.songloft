#!/bin/bash
set -e

ADDON_ID="plugin.audio.songloft"
VERSION=$(grep -oP '<addon\b[^>]*\bversion="\K[^"]+' addon.xml)
ZIP_NAME="${ADDON_ID}-${VERSION}.zip"

cd ..
rm -f "${ADDON_ID}/${ZIP_NAME}" 2>/dev/null || true
zip -r "$ZIP_NAME" "$ADDON_ID/" \
  --exclude "$ADDON_ID/.git/*" \
  --exclude "$ADDON_ID/.github/*" \
  --exclude "$ADDON_ID/.gitignore" \
  --exclude "$ADDON_ID/*.zip" \
  --exclude "$ADDON_ID/screenshot/*" \
  --exclude "$ADDON_ID/README.md"
mv "$ZIP_NAME" "$ADDON_ID/"
echo "Built: $ADDON_ID/$ZIP_NAME"
