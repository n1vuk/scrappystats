#!/usr/bin/env bash
set -euo pipefail

# =============================
# Configuration
# =============================
APP_NAME="scrappystats"
BUILD_DIR="dist"
VERSION_FILE="VERSION"

# ---- optional deploy settings ----
DEPLOY_ENABLED=true
DEPLOY_USER="root"
DEPLOY_HOST="boboandscrappy.com"
DEPLOY_PORT=2792
DEPLOY_PATH="/root/docker/scrappystats"

# =============================
# Sanity checks
# =============================

if ! git describe --tags --exact-match >/dev/null 2>&1; then
  echo "❌ ERROR: You must be on a tagged commit to build a release."
  exit 1
fi

TAG=$(git describe --tags --exact-match)
VERSION="${TAG#v}"

echo "📦 Building release for tag: $TAG"

# =============================
# Build
# =============================

TAG=$(git describe --tags --exact-match)
VERSION="${TAG#v}"

echo "Building release for tag $TAG"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

TMP_DIR="$(mktemp -d)"
ARCHIVE_NAME="${APP_NAME}_v${VERSION}.zip"
ARCHIVE_PATH="$(pwd)/$BUILD_DIR/$ARCHIVE_NAME"

# Export source from tags
git archive "$TAG" | tar -x -C "$TMP_DIR"

# Inject correct VERSION
echo "$VERSION" > "$TMP_DIR/VERSION"

# Create zip
(
  cd "$TMP_DIR"
  zip -qr "$ARCHIVE_PATH" .
)

rm -rf "$TMP_DIR"

echo "Release created: $ARCHIVE_PATH"

# Optional transfer
if [[ "$DEPLOY_ENABLED" == "true" ]]; then
  scp -P "$DEPLOY_PORT" \
    "$ARCHIVE_PATH" \
    "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"
  echo "Transferred to server"
fi
