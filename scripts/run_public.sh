#!/usr/bin/env bash
# Start Project Supernova behind a Cloudflare tunnel (public HTTPS).
#
# Requires CLOUDFLARE_TUNNEL_TOKEN in the environment or gitignored .env
# (never commit the token; never pass it on argv in docs).
#
# Usage (from repo root):
#   bash scripts/run_public.sh
#
# Optional env:
#   BREAKOUT_PUBLIC_BASE_URL  default https://supernova.lylinks.com
#   BREAKOUT_API_HOST/PORT    local bind (default 127.0.0.1:8000)
#   BREAKOUT_SKIP_FRONTEND_BUILD=1  skip npm build when dist is fresh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer project venv + local cloudflared if present.
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi
if [[ -x "$ROOT/.local/bin/cloudflared" ]]; then
  export PATH="$ROOT/.local/bin:$PATH"
fi

# Load KEY=VALUE pairs from gitignored .env (never `source` — .env may contain
# commented run hints; bare commands must not execute).
load_dotenv_keys() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ""|\#*) continue ;;
    esac
    [[ "$line" == *=* ]] || continue
    local key="${line%%=*}"
    local val="${line#*=}"
    key="$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    # Strip inline comments and surrounding quotes.
    val="${val%%#*}"
    val="$(echo "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^["'\'']//;s/["'\'']$//')"
    # Only export simple ENV keys; skip shell-looking lines.
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    # Do not override variables already set in the process environment.
    if [[ -z "${!key+x}" ]]; then
      export "$key=$val"
    fi
  done < "$file"
}
load_dotenv_keys "$ROOT/.env"

TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "ERROR: CLOUDFLARE_TUNNEL_TOKEN is not set." >&2
  echo "Add it to .env (gitignored) or export it in this shell. See .env.example." >&2
  exit 1
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "ERROR: cloudflared not found on PATH." >&2
  echo "Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  echo "Or place a binary at $ROOT/.local/bin/cloudflared" >&2
  exit 1
fi

export ENV="${ENV:-production}"
export BREAKOUT_ENV="${BREAKOUT_ENV:-production}"
export BREAKOUT_PUBLIC="${BREAKOUT_PUBLIC:-1}"
export BREAKOUT_PUBLIC_BASE_URL="${BREAKOUT_PUBLIC_BASE_URL:-https://supernova.lylinks.com}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-$BREAKOUT_PUBLIC_BASE_URL}"
export BREAKOUT_SERVE_FRONTEND="${BREAKOUT_SERVE_FRONTEND:-1}"
export USE_CACHED_STREAM="${USE_CACHED_STREAM:-True}"
export VOICE_MODE="${VOICE_MODE:-off}"
export LCOGT_DRY_RUN="${LCOGT_DRY_RUN:-True}"

API_HOST="${BREAKOUT_API_HOST:-127.0.0.1}"
API_PORT="${BREAKOUT_API_PORT:-8000}"

DIST="$ROOT/frontend/dist/index.html"
SPACEX_DIST="$ROOT/frontend-spacex/dist/index.html"
if [[ "${BREAKOUT_SKIP_FRONTEND_BUILD:-0}" != "1" ]]; then
  if [[ ! -f "$DIST" ]] || [[ "${BREAKOUT_FORCE_FRONTEND_BUILD:-0}" == "1" ]]; then
    echo "Building frontend for single-origin static serve…"
    npm --prefix frontend run build
  else
    echo "Using existing frontend/dist (set BREAKOUT_FORCE_FRONTEND_BUILD=1 to rebuild)."
  fi
  if [[ ! -f "$SPACEX_DIST" ]] || [[ "${BREAKOUT_FORCE_FRONTEND_BUILD:-0}" == "1" ]]; then
    echo "Building SpaceX-track frontend (/spacex)…"
    npm --prefix frontend-spacex install
    npm --prefix frontend-spacex run build
  else
    echo "Using existing frontend-spacex/dist."
  fi
fi

if [[ ! -f "$DIST" ]]; then
  echo "ERROR: frontend/dist missing; cannot serve UI from the API process." >&2
  exit 1
fi

cleanup() {
  local code=$?
  if [[ -n "${UVICORN_PID:-}" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
  if [[ -n "${TUNNEL_PID:-}" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

echo "Starting uvicorn on ${API_HOST}:${API_PORT} (public_base_url=${BREAKOUT_PUBLIC_BASE_URL})"
python -m uvicorn backend.app:app --host "$API_HOST" --port "$API_PORT" &
UVICORN_PID=$!

# Wait for local health before bringing the tunnel up.
for _ in $(seq 1 60); do
  if curl -fsS "http://${API_HOST}:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
if ! curl -fsS "http://${API_HOST}:${API_PORT}/health" >/dev/null; then
  echo "ERROR: local /health did not become ready." >&2
  exit 1
fi
echo "Local API healthy."

# Token from env/.env only — never echo it. Unset from the environment before
# exec so cloudflared does not dump CLOUDFLARE_TUNNEL_TOKEN in its settings log.
echo "Starting Cloudflare tunnel (token redacted)…"
unset CLOUDFLARE_TUNNEL_TOKEN
cloudflared tunnel --no-autoupdate run --token "$TOKEN" &
TUNNEL_PID=$!
# Drop shell copy after spawn (child already received argv).
TOKEN=""

sleep 2
if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
  echo "ERROR: cloudflared exited immediately — check token / Zero Trust config." >&2
  exit 1
fi
echo "cloudflared running (pid=${TUNNEL_PID}). Public host: ${BREAKOUT_PUBLIC_BASE_URL}"
echo "Try: curl -fsS ${BREAKOUT_PUBLIC_BASE_URL}/health"

wait
