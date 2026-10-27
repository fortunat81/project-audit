#!/usr/bin/env bash
# Runs the auditor against every test scenario and checks it finds what was planted,
# and doesn't flag what's fine.
#
# Usage (from anywhere):
#   bash tests/run-tests.sh                   all scenarios
#   bash tests/run-tests.sh expo-supabase-ai  just one (or several)
#   bash tests/run-tests.sh --install         first install every missing scanner, then test
#   KEEP=1 bash tests/run-tests.sh            keep the test projects (in .test-work/) to inspect them
#
# Output is also saved to tests/last-run.txt.
#
# Each scenario folder has:
#   files/         the fake project (copied to a temp folder and committed to a fresh git repo)
#   setup.sh       optional: runs after the first commit (history secrets, staged files, .env...)
#                  Fake secrets are generated here at test time, so none are ever committed.
#   expected.tsv   one check per line, tab-separated:
#                    <tool>  <status>  <output must contain>  <output must NOT contain>
#                  status: a regex on the manifest status, or "ran" (clean/findings/done/partial)
#                  or "absent" (the row must not exist). Use - for "no condition".
#                  Also: @traits <words>  @not-traits <words>  @coverage <regex>
#
# Results: PASS, FAIL, or UNTESTED (the tool isn't installed on this machine, so the
# expectation couldn't be checked). Exit code is 1 if anything failed.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
SCAN="$REPO/scripts/scan.sh"
WORK="$REPO/.test-work"           # git-ignored; recreated on every run
rm -rf "$WORK"; mkdir -p "$WORK"
# Ignore it via .git/info/exclude, not .gitignore: scanners such as osv-scanner obey a parent
# .gitignore and would skip the test projects entirely.
EXC="$REPO/.git/info/exclude"
grep -qx '.test-work/' "$EXC" 2>/dev/null || { mkdir -p "$(dirname "$EXC")"; echo '.test-work/' >> "$EXC"; }
exec > >(tee "$HERE/last-run.txt") 2>&1

rand_alnum() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"; }
# AWS key ids use base32 (A-Z, 2-7); gitleaks' aws-access-token rule only matches those
rand_upper() { LC_ALL=C tr -dc 'A-Z2-7' < /dev/urandom | head -c "$1"; }
export -f rand_alnum rand_upper

export FAKE_SECRET_TOKEN_FOR_TESTS="not-a-real-secret"   # lets a test check that untrusted mode hides secret-looking variables
PASS=0; FAIL=0; UNTESTED=0
ok()   { PASS=$((PASS+1)); printf "  PASS      %s\n" "$1"; }
bad()  { FAIL=$((FAIL+1)); printf "  FAIL      %s\n" "$1"; [ -n "${2:-}" ] && printf "            %s\n" "$2"; }
skip() { UNTESTED=$((UNTESTED+1)); printf "  UNTESTED  %s\n" "$1"; }

if [ "${1:-}" = "--install" ]; then
  shift
  echo "=== Installing missing scanners"
  bash "$SCAN" --install all
  echo
fi

if [ $# -gt 0 ]; then SCENARIOS="$*"; else SCENARIOS="$(ls "$HERE/scenarios")"; fi

for name in $SCENARIOS; do
  [ "$name" = "report-check" ] && continue
  [ "$name" = "verdict-check" ] && continue
  [ "$name" = "html-check" ] && continue
  [ "$name" = "serve-check" ] && continue
  [ "$name" = "translate-check" ] && continue   # handled after the scenarios
  src="$HERE/scenarios/$name"
  [ -d "$src" ] || { echo "No such scenario: $name"; FAIL=$((FAIL+1)); continue; }
  dest="$WORK/$name"
  mkdir -p "$dest"
  [ -d "$src/files" ] && cp -R "$src/files/." "$dest/"
  echo
  echo "=== $name"
  (
    cd "$dest" || exit 1
    git init -q
    git config user.email "audit-test@example.com"
    git config user.name "audit-test"
    git config commit.gpgsign false
    git add -A && git commit -qm "initial" --allow-empty
    [ -f "$src/setup.sh" ] && bash "$src/setup.sh"
    if [ -d "$src/bin" ]; then   # stand-in commands that go first on PATH (for example one that edits the project mid-scan)
      mkdir -p "$WORK/.shim-$name"; cp -R "$src/bin/." "$WORK/.shim-$name/"; chmod +x "$WORK/.shim-$name/"* 2>/dev/null
      PATH="$WORK/.shim-$name:$PATH"; export SHIM_DIR="$WORK/.shim-$name"
    fi
    AUDIT_NO_FETCH=1 bash "$SCAN" $(cat "$src/scan-args" 2>/dev/null) > "$WORK/$name.log" 2>&1
  )
  if [ ! -f "$dest/audit/latest.txt" ]; then
    bad "scan ran" "no results folder; see $WORK/$name.log"; continue
  fi
  OUT="$(cat "$dest/audit/latest.txt")"
  M="$OUT/manifest.tsv"
  TRAITS=" $(grep '^traits=' "$OUT/meta.txt" | cut -d= -f2-) "

  while IFS="$(printf '\t')" read -r tool want contains notcontains; do
    case "$tool" in ''|'#'*) continue ;; esac
    case "$tool" in
      @traits)
        for t in $want; do
          case "$TRAITS" in *" $t "*) ok "trait $t detected" ;; *) bad "trait $t detected" "traits were:$TRAITS" ;; esac
        done; continue ;;
      @not-traits)
        for t in $want; do
          case "$TRAITS" in *" $t "*) bad "trait $t NOT detected" "traits were:$TRAITS" ;; *) ok "trait $t not detected" ;; esac
        done; continue ;;
      @file)       # a file the scan must have created, inside the test project
        for t in $want; do if [ -e "$dest/$t" ]; then ok "file exists: $t"; else bad "file exists: $t" "not found in the test project"; fi; done; continue ;;
      @no-file)    # a file that must NOT exist (for example a marker the project would write if the scan ran its code)
        for t in $want; do if [ -e "$dest/$t" ]; then bad "file absent: $t" "the scan ran code from the project"; else ok "file absent: $t"; fi; done; continue ;;
      @meta)       # a line the run's meta.txt must contain
        if grep -Eq "$want" "$OUT/meta.txt"; then ok "meta: $want"; else bad "meta: $want" "not in meta.txt"; fi; continue ;;
      @html)       # text report.html must contain
        if grep -Eq "$want" "$OUT/report.html" 2>/dev/null; then ok "web page has: $want"; else bad "web page has: $want" "not in report.html"; fi; continue ;;
      @not-html)   # text report.html must NOT contain (secret values, unescaped markup)
        if grep -Eq "$want" "$OUT/report.html" 2>/dev/null; then bad "web page has no: $want" "found in report.html"; else ok "web page has no: $want"; fi; continue ;;
      @digest)     # a line digest.txt must contain
        if grep -Eq "$want" "$OUT/digest.txt" 2>/dev/null; then ok "digest has: $want"; else bad "digest has: $want" "not in digest.txt"; fi; continue ;;
      @not-digest) # text digest.txt and findings.tsv must NOT contain (secret values, for example)
        if grep -Eq "$want" "$OUT/digest.txt" "$OUT/findings.tsv" 2>/dev/null; then bad "digest has no: $want" "found in digest.txt or findings.tsv"; else ok "digest has no: $want"; fi; continue ;;
      @coverage)
        if grep -Eq "$want" "$OUT/coverage.txt"; then ok "coverage note: $want"; else bad "coverage note: $want" "$(tr '\n' ' ' < "$OUT/coverage.txt")"; fi
        continue ;;
    esac

    row="$(awk -F'\t' -v t="$tool" 'NR>1 && $1==t' "$M" | head -1)"
    status="$(printf '%s' "$row" | cut -f2)"
    file="$(printf '%s' "$row" | cut -f4)"
    label="$tool: $want${contains:+ | has '$contains'}"
    [ "${contains:-}" = "-" ] && label="$tool: $want"

    if [ "$want" = "absent" ]; then
      if [ -z "$row" ]; then ok "$tool: not run (not applicable)"; else bad "$tool: should not run" "status: $status"; fi
      continue
    fi
    if [ -z "$row" ]; then bad "$label" "no row in the manifest (module didn't run)"; continue; fi
    case "$status" in
      "skipped: not installed"*|"skipped: npx not found"*|"skipped: Flutter SDK not found"*|"skipped: Dart SDK not found"*|"skipped: npm not found"*)
        case "$want" in ^skipped*) ;; *) skip "$label (tool not installed here)"; continue ;; esac ;;
    esac

    if [ "$want" = "ran" ]; then re='^(clean|findings|done|partial)'; else re="$want"; fi
    if ! printf '%s' "$status" | grep -Eq "$re"; then
      bad "$label" "status was: $status  (log: $WORK/$name.log)"; continue
    fi
    f="$OUT/$file"
    if [ -n "${contains:-}" ] && [ "$contains" != "-" ]; then
      if [ ! -f "$f" ] || ! grep -Eq "$contains" "$f"; then bad "$label" "'$contains' not found in $file"; continue; fi
    fi
    if [ -n "${notcontains:-}" ] && [ "$notcontains" != "-" ] && [ -f "$f" ] && grep -Eq "$notcontains" "$f"; then
      bad "$label" "false positive: '$notcontains' found in $file: $(grep -Em1 "$notcontains" "$f" | cut -c1-120)"; continue
    fi
    ok "$label"
  done < "$src/expected.tsv"
done

# A fresh, correct report folder for the report, verdict and web-page tests
make_report() {   # make_report <dir> <verdict> <level> <mode> <fail-count>   (a fresh, correct report)
  local d="$1"; mkdir -p "$d"
  printf 'tool	status	exit	output	dimension
semgrep	findings	0	s.json	security
gitleaks	clean	0	g.json	security
' > "$d/manifest.tsv"
  local mark="✅"; [ "$5" -gt 0 ] && mark="❌"
  printf "# Audit

Verdict: Launch with limits

| 1 | No secrets | %s | T | gitleaks clean |
| 2 | Backups | ❓ | Y | not answered |

| Security | 70 | medium | semgrep (findings), gitleaks (clean) | ok |
" "$mark" > "$d/AUDIT.md"
  printf '{"date":"2026-01-01","mode":"%s","rubric":2,"level":%s,"verdict":"%s","confirmed":{"critical":0,"high":0},"checklist":{"pass":%s,"fail":%s,"partial":0,"not_verified":1,"not_applicable":0},"scores":{"architecture":80,"modularity":80,"spaghettiness":80,"security":70,"quality":80,"scalability":null,"documentation":60}}'     "$4" "$3" "$2" "$([ "$5" -gt 0 ] && echo 0 || echo 1)" "$5" > "$d/scores.json"
}
# --- Report checker: a good report passes, each kind of mistake is caught
if [ $# -eq 0 ] || [ "${1:-}" = "report-check" ]; then
echo
echo "=== report-check (scripts/verify-report.sh)"
VR="$HERE/../scripts/verify-report.sh"
expect_report() {   # expect_report <label> <dir> <ok|fail>
  if bash "$VR" "$2" >"$2/verify.out" 2>&1; then got=ok; else got=fail; fi
  if [ "$got" = "$3" ]; then ok "report-check: $1"; else bad "report-check: $1" "expected $3, got $got: $(grep -E '^(FAIL|WARN)' "$2/verify.out" | head -3 | tr '
' ' ')"; fi
}
RC="$WORK/report-check"; rm -rf "$RC"
make_report "$RC/good" launch-with-limits 2 full 0;             expect_report "a correct report passes" "$RC/good" ok
make_report "$RC/note" launch-with-limits 2 full 0; sed -i 's/semgrep (findings)/semgrep (findings, see note)/' "$RC/note/AUDIT.md"
expect_report "a status followed by a note is read correctly" "$RC/note" ok
make_report "$RC/fixok" launch-with-limits 2 full 0; printf '{"fixes":[{"id":"P-1","title":"Pin actions","who":"claude","change":"x","verify":"y"}]}' > "$RC/fixok/fixes.json"
expect_report "a well-formed fixes.json passes" "$RC/fixok" ok
make_report "$RC/fixbad" launch-with-limits 2 full 0; printf '{"fixes":[{"id":"P-1","title":"a","who":"robot"},{"id":"P-1","title":"b","who":"claude"}]}' > "$RC/fixbad/fixes.json"
expect_report "a bad 'who' and a repeated fix id are caught" "$RC/fixbad" fail
make_report "$RC/fixsecret" launch-with-limits 2 full 0; printf '{"fixes":[{"id":"P-1","title":"a","who":"you","change":"use ghp_%s"}]}' "$(rand_alnum 36)" > "$RC/fixsecret/fixes.json"
expect_report "a secret-looking value inside fixes.json is caught" "$RC/fixsecret" fail
make_report "$RC/counts" launch-with-limits 2 full 0; sed -i 's/"pass":1/"pass":3/' "$RC/counts/scores.json"
expect_report "marks that differ from scores.json are caught" "$RC/counts" fail
make_report "$RC/status" launch-with-limits 2 full 0; sed -i 's/gitleaks (clean)/gitleaks (findings)/' "$RC/status/AUDIT.md"
expect_report "a tool status that differs from the manifest is caught" "$RC/status" fail
make_report "$RC/ghost" launch-with-limits 2 full 0; printf '| Quality | 80 | low | madge (clean) | x |
' >> "$RC/ghost/AUDIT.md"
expect_report "a tool that never ran listed as a source is caught" "$RC/ghost" fail
make_report "$RC/secret" launch-with-limits 2 full 0; printf 'token ghp_%s
' "$(rand_alnum 36)" >> "$RC/secret/AUDIT.md"
expect_report "a secret-looking value in the report is caught" "$RC/secret" fail
make_report "$RC/green3" no-blocking-problems 3 full 0; sed -i 's/Launch with limits/No blocking problems found/' "$RC/green3/AUDIT.md"
expect_report "a green verdict at Level 3 is caught" "$RC/green3" fail
make_report "$RC/greenfail" no-blocking-problems 1 full 1; sed -i 's/Launch with limits/No blocking problems found/' "$RC/greenfail/AUDIT.md"
expect_report "a green verdict with a failed item is caught" "$RC/greenfail" fail
make_report "$RC/phrase" launch-with-limits 2 full 0; sed -i 's/Launch with limits/Looks fine/' "$RC/phrase/AUDIT.md"
expect_report "a report that does not state the verdict is caught" "$RC/phrase" fail
fi

# --- Verdict rules: the same inputs always give the same verdict (scripts/audit_verdict.py)
if [ $# -eq 0 ] || [ "${1:-}" = "verdict-check" ]; then
echo
echo "=== verdict-check (scripts/audit_verdict.py)"
. "$HERE/../scripts/find-python.sh"
if ! find_python; then skip "verdict rules (no Python 3.8+ found)"; else
expect_verdict() {   # expect_verdict <label> <expected> <args...>
  local label="$1" want="$2"; shift 2
  got="$(PYTHONUTF8=1 $PYTHON "$HERE/../scripts/audit_verdict.py" "$@" 2>&1 | sed -n 's/^VERDICT=//p')"
  if [ "$got" = "$want" ]; then ok "verdict: $label"; else bad "verdict: $label" "expected $want, got ${got:-nothing}"; fi
}
ALLPASS="1:pass,2:pass,9:pass,13:pass,19:pass,22:pass"
expect_verdict "a confirmed critical finding blocks, even with every item passed" dont-launch --level 1 --mode full --critical 1 --marks "$ALLPASS"
expect_verdict "a confirmed high finding blocks" dont-launch --level 2 --mode full --high 1 --marks "$ALLPASS"
expect_verdict "a failed secrets item (group A) blocks" dont-launch --level 1 --mode full --marks "1:fail,2:pass"
expect_verdict "a failed access item (group C) blocks" dont-launch --level 2 --mode full --marks "9:fail,1:pass"
expect_verdict "a failed money-logic item (group D) blocks" dont-launch --level 2 --mode full --marks "13:fail,1:pass"
expect_verdict "a failed item outside groups A to D does not block, but is not green" launch-with-limits --level 1 --mode full --marks "19:fail,1:pass"
expect_verdict "every item passed at Level 1 is green" no-blocking-problems --level 1 --mode full --marks "$ALLPASS"
expect_verdict "every item passed at Level 2, full mode, is green" no-blocking-problems --level 2 --mode full --marks "$ALLPASS"
expect_verdict "not-applicable items do not count against green" no-blocking-problems --level 1 --mode full --marks "1:pass,9:na,13:na"
expect_verdict "a quick audit of a Level 2 project is never green" launch-with-limits --level 2 --mode quick --marks "$ALLPASS"
expect_verdict "a quick audit of a Level 1 project can be green" no-blocking-problems --level 1 --mode quick --marks "$ALLPASS"
expect_verdict "Level 3 is never green" launch-with-limits --level 3 --mode full --marks "$ALLPASS"
expect_verdict "an unverified item keeps it at launch with limits" launch-with-limits --level 1 --mode full --marks "1:pass,4:unverified"
expect_verdict "a partly done item keeps it at launch with limits" launch-with-limits --level 1 --mode full --marks "1:pass,19:partial"
expect_verdict "no checklist at all is never green" launch-with-limits --level 1 --mode full
fi
fi

# --- Web page: hostile text in a report or finding must be shown as text, never run
if [ $# -eq 0 ] || [ "${1:-}" = "html-check" ]; then
echo
echo "=== html-check (scripts/audit_report_html.py)"
. "$HERE/../scripts/find-python.sh"
if ! find_python; then skip "web page (no Python 3.8+ found)"; else
  H="$WORK/html-check"; rm -rf "$H"; make_report "$H" launch-with-limits 2 full 0
  printf 'WARN  X-RULE: bad <img src=x onerror=alert(1)>: src/<script>alert(2)</script>.js:3
' > "$H/release-checks.txt"
  printf '
<script>alert(3)</script> and <img src=x onerror=alert(4)>
' >> "$H/AUDIT.md"
  PYTHONUTF8=1 $PYTHON "$HERE/../scripts/audit_report_html.py" "$H" > /dev/null 2>&1
  if [ -s "$H/report.html" ]; then ok "web page is built"; else bad "web page is built" "report.html missing or empty"; fi
  if grep -Eq '<script>alert|<img src=x onerror' "$H/report.html"; then bad "hostile markup is not rendered" "raw markup found in report.html"; else ok "hostile markup is not rendered"; fi
  if grep -q 'Launch with limits' "$H/report.html" && grep -q 'No secrets' "$H/report.html"; then ok "web page shows the verdict and the checklist"; else bad "web page shows the verdict and the checklist" "missing"; fi
  # Without JavaScript (a viewer that does not run scripts, such as a file preview) the page must still show its content
  if PYTHONUTF8=1 $PYTHON -c "
import re, sys, html
t = open(sys.argv[1], encoding='utf-8').read()
t = html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'<script.*?</script>', '', t, flags=re.S)))
need = ['Launch with limits', 'No secrets', 'Findings', 'Launch checklist', 'What was checked', 'X-RULE', 'Written report']
sys.exit(0 if all(n in t for n in need) else 1)" "$H/report.html"; then ok "the page shows its content without JavaScript"; else bad "the page shows its content without JavaScript" "content missing when scripts are removed"; fi
  # French and English carry the same labels
  if PYTHONUTF8=1 $PYTHON -c "import sys; sys.path.insert(0, sys.argv[1]); import audit_report_html as m; sys.exit(0 if set(m.I18N['en']) == set(m.I18N['fr']) else 1)" "$HERE/../scripts"; then ok "French and English have the same labels"; else bad "French and English have the same labels" "keys differ"; fi
  # Hostile text in the report and in proposed fixes is shown as text
  H2="$WORK/html-check2"; rm -rf "$H2"; make_report "$H2" launch-with-limits 2 full 0
  printf '
[click](javascript:alert(7)) and **bold** and `code`

```
<script>alert(8)</script>
```
' >> "$H2/AUDIT.md"
  printf '{"fixes":[{"id":"P-1","title":"<img src=x onerror=alert(9)>","who":"claude","change":"<script>alert(10)</script>","why":"<b>x</b>"}]}' > "$H2/fixes.json"
  PYTHONUTF8=1 $PYTHON "$HERE/../scripts/audit_report_html.py" "$H2" > /dev/null 2>&1
  bs="$(printf '\')"   # one backslash
  # The page keeps its data as JSON with "<" written as <, so look for the escaped forms
  if grep -Fq 'href='"$bs"'"javascript' "$H2/report.html" || grep -Fq '<script>alert' "$H2/report.html" || grep -Fq '<img src=x onerror' "$H2/report.html"; then bad "report and fixes are escaped" "raw or unsafe markup found"; else ok "report and fixes are escaped"; fi
  if grep -Fq "$bs"'u0026lt;script' "$H2/report.html"; then ok "script text in the report is shown as text"; else bad "script text in the report is shown as text" "escaped form not found"; fi
  if grep -Fq "$bs"'u003cstrong'"$bs"'u003ebold' "$H2/report.html" && grep -Fq "$bs"'u003ccode'"$bs"'u003ecode' "$H2/report.html"; then ok "the report is shown formatted"; else bad "the report is shown formatted" "no formatting found"; fi
  if grep -q 'AUDIT_SERVER' "$H2/report.html"; then ok "the page has a place for the local server controls"; else bad "the page has a place for the local server controls" "placeholder missing"; fi
  if grep -Eq 'https?://[^"'"'"' )]*\.(js|css)' "$H/report.html"; then bad "web page needs no internet" "an external file is referenced"; else ok "web page needs no internet"; fi
fi
fi

# --- Local server that starts Claude on approved fixes (tests/serve_test.py, with a stand-in for claude)
if [ $# -eq 0 ] || [ "${1:-}" = "serve-check" ]; then
echo
echo "=== serve-check (scripts/audit_serve.py)"
. "$HERE/../scripts/find-python.sh"
if ! find_python; then skip "local server (no Python 3.8+ found)"; else
  while IFS= read -r line; do
    case "$line" in
      "OK: "*) ok "server: ${line#OK: }" ;;
      "BAD: "*) bad "server: ${line#BAD: }" ;;
    esac
  done < <(PYTHONUTF8=1 $PYTHON "$HERE/serve_test.py" 2>&1)
fi
fi

# --- English and French: tables, translate helper (with a stand-in for claude), report check on translations
if [ $# -eq 0 ] || [ "${1:-}" = "translate-check" ]; then
echo
echo "=== translate-check (scripts/audit_i18n.py, audit_translate.py)"
. "$HERE/../scripts/find-python.sh"
if ! find_python; then skip "translations (no Python 3.8+ found)"; else
  while IFS= read -r line; do
    case "$line" in
      "OK: "*) ok "translate: ${line#OK: }" ;;
      "BAD: "*) bad "translate: ${line#BAD: }" ;;
    esac
  done < <(PYTHONUTF8=1 $PYTHON "$HERE/translate_test.py" 2>&1)
fi
fi

echo
echo "RESULT: $PASS passed, $FAIL failed, $UNTESTED untested (tool not installed)"
if [ "${KEEP:-0}" = "1" ]; then echo "Test projects kept in: $WORK"; else rm -rf "$WORK"; fi
[ $FAIL -eq 0 ]
