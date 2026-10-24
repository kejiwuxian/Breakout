#!/usr/bin/env bash
# MVP gate: prints PASS or FAIL. Full suite wired in later prompts.
# At scaffold time only health is required to be green.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "BREAKOUT MVP gate"

fail=0

if [[ ! -f .cursor/rules/astro-conventions.mdc ]]; then
  echo "FAIL: missing .cursor/rules/astro-conventions.mdc"
  fail=1
fi

if [[ ! -f docs/prompt-log.md ]]; then
  echo "FAIL: missing docs/prompt-log.md"
  fail=1
fi

if ! python -m pytest tests/test_health.py -q; then
  echo "FAIL: pytest tests/test_health.py"
  fail=1
fi

# Placeholders for full gate (later prompts):
#   test_e2e, scenario tests, test_actions, test_voice, test_offline, Playwright

if [[ "$fail" -ne 0 ]]; then
  echo "FAIL"
  exit 1
fi

echo "PASS (scaffold health only; full gate not yet armed)"
exit 0
