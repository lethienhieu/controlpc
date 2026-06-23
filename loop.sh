#!/usr/bin/env bash
# =============================================================================
# loop.sh — a loop-engineering driver for CONTROLPC.
#
# Runs the project's SUCCESS GATES in a loop until they ALL pass (or until
# MAX_ATTEMPTS is exhausted). This is the "agentic loop" applied to the project
# itself: explicit success criteria, cheapest gate first (fast feedback),
# bounded retries (never infinite), idempotent (safe to re-run).
#
#   Gate 1  frontend lint      (eslint, zero warnings)        — ~1s
#   Gate 2  frontend tests     (vitest)                        — ~2s
#   Gate 3  backend tests      (policy/tools/remote/...)       — ~5s
#   Gate 4  control self-check (boots the GPU agent, opens &   — ~30s
#           verifies real apps via selfcheck.py)
#
# Usage:
#   bash loop.sh                     # 5 attempts, all gates
#   MAX_ATTEMPTS=3 bash loop.sh      # custom attempt cap
#   SKIP_CONTROL=1 bash loop.sh      # skip the GPU/desktop control gate (CI-safe)
#
# Exit 0 once every gate passes; exit 1 if still failing after MAX_ATTEMPTS.
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve the project's Python (venv first, then fallbacks).
PY="$ROOT/backend/venv/Scripts/python.exe"            # Windows venv
[ -x "$PY" ] || PY="$ROOT/backend/venv/bin/python"    # POSIX venv
[ -x "$PY" ] || PY="$(command -v python || command -v python3)"

MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}"
BACKEND_TESTS="test_policy test_tools test_remote test_smoke test_email test_messaging test_planner"

export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

c_cyan='\033[1;36m'; c_grn='\033[1;32m'; c_red='\033[1;31m'; c_off='\033[0m'
log() { printf "${c_cyan}[loop %s]${c_off} %s\n" "$(date +%H:%M:%S)" "$*"; }
ok()  { printf "  ${c_grn}PASS${c_off} %s\n" "$*"; }
bad() { printf "  ${c_red}FAIL${c_off} %s\n" "$*"; }

# One-time bootstrap so a fresh checkout doesn't fail confusingly.
[ -d "$ROOT/frontend/node_modules" ] || { log "installing frontend deps…"; ( cd "$ROOT/frontend" && npm install ); }

# Run every gate once. Returns non-zero on the FIRST gate that fails (so a broken
# cheap gate gives feedback in seconds instead of after a 30s GPU run).
run_gates() {
  log "gate 1/4 — frontend lint (zero warnings)"
  if ( cd "$ROOT/frontend" && npx eslint . --max-warnings 0 ); then ok "lint clean"; else bad "eslint"; return 1; fi

  log "gate 2/4 — frontend tests (vitest)"
  if npm --prefix "$ROOT/frontend" test --silent; then ok "npm test"; else bad "npm test"; return 1; fi

  log "gate 3/4 — backend tests"
  for t in $BACKEND_TESTS; do
    if "$PY" "$ROOT/$t.py" >"/tmp/loop_$t.log" 2>&1; then ok "$t"; else bad "$t  (log: /tmp/loop_$t.log)"; return 1; fi
  done

  if [ "${SKIP_CONTROL:-0}" = "1" ]; then log "gate 4/4 — control self-check SKIPPED (SKIP_CONTROL=1)"; return 0; fi
  log "gate 4/4 — control self-check (real GPU agent controls the PC)"
  if "$PY" "$ROOT/selfcheck.py"; then ok "control self-check"; else bad "control self-check"; return 1; fi
  return 0
}

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  log "================ attempt $attempt / $MAX_ATTEMPTS ================"
  if run_gates; then
    printf "${c_grn}[loop %s] ✅ SUCCESS — all gates passed on attempt %s${c_off}\n" "$(date +%H:%M:%S)" "$attempt"
    exit 0
  fi
  log "attempt $attempt failed — retrying in 2s (transient/cold issues self-heal; real bugs need a fix)"
  attempt=$((attempt + 1))
  sleep 2
done

printf "${c_red}[loop %s] ❌ FAILURE — gates still red after %s attempts. Fix the reported gate, then re-run.${c_off}\n" "$(date +%H:%M:%S)" "$MAX_ATTEMPTS"
exit 1
