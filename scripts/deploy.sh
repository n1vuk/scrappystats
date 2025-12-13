#!/usr/bin/env bash
set -e

export COMPOSE_PROJECT_NAME=scrappystats
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASES="$BASE_DIR/releases"

cd "$BASE_DIR"

# ---- ZIP SELECTION ----
if [[ -n "$1" ]]; then
  ZIP="$1"
else
  ZIP=$(ls -t scrappystats_*.zip 2>/dev/null | head -n 1)
fi

if [[ -z "$ZIP" || ! -f "$ZIP" ]]; then
  echo "❌ No ScrappyStats ZIP found."
  echo "   Usage: ./update.sh [scrappystats_vX.Y.Z.zip]"
  exit 1
fi

VERSION=$(basename "$ZIP" .zip)
TARGET="$RELEASES/$VERSION"

echo "📦 Installing $VERSION"
echo "📄 Using ZIP: $ZIP"

# ---- PREPARE RELEASE DIR ----
mkdir -p "$TARGET"
unzip -q "$ZIP" -d "$TARGET"

# ---- SANITY CHECKS (ENFORCE SOURCE OF RECORD) ----
[[ -f "$TARGET/docker-compose.yml" ]] || { echo "❌ docker-compose.yml missing"; exit 1; }
[[ -f "$TARGET/Dockerfile" ]] || { echo "❌ Dockerfile missing"; exit 1; }
[[ -f "$TARGET/supervisord.conf" ]] || { echo "❌ supervisord.conf missing"; exit 1; }
[[ -f "$TARGET/crontab" ]] || { echo "❌ crontab missing"; exit 1; }
[[ -d "$TARGET/app/scrappystats" ]] || { echo "❌ app/scrappystats missing"; exit 1; }

# ---- READ APP VERSION (AUTHORITATIVE) ----
APP_VERSION="unknown"
if [[ -f "$TARGET/VERSION" ]]; then
  APP_VERSION=$(cat "$TARGET/VERSION")
elif [[ -f "$TARGET/app/scrappystats/version.py" ]]; then
  APP_VERSION=$(grep -E "__version__" "$TARGET/app/scrappystats/version.py" | cut -d'"' -f2)
fi

# ---- OVERWRITE AUTHORITATIVE FILES ----
# echo "🧩 Applying authoritative deployment files"
# cp -f "$TARGET/docker-compose.yml" "$BASE_DIR/docker-compose.yml"

# ---- ATOMIC SWITCH ----
echo "🔁 Switching current symlink"
ln -sfn "$TARGET" "$BASE_DIR/current"

# ---- BUILD & RUN FROM CURRENT ----
### cd "$BASE_DIR/current"

echo "🐳 Building image"
docker compose build scrappystats

echo "🚀 Restarting service"
docker compose up -d scrappystats


# ---- OBSERVE ----
echo "📌 Deployed ScrappyStats version: $APP_VERSION"

WAIT_SECONDS=15
echo "⏳ Waiting ${WAIT_SECONDS}s for startup..."
sleep "$WAIT_SECONDS"

echo "📜 Tailing logs (Ctrl+C to exit)"
if [[ "${TAIL_LOGS:-true}" == "true" ]]; then
  docker compose logs -f scrappystats
fi
