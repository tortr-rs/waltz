#!/usr/bin/env bash
# Builds a release tarball: everything install.sh needs, in one file, so
# getting Waltz is "download, extract, ./install.sh" instead of assembling
# the source tree and each system dependency by hand.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT_DIR'); from waltz import __version__; print(__version__)")"
NAME="waltz-${VERSION}"

DIST_DIR="$ROOT_DIR/dist"
STAGE_DIR="$DIST_DIR/$NAME"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"

cp -r "$ROOT_DIR/waltz" "$STAGE_DIR/"
cp -r "$ROOT_DIR/bin" "$STAGE_DIR/"
cp -r "$ROOT_DIR/scripts" "$STAGE_DIR/"
cp "$ROOT_DIR/waltz.desktop" "$STAGE_DIR/"
cp "$ROOT_DIR/README.md" "$STAGE_DIR/"

# waltzer-white ships as source, not a prebuilt binary — a binary built on
# this machine isn't guaranteed to work on the installer's architecture or
# glibc version. install.sh builds it from this on first install instead.
mkdir -p "$STAGE_DIR/waltzer-white"
cp -r "$ROOT_DIR/waltzer-white/src" "$ROOT_DIR/waltzer-white/Cargo.toml" \
      "$ROOT_DIR/waltzer-white/Cargo.lock" "$STAGE_DIR/waltzer-white/"

find "$STAGE_DIR" \( -name "__pycache__" -o -name "target" \) -type d -prune -exec rm -rf {} +
chmod +x "$STAGE_DIR/bin/waltz" "$STAGE_DIR/scripts/install.sh" "$STAGE_DIR/scripts/make-dist.sh"

tar -C "$DIST_DIR" -czf "$DIST_DIR/${NAME}.tar.gz" "$NAME"
rm -rf "$STAGE_DIR"

echo "Built $DIST_DIR/${NAME}.tar.gz"
