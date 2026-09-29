#!/usr/bin/env bash
# ==========================================================================
#  Deploy / redeploy the AMS-DIU backend (Django) + its PostgreSQL.
#  Safe to run on every push: the database volume is preserved, only the
#  app image is rebuilt and migrations are applied.
#
#  Usage:   ./deploy.sh
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run:  cp .env.example .env  then edit it." >&2
  exit 1
fi

echo ">> Ensuring shared 'web' network exists..."
docker network inspect web >/dev/null 2>&1 || docker network create web

echo ">> Pulling latest code..."
git pull --ff-only || echo "   (skipping git pull — not a fast-forward or no upstream)"

echo ">> Building and starting backend + postgres..."
# NOTE: never use 'down -v' here — that would delete the database volume.
docker compose --env-file .env up -d --build

echo ">> Cleaning up dangling images..."
docker image prune -f >/dev/null 2>&1 || true

echo ""
echo ">> Status:"
docker compose ps
echo ""
echo "Backend deployed -> https://$((grep -E '^API_DOMAIN=' .env || true) | cut -d= -f2 | tr -d '\r')"
echo "Tip: create an admin user with:"
echo "  docker compose exec web sh -c 'cd amsapp && python manage.py createsuperuser'"
