#!/usr/bin/env bash
# Runs the auditor against every test scenario, plus the unit-style checks, in parallel.
#
# Usage (from anywhere):
#   bash tests/run-tests.sh                   everything (scenarios and checks), in parallel
#   bash tests/run-tests.sh --fast            the quick set: checks plus a few scenarios (about a minute)
#   bash tests/run-tests.sh expo-supabase-ai  just one (or several): scenario names or check names
#   bash tests/run-tests.sh --jobs 2          how many run at once (default: your CPU count, at most 4)
#   bash tests/run-tests.sh --serial          one at a time (same as --jobs 1), easier to read when debugging
#   bash tests/run-tests.sh --install         first install every missing scanner, then test
#   KEEP=1 bash tests/run-tests.sh            keep the test projects (in .test-work/) to inspect them
#
# Checks: report-check verdict-check html-check serve-check translate-check engine-check core-check detect-check digest-check modes-check helpers-check progress-check (see units.sh).
# Scenarios: tests/scenarios/<name>/ (see scenario.sh for the folder layout and expected.tsv format).
# Output is also saved to tests/last-run.txt.
#
# Results: PASS, FAIL, or UNTESTED (the tool isn't installed here, so the expectation couldn't be
# checked). Exit code is 1 if anything failed.
#
# How it works: each scenario or check runs as its own process (this script with --one <name>) in its
# own folder under .test-work/, writes its lines to .test-work/results/<name>.txt, and this script prints
# them in order and counts them.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
. "$HERE/lib.sh"
. "$HERE/units.sh"
. "$HERE/scenario.sh"

# The quick set: every check, plus scenarios that cover the main code paths without heavy scanners
FAST_SCENARIOS="clean-baseline monorepo-plain js-parser-crash astro-site release-hygiene ai-raw-fetch untrusted-trap"

# --- Child mode: run one scenario or check and print its lines
if [ "${1:-}" = "--one" ]; then
  name="$2"
  case " $UNITS " in
    *" $name "*) "unit_${name//-/_}" ;;
    *) run_scenario "$name" ;;
  esac
  exit 0
fi

# --- Parent mode
INSTALL=0; FAST=0; JOBS="${JOBS:-}"; NAMES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --install) INSTALL=1 ;;
    --fast) FAST=1 ;;
    --serial) JOBS=1 ;;
    --jobs) shift; JOBS="${1:-1}" ;;
    *) NAMES="$NAMES $1" ;;
  esac
  shift
done

if [ -z "$JOBS" ]; then
  JOBS="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)"
  [ "$JOBS" -gt 4 ] && JOBS=4
fi

if [ -n "$NAMES" ]; then LIST="$NAMES"
elif [ "$FAST" = 1 ]; then LIST="$UNITS $FAST_SCENARIOS"
else LIST="$UNITS $(ls "$HERE/scenarios" | tr '\n' ' ')"
fi

rm -rf "$WORK"; mkdir -p "$WORK/results"
# Ignore it via .git/info/exclude, not .gitignore: scanners such as osv-scanner obey a parent
# .gitignore and would skip the test projects entirely.
EXC="$REPO/.git/info/exclude"
grep -qx '.test-work/' "$EXC" 2>/dev/null || { mkdir -p "$(dirname "$EXC")"; echo '.test-work/' >> "$EXC"; }
exec > >(tee "$HERE/last-run.txt") 2>&1

if [ "$INSTALL" = 1 ]; then
  echo "=== Installing missing scanners"
  bash "$SCAN" --install all
  echo
fi

START="$(date +%s)"
export AUDIT_TEST_WORK="$WORK"
# shellcheck disable=SC2086
# Each one runs under a time limit (TEST_TIMEOUT seconds, default 300), so a hung test fails with a clear
# message instead of blocking the run. The ">>>" lines show live which ones started and finished.
. "$REPO/scripts/find-python.sh"
find_python || { echo "The tests need Python 3.8 or newer (none found)."; exit 1; }
export AUDIT_TEST_PY="$PYTHON"
# Several tests start the same npx tool at once, and two downloads into npm's shared cache corrupt it.
# So fetch the pinned npx tools once, one after another, before the parallel part.
if command -v npx >/dev/null 2>&1 && [ -z "${AUDIT_NO_PREWARM:-}" ]; then
  for pkg in $(grep -hE '^(MADGE|JSCPD)_PKG *=' "$REPO/scripts/audit_core.py" | cut -d'"' -f2); do
    echo "Fetching $pkg (once, before the parallel run)"
    npx --yes "$pkg" --version >/dev/null 2>&1 || true
  done
fi
printf '%s\n' $LIST | xargs -P "$JOBS" -I{} bash -c 'echo ">>> start $1" >&2; PYTHONUTF8=1 $AUDIT_TEST_PY "$3/with_timeout.py" "${TEST_TIMEOUT:-300}" "$2/results/$1.txt" bash "$3/run-tests.sh" --one "$1"; echo ">>> done $1 (exit $?)" >&2' _ {} "$WORK" "$HERE"

for n in $LIST; do
  echo
  if [ -s "$WORK/results/$n.txt" ]; then cat "$WORK/results/$n.txt"
  else echo "=== $n"; bad "$n ran" "it produced no output"; fi
done

PASS="$(cat "$WORK"/results/*.txt 2>/dev/null | grep -c '^  PASS')"
FAIL="$(cat "$WORK"/results/*.txt 2>/dev/null | grep -c '^  FAIL')"
UNTESTED="$(cat "$WORK"/results/*.txt 2>/dev/null | grep -c '^  UNTESTED')"
# A listed name that produced no output at all is a failure too
for n in $LIST; do [ -s "$WORK/results/$n.txt" ] || FAIL=$((FAIL+1)); done

echo
echo "RESULT: $PASS passed, $FAIL failed, $UNTESTED untested (tool not installed)   [$(( $(date +%s) - START ))s, $JOBS at a time]"
if [ "${KEEP:-0}" = "1" ]; then echo "Test projects kept in: $WORK"; else rm -rf "$WORK"; fi
[ "$FAIL" -eq 0 ]
