#!/usr/bin/env bash
# Offline-mode check before demo (venue Wi-Fi off).
# Verifies .env flags, cache artifacts (including voice clips), literature
# index, then runs tests/test_offline.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi

echo "BREAKOUT preflight"

fail=0

ENV_FILE=".env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "FAIL: missing .env (copy from .env.example)"
  fail=1
else
  # shellcheck disable=SC1091
  set -a
  # Read KEY=VALUE lines; ignore comments/blank.
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ""|\#*) continue ;;
    esac
    if [[ "$line" == *=* ]]; then
      key="${line%%=*}"
      val="${line#*=}"
      val="${val%%#*}"
      val="$(echo "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      export "$key=$val"
    fi
  done < "$ENV_FILE"
  set +a

  ucs="$(echo "${USE_CACHED_STREAM:-}" | tr '[:upper:]' '[:lower:]')"
  dry="$(echo "${LCOGT_DRY_RUN:-}" | tr '[:upper:]' '[:lower:]')"
  echo "  USE_CACHED_STREAM=${USE_CACHED_STREAM:-}"
  echo "  LCOGT_DRY_RUN=${LCOGT_DRY_RUN:-}"
  echo "  VOICE_MODE=${VOICE_MODE:-}"
  if [[ "$ucs" != "true" && "$ucs" != "1" && "$ucs" != "yes" ]]; then
    echo "FAIL: .env USE_CACHED_STREAM must be True (got ${USE_CACHED_STREAM:-empty})"
    fail=1
  fi
  if [[ "$dry" != "true" && "$dry" != "1" && "$dry" != "yes" ]]; then
    echo "FAIL: .env LCOGT_DRY_RUN must be True (got ${LCOGT_DRY_RUN:-empty})"
    fail=1
  fi
fi

require_file() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "FAIL: missing $path"
    fail=1
  fi
}

require_file "data/cache/scenario_a_galactic_ccsn/alerts.jsonl"
require_file "data/cache/scenario_b_icecube_170922a/alerts.jsonl"
require_file "data/voice/announcer_lines.json"
require_file "data/stars/curated_stars.json"
require_file "backend/literature/index.parquet"
require_file ".cursor/rules/astro-conventions.mdc"

# Voice clips for both scenarios (at least one MP3 each; A needs 0-4, B 0-3).
for scenario in scenario_a_galactic_ccsn scenario_b_icecube_170922a; do
  vdir="data/cache/${scenario}/voice"
  if [[ ! -d "$vdir" ]]; then
    echo "FAIL: missing $vdir"
    fail=1
    continue
  fi
  shopt -s nullglob
  clips=("$vdir"/*.mp3)
  shopt -u nullglob
  if [[ ${#clips[@]} -lt 1 ]]; then
    echo "FAIL: no MP3 clips in $vdir (run announcer --prerender ${scenario})"
    fail=1
  else
    echo "  voice clips ${scenario}: ${#clips[@]} file(s)"
  fi
done

# Scenario A expected 5 clips; B expected 4.
for i in 0 1 2 3 4; do
  require_file "data/cache/scenario_a_galactic_ccsn/voice/${i}.mp3"
done
for i in 0 1 2 3; do
  require_file "data/cache/scenario_b_icecube_170922a/voice/${i}.mp3"
done

if [[ "$fail" -ne 0 ]]; then
  echo "FAIL"
  exit 1
fi

echo "Running offline tests (network must stay unused)…"
export USE_CACHED_STREAM=True
export VOICE_MODE=cached
export LCOGT_DRY_RUN=True
export BREAKOUT_DISABLE_AUTOSTART=1
if ! python -m pytest tests/test_offline.py -q; then
  echo "FAIL: tests/test_offline.py"
  exit 1
fi

echo "PASS"
exit 0
