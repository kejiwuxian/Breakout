#!/usr/bin/env bash
# Offline-mode check before demo. Filled further in later prompts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "BREAKOUT preflight"
echo "  USE_CACHED_STREAM=${USE_CACHED_STREAM:-True}"
echo "  SCENARIO=${SCENARIO:-scenario_a_galactic_ccsn}"
echo "  LCOGT_DRY_RUN=${LCOGT_DRY_RUN:-True}"
echo "  VOICE_MODE=${VOICE_MODE:-live}"

missing=0
for path in \
  "data/cache/scenario_a_galactic_ccsn" \
  "data/cache/scenario_b_icecube_170922a" \
  "data/voice/announcer_lines.json" \
  "data/stars/curated_stars.json" \
  ".cursor/rules/astro-conventions.mdc"
do
  if [[ ! -e "$path" ]]; then
    echo "MISSING: $path"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "preflight FAIL"
  exit 1
fi

echo "preflight OK (scaffold)"
exit 0
