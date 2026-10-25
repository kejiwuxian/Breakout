#!/usr/bin/env bash
# MVP gate: prints PASS or FAIL with failing items listed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# Prefer project venv so gate works outside activated shells.
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  export PATH="$ROOT/.venv/bin:$PATH"
fi

echo "BREAKOUT MVP gate"

fail=0
failures=()

note_fail() {
  local msg="$1"
  echo "FAIL: $msg"
  failures+=("$msg")
  fail=1
}

# Required docs must be tracked in git.
if [[ ! -f .cursor/rules/astro-conventions.mdc ]]; then
  note_fail "missing .cursor/rules/astro-conventions.mdc"
elif ! git ls-files --error-unmatch .cursor/rules/astro-conventions.mdc >/dev/null 2>&1; then
  note_fail ".cursor/rules/astro-conventions.mdc not tracked in git"
fi

if [[ ! -f docs/prompt-log.md ]]; then
  note_fail "missing docs/prompt-log.md"
elif ! git ls-files --error-unmatch docs/prompt-log.md >/dev/null 2>&1; then
  note_fail "docs/prompt-log.md not tracked in git"
fi

export USE_CACHED_STREAM="${USE_CACHED_STREAM:-True}"
export VOICE_MODE="${VOICE_MODE:-cached}"
export LCOGT_DRY_RUN="${LCOGT_DRY_RUN:-True}"
export BREAKOUT_DISABLE_AUTOSTART=1
export SCENARIO="${SCENARIO:-scenario_a_galactic_ccsn}"

# Prefer python3 when `python` is absent (common on minimal images).
if command -v python >/dev/null 2>&1; then
  PY=python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  echo "FAIL: neither python nor python3 found"
  fail=1
  PY=
fi

if [[ -n "$PY" ]]; then
  if ! "$PY" -m pytest tests/test_health.py -q; then
    echo "FAIL: pytest tests/test_health.py"
    fail=1
  fi
  if [[ -f tests/test_flags_off.py ]]; then
    if ! "$PY" -m pytest tests/test_flags_off.py -q; then
      echo "FAIL: pytest tests/test_flags_off.py"
      fail=1
    fi
  fi
fi


run_pytest() {
  local label="$1"
  shift
  echo "→ pytest $*"
  if ! python -m pytest "$@" -q; then
    note_fail "$label"
  fi
}

run_pytest "tests/test_e2e.py" tests/test_e2e.py
run_pytest "scenario tests" tests/test_scenario_betelgeuse.py tests/test_scenario_icecube.py
run_pytest "tests/test_actions.py" tests/test_actions.py
run_pytest "tests/test_notify.py" tests/test_notify.py
run_pytest "tests/test_voice.py" tests/test_voice.py
run_pytest "tests/test_offline.py" tests/test_offline.py

echo "→ Playwright e2e (tests/e2e_ui.spec.ts)"
if ! npm run test:e2e; then
  note_fail "Playwright tests/e2e_ui.spec.ts"
fi

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "FAILING ITEMS:"
  for item in "${failures[@]}"; do
    echo "  - $item"
  done
  echo "FAIL"
  exit 1
fi

echo "PASS"
exit 0
