#!/bin/bash
# Sign CAHON.app with a Developer ID for notarization (hardened runtime, secure timestamp).
#
#   packaging/macos/sign.sh dist/CAHON.app "Developer ID Application: Name (TEAMID)"
#
# Every Mach-O file inside (Python's .so/.dylib, the Rust readers, Tesseract and its
# libraries in Resources) is signed first, deepest path first, then the app itself.
# `codesign --deep` would miss the binaries kept in Contents/Resources, and Apple's
# notary service rejects a bundle with any unsigned binary in it.
set -euo pipefail
APP="$1"
IDENTITY="$2"
ENT="$(cd "$(dirname "$0")" && pwd)/entitlements.plist"
SIGN=(codesign --force --timestamp --options runtime --entitlements "$ENT" --sign "$IDENTITY")

list="$(mktemp)"
find "$APP/Contents" -type f ! -path "*/Contents/MacOS/CAHON" -print0 |
  while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q "Mach-O"; then printf '%s\t%s\n' "${#f}" "$f"; fi
  done | sort -rn | cut -f2- > "$list"
echo "signing $(wc -l < "$list" | tr -d ' ') binaries inside the app"
while IFS= read -r f; do "${SIGN[@]}" "$f"; done < "$list"
rm -f "$list"
"${SIGN[@]}" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
