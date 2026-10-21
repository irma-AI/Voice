#!/usr/bin/env bash
# Starts the Portal's local Postgres (compose.yml) and fails closed unless DATABASE_URL's port is the one it got,
# so a stale .env can't reach another project's Postgres (VOI-257). Docker itself refuses a taken port.
set -euo pipefail
port=${DATABASE_URL%/*}; port=${port##*:}
docker compose up -d --wait
published=$(docker compose port postgres 5432 || true)
if [ "${published##*:}" != "$port" ]; then
  echo "DATABASE_URL uses port $port, but Voice's Postgres is published at '${published:-nowhere}': fix DATABASE_URL in .env (see .env.example)" >&2
  exit 1
fi
