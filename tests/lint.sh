#!/usr/bin/env bash
# Quick checks that catch typing mistakes before the real tests run (a few seconds):
#   - every shell script parses (bash -n) and has Unix line endings
#   - every Python file parses; Ruff (if installed) reports real errors (not style)
#   - ShellCheck (if installed) reports errors
#   - the JavaScript inside the web page parses (node --check), and every label it asks for exists in
#     both languages
# Usage: bash tests/lint.sh          Exit code 1 if anything failed.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$REPO" || exit 1
. "$REPO/scripts/find-python.sh"
FAILS=0
pass() { printf "  OK    %s\n" "$1"; }
note() { printf "  skip  %s\n" "$1"; }
fail() { printf "  FAIL  %s\n" "$1"; FAILS=$((FAILS+1)); }

if ! find_python; then fail "Python 3.8+ not found (needed for the checks below)"; exit 1; fi

echo "Shell scripts"
SH_FILES="$(find scripts tests -name '*.sh' -not -path '*/node_modules/*' -not -path '*/.test-work/*' | sort)"
bad=0
for f in $SH_FILES; do
  if ! bash -n "$f" 2>/dev/null; then fail "$f does not parse (bash -n)"; bad=1; fi
  if grep -q "$(printf '\r')" "$f"; then fail "$f has Windows line endings (CRLF); scripts must use LF"; bad=1; fi
done
[ $bad -eq 0 ] && pass "$(echo "$SH_FILES" | wc -l | tr -d ' ') shell scripts parse and use LF"
if command -v shellcheck >/dev/null 2>&1; then
  # shellcheck disable=SC2086
  if shellcheck -s bash -S error $SH_FILES >/tmp/shellcheck.out 2>&1; then pass "ShellCheck: no errors"; else fail "ShellCheck found errors (see below)"; head -30 /tmp/shellcheck.out; fi
else note "ShellCheck not installed (CI runs it)"; fi

# GNU-only habits that break on macOS (BSD sed has a different -i; grep -P does not exist)
gnu="$(grep -nE "sed -i|grep -[a-zA-Z]*P" $SH_FILES | grep -v "^tests/lint.sh" || true)"
if [ -n "$gnu" ]; then fail "GNU-only commands (sed -i, grep -P) break on macOS: $gnu"; else pass "no GNU-only sed -i or grep -P in the scripts"; fi

echo "Test runner"
# An option the runner does not know used to be taken for a test name and started (and wiped) a real run.
out="$(bash tests/run-tests.sh --no-such-option 2>&1)"; code=$?
case "$out" in *Usage*) has_usage=1 ;; *) has_usage=0 ;; esac
if [ "$code" -ne 0 ] && [ "$has_usage" = 1 ]; then pass "run-tests.sh refuses an unknown option and prints the usage"; else fail "run-tests.sh must refuse an unknown option and print the usage (exit $code)"; fi
out="$(bash tests/run-tests.sh --help 2>&1)"; code=$?
case "$out" in *Usage*) has_usage=1 ;; *) has_usage=0 ;; esac
if [ "$code" -eq 0 ] && [ "$has_usage" = 1 ]; then pass "run-tests.sh --help prints the usage and runs nothing"; else fail "run-tests.sh --help must print the usage and exit 0 (exit $code)"; fi

echo "Python"
PY_FILES="$(find scripts tests -name '*.py' -not -path '*/node_modules/*' -not -path '*/.test-work/*' | sort)"
bad=0
for f in $PY_FILES; do
  if ! PYTHONUTF8=1 $PYTHON -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" "$f" 2>/dev/null; then fail "$f does not parse"; bad=1; fi
done
[ $bad -eq 0 ] && pass "$(echo "$PY_FILES" | wc -l | tr -d ' ') Python files parse"
if PYTHONUTF8=1 $PYTHON -m ruff --version >/dev/null 2>&1; then
  # E9: syntax errors, F: unused names and undefined names, E7: statement problems
  # shellcheck disable=SC2086
  if PYTHONUTF8=1 $PYTHON -m ruff check --select E9,F,E7 --no-cache $PY_FILES >/tmp/ruff.out 2>&1; then pass "Ruff: no errors"; else fail "Ruff found problems (see below)"; head -30 /tmp/ruff.out; fi
else note "Ruff not installed (pip install ruff)"; fi

echo "Web page"
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t lint)"
mkdir -p "$TMP/p/audit/2026-01-01_000000"
RUN="$TMP/p/audit/2026-01-01_000000"
printf 'tool\tstatus\texit\toutput\tdimension\ngitleaks\tclean\t0\tg.json\tsecurity\n' > "$RUN/manifest.tsv"
printf 'date=2026-01-01\ncommit=abc\n' > "$RUN/meta.txt"
if PYTHONUTF8=1 $PYTHON "$REPO/scripts/audit_report_html.py" "$RUN" >/dev/null 2>&1; then
  pass "the page builds"
  if command -v node >/dev/null 2>&1; then
    PYTHONUTF8=1 $PYTHON -c "
import re, sys
t = open(sys.argv[1], encoding='utf-8').read()
open(sys.argv[2], 'w', encoding='utf-8').write(re.findall(r'<script>(.*?)</script>', t, re.S)[-1])" "$RUN/report.html" "$TMP/page.js"
    if node --check "$TMP/page.js" 2>"$TMP/node.err"; then pass "the page's JavaScript parses"; else fail "the page's JavaScript has a syntax error"; head -5 "$TMP/node.err"; fi
  else note "node not installed: page JavaScript not checked"; fi
  # every label the page script or markup asks for exists in English and French
  if PYTHONUTF8=1 $PYTHON -c "
import re, sys
sys.path.insert(0, sys.argv[1])
import audit_report_html as m
page = m.PAGE
keys = set(re.findall(r\"\\bt\\('([a-z_0-9]+)'[,)]\", page)) | set(re.findall(r'data-i18n(?:-ph)?=\"([a-z_0-9]+)\"', page))
missing = sorted(k for k in keys if k not in m.I18N['en'] or k not in m.I18N['fr'])
print(' '.join(missing)); sys.exit(1 if missing else 0)" "$REPO/scripts" >"$TMP/keys.out" 2>&1; then pass "every label used by the page exists in English and French"; else fail "labels missing in a language: $(cat "$TMP/keys.out")"; fi
else fail "the page does not build"; fi
rm -rf "$TMP"

echo
if [ $FAILS -eq 0 ]; then echo "LINT OK"; else echo "LINT FOUND $FAILS PROBLEM(S)"; fi
[ $FAILS -eq 0 ]
