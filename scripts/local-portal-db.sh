#!/usr/bin/env bash
# Starts the Portal's local Postgres (compose.yml) and fails closed unless DATABASE_URL reaches that one,
# not another Postgres holding the same port (VOI-257). Run with the Portal's env loaded (`make portal-up`).
set -euo pipefail
addr=${DATABASE_URL:?DATABASE_URL is not set (see .env.example)}; addr=${addr##*@}; addr=${addr%%/*}; port=${addr##*:}
[[ $port =~ ^[0-9]+$ ]] || { echo "DATABASE_URL names no port ($addr): see .env.example" >&2; exit 1; }

holder() {
  local name; name=$(docker ps --filter "publish=$port" --format '{{.Names}}' | head -1)
  echo "${name:-a program outside Docker}"
}

# shortcut: another checkout's (a worktree's) Voice Postgres counts as someone else's and is refused, give compose.yml a fixed `name:` if checkouts should share one database.
if [ -z "$(docker compose ps -q --status running postgres)" ] && (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
  echo "Port $port (DATABASE_URL) is taken by $(holder), not Voice's Postgres: stop it, or check DATABASE_URL in .env against .env.example" >&2
  exit 1
fi
docker compose up -d --wait
published=$(docker compose port postgres 5432 || true)
if [ "${published##*:}" != "$port" ]; then
  echo "DATABASE_URL uses port $port, but Voice's Postgres is published at '${published:-nowhere}' (port $port held by $(holder)?): fix DATABASE_URL in .env, or free the port compose.yml publishes" >&2
  exit 1
fi
