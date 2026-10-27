#!/usr/bin/env bash
# Checks a finished audit report for mistakes a person (or Claude) can make while writing it.
#   bash verify-report.sh [audit-folder]     default: the latest run in ./audit/
# Looks at AUDIT.md, scores.json and manifest.tsv in that folder. Prints PASS / WARN / FAIL lines and
# exits 1 if anything FAILED. Changes nothing. It never prints the text it matched (a secret would
# end up in the output), only where it was found.
#   1. scores.json is valid and has every field, with sensible values
#   2. the verdict is allowed for the level and mode (see reviews/release-gate.md)
#   3. AUDIT.md names the same verdict, and its checklist marks add up to the counts in scores.json
#   4. every tool named with a status in AUDIT.md exists in manifest.tsv with that status
#   5. no secret-looking text in AUDIT.md or scores.json

set -u
has() { command -v "$1" >/dev/null 2>&1; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Same helper as in scan.sh: evaluate an expression over a JSON file with node, or Python.
#   json_eval <file> <js expression using d> <python expression using d>
json_eval() {
  if has node; then node -e 'const d=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log(('"$2"'))' "$1" 2>/dev/null; return; fi
  local py; for py in python3 python; do
    if has "$py" && "$py" -c 'import json' >/dev/null 2>&1; then
      "$py" -c 'import json,sys;d=json.load(open(sys.argv[1],encoding="utf-8"));print('"$3"')' "$1" 2>/dev/null; return
    fi
  done
}

DIR="${1:-}"
if [ -z "$DIR" ] && [ -f audit/latest.txt ]; then DIR="$(cat audit/latest.txt)"; fi
if [ -z "$DIR" ] || [ ! -d "$DIR" ]; then echo "FAIL: no audit folder (pass one, or run the scan first)"; exit 1; fi
R="$DIR/AUDIT.md"; S="$DIR/scores.json"; M="$DIR/manifest.tsv"
FAILS=0
pass() { echo "PASS: $1"; }
warn() { echo "WARN: $1"; }
fail() { echo "FAIL: $1"; FAILS=$((FAILS+1)); }

if [ -f "$R" ]; then pass "AUDIT.md exists"; else fail "AUDIT.md is missing in $DIR"; fi
if [ ! -f "$S" ]; then fail "scores.json is missing in $DIR"; exit 1; fi
if [ -z "$(json_eval "$S" 'typeof d' '"object"')" ]; then fail "scores.json is not valid JSON"; exit 1; fi
pass "scores.json is valid JSON"

get() { json_eval "$S" "$1" "$2"; }
MODE="$(get 'd.mode' 'd.get("mode")')"
LEVEL="$(get 'd.level' 'd.get("level")')"
VERDICT="$(get 'd.verdict' 'd.get("verdict")')"
RUBRIC="$(get 'd.rubric' 'd.get("rubric")')"

# 1. fields
case "$MODE" in quick|full) pass "mode is $MODE" ;; *) fail "mode must be quick or full (found: ${MODE:-none})" ;; esac
case "$LEVEL" in 1|2|3) pass "level is $LEVEL" ;; *) fail "level must be 1, 2 or 3 (found: ${LEVEL:-none})" ;; esac
case "$VERDICT" in
  dont-launch|launch-with-limits|no-blocking-problems) pass "verdict is $VERDICT" ;;
  *) fail "verdict must be dont-launch, launch-with-limits or no-blocking-problems (found: ${VERDICT:-none})" ;;
esac
case "$RUBRIC" in ""|undefined|None) fail "rubric is missing" ;; *) pass "rubric is $RUBRIC" ;; esac
BAD="$(get '["architecture","modularity","spaghettiness","security","quality","scalability","documentation"].filter(k=>{const v=(d.scores||{})[k];return !(v===null||(Number.isInteger(v)&&v>=0&&v<=100))}).join(",")' \
  '",".join(k for k in ["architecture","modularity","spaghettiness","security","quality","scalability","documentation"] if not (k in d.get("scores",{}) and (d["scores"][k] is None or (isinstance(d["scores"][k],int) and 0<=d["scores"][k]<=100))))')"
if [ -z "$BAD" ]; then pass "all seven scores are 0-100 or null"; else fail "scores missing or out of range: $BAD"; fi
CK="$(get '["pass","fail","partial","not_verified","not_applicable"].map(k=>(d.checklist||{})[k]).join(" ")' \
  '" ".join(str(d.get("checklist",{}).get(k)) for k in ["pass","fail","partial","not_verified","not_applicable"])')"
case "$CK" in *undefined*|*None*|"") fail "checklist counts are missing in scores.json"; CK="0 0 0 0 0" ;; *) pass "checklist counts present ($CK)" ;; esac
set -- $CK
C_PASS="${1:-0}"; C_FAIL="${2:-0}"; C_PART="${3:-0}"; C_NV="${4:-0}"; C_NA="${5:-0}"
SEC="$(get 'd.scores && d.scores.security' 'd.get("scores",{}).get("security")')"

# 2. verdict rules
if [ "$VERDICT" = "no-blocking-problems" ]; then
  if [ "$C_FAIL" -eq 0 ]; then pass "green verdict has no failed checklist items"; else fail "green verdict but $C_FAIL checklist item(s) failed"; fi
  if [ "$MODE" = quick ] && [ "$LEVEL" != 1 ]; then fail "a quick audit of a Level 2 or 3 project cannot be green (most Claude-checked items stay unverified)"; fi
  if [ "$LEVEL" = 3 ]; then fail "Level 3 cannot be green without the specialist items in reviews/release-gate.md"; fi
  case "$SEC" in ""|None|undefined|null) ;; *) if [ "$SEC" -lt 60 ] 2>/dev/null; then fail "green verdict but Security is $SEC (below 60)"; fi ;; esac
fi

# 3. the report says the same thing
if [ -f "$R" ]; then
  case "$VERDICT" in
    dont-launch)          PHRASE="Don't launch yet" ;;
    launch-with-limits)   PHRASE="Launch with limits" ;;
    no-blocking-problems) PHRASE="No blocking problems found" ;;
    *) PHRASE="" ;;
  esac
  if [ -n "$PHRASE" ]; then
    if grep -qF "$PHRASE" "$R"; then pass "AUDIT.md states the verdict ($PHRASE)"; else fail "AUDIT.md does not contain the verdict text '$PHRASE'"; fi
  fi
  ROWS="$(grep -E '^\|[[:space:]]*[0-9]+[[:space:]]*\|' "$R")"
  if [ -n "$ROWS" ]; then
    n_of() { printf '%s\n' "$ROWS" | grep -o "$1" | wc -l | tr -d ' '; }
    R_PASS="$(n_of '✅')"; R_FAIL="$(n_of '❌')"; R_PART="$(n_of '⚠️')"; R_NV="$(n_of '❓')"; R_NA="$(n_of '➖')"
    if [ "$R_PASS $R_FAIL $R_PART $R_NV $R_NA" = "$C_PASS $C_FAIL $C_PART $C_NV $C_NA" ]; then
      pass "checklist marks in AUDIT.md match scores.json"
    else
      fail "checklist marks in AUDIT.md ($R_PASS pass, $R_FAIL fail, $R_PART partial, $R_NV unverified, $R_NA n/a) differ from scores.json ($C_PASS, $C_FAIL, $C_PART, $C_NV, $C_NA)"
    fi
    if [ "$R_FAIL" -gt 0 ] && [ "$VERDICT" = "no-blocking-problems" ]; then fail "AUDIT.md has failed checklist items but the verdict is green"; fi
  else
    warn "no checklist table rows found in AUDIT.md"
  fi

  # 4. tool names with a status in brackets must match the manifest
  if [ -f "$M" ]; then
    TMP="$(mktemp 2>/dev/null || mktemp -t verify)"
    grep -oE '[a-z][a-z0-9-]+ \((clean|findings|done|partial|skipped|failed-to-run|timeout|unavailable)[^)]*\)' "$R" | sort -u | while IFS= read -r item; do
      tool="${item%% *}"; st="${item#*(}"; st="${st%%[ :),;]*}"
      row="$(awk -F'\t' -v t="$tool" 'NR>1 && $1==t {print $2; exit}' "$M")"
      if [ -z "$row" ]; then
        echo "FAIL: AUDIT.md lists '$tool' but it is not in manifest.tsv (a tool that did not run must not be listed as a source)"
      else
        case "$row" in "$st"*) ;; *) echo "FAIL: AUDIT.md says $tool ($st) but manifest.tsv says: $row" ;; esac
      fi
    done > "$TMP"
    if [ -s "$TMP" ]; then cat "$TMP"; FAILS=$((FAILS + $(wc -l < "$TMP" | tr -d ' '))); else pass "tool statuses in AUDIT.md match manifest.tsv"; fi
    rm -f "$TMP"
  fi
fi

# 5. secrets: known key shapes first, then gitleaks (its rules plus our NAME=value rule) if installed
LEAK=0
for f in "$R" "$S"; do
  [ -f "$f" ] || continue
  if grep -qE 'sk_live_[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z2-7]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----' "$f"; then
    fail "$(basename "$f") contains text shaped like a secret (key, token or private key); remove it, never print values"; LEAK=1
  fi
done
if has gitleaks; then
  T="$(mktemp -d 2>/dev/null || mktemp -d -t verify)"
  cp "$R" "$S" "$T/" 2>/dev/null
  if ! (cd "$T" && gitleaks detect --no-git --source . --config "$SCRIPT_DIR/gitleaks-extra.toml" --redact --report-format json --report-path "$T/out.json" --no-banner >/dev/null 2>&1); then
    fail "gitleaks found something secret-like in the report files; find and remove it"; LEAK=1
  fi
  rm -rf "$T"
else
  warn "gitleaks not installed: only the built-in key-shape check ran on the report"
fi
if [ $LEAK -eq 0 ]; then pass "no secret-looking text in the report"; fi

echo
if [ $FAILS -eq 0 ]; then echo "REPORT OK"; else echo "REPORT HAS $FAILS PROBLEM(S): fix them before showing it"; fi
[ $FAILS -eq 0 ]
