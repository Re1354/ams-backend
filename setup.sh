#!/usr/bin/env bash
# ==========================================================================
#  ONE-TIME VPS bootstrap. Run this once, from the backend repo, before the
#  first deploy of ANY app. It creates the shared docker network and starts
#  the reverse proxy + Let's Encrypt SSL companion.
#
#  Re-running it is safe (idempotent).
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run:  cp .env.example .env  then edit it." >&2
  exit 1
fi

echo ">> Creating shared 'web' docker network (if missing)..."
docker network inspect web >/dev/null 2>&1 || docker network create web

echo ">> Starting reverse proxy + SSL companion..."
docker compose -f docker-compose.proxy.yml --env-file .env up -d

echo ""
echo "Done. The reverse proxy is running on ports 80/443."
echo "Next: run ./deploy.sh here, then deploy the two frontends."
