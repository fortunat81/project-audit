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
  [ "$name" = "report-check" ] && continue   # handled after the scenarios
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

# --- Report checker: a good report passes, each kind of mistake is caught
if [ $# -eq 0 ] || [ "${1:-}" = "report-check" ]; then
echo
echo "=== report-check (scripts/verify-report.sh)"
VR="$HERE/../scripts/verify-report.sh"
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
  printf '{"date":"2026-01-01","mode":"%s","rubric":2,"level":%s,"verdict":"%s","checklist":{"pass":%s,"fail":%s,"partial":0,"not_verified":1,"not_applicable":0},"scores":{"architecture":80,"modularity":80,"spaghettiness":80,"security":70,"quality":80,"scalability":null,"documentation":60}}'     "$4" "$3" "$2" "$([ "$5" -gt 0 ] && echo 0 || echo 1)" "$5" > "$d/scores.json"
}
expect_report() {   # expect_report <label> <dir> <ok|fail>
  if bash "$VR" "$2" >"$2/verify.out" 2>&1; then got=ok; else got=fail; fi
  if [ "$got" = "$3" ]; then ok "report-check: $1"; else bad "report-check: $1" "expected $3, got $got: $(grep -E '^(FAIL|WARN)' "$2/verify.out" | head -3 | tr '
' ' ')"; fi
}
RC="$WORK/report-check"; rm -rf "$RC"
make_report "$RC/good" launch-with-limits 2 full 0;             expect_report "a correct report passes" "$RC/good" ok
make_report "$RC/note" launch-with-limits 2 full 0; sed -i 's/semgrep (findings)/semgrep (findings, see note)/' "$RC/note/AUDIT.md"
expect_report "a status followed by a note is read correctly" "$RC/note" ok
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

echo
echo "RESULT: $PASS passed, $FAIL failed, $UNTESTED untested (tool not installed)"
if [ "${KEEP:-0}" = "1" ]; then echo "Test projects kept in: $WORK"; else rm -rf "$WORK"; fi
[ $FAIL -eq 0 ]
