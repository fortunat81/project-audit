#!/usr/bin/env bash
# Runs the auditor against every test scenario and checks it finds what was planted,
# and doesn't flag what's fine.
#
# Usage (from anywhere):
#   bash tests/run-tests.sh                   all scenarios
#   bash tests/run-tests.sh expo-supabase-ai  just one (or several)
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
exec > >(tee "$HERE/last-run.txt") 2>&1

rand_alnum() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"; }
rand_upper() { LC_ALL=C tr -dc 'A-Z0-9' < /dev/urandom | head -c "$1"; }
export -f rand_alnum rand_upper

PASS=0; FAIL=0; UNTESTED=0
ok()   { PASS=$((PASS+1)); printf "  PASS      %s\n" "$1"; }
bad()  { FAIL=$((FAIL+1)); printf "  FAIL      %s\n" "$1"; [ -n "${2:-}" ] && printf "            %s\n" "$2"; }
skip() { UNTESTED=$((UNTESTED+1)); printf "  UNTESTED  %s\n" "$1"; }

if [ $# -gt 0 ]; then SCENARIOS="$*"; else SCENARIOS="$(ls "$HERE/scenarios")"; fi

for name in $SCENARIOS; do
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
    AUDIT_NO_FETCH=1 bash "$SCAN" > "$WORK/$name.log" 2>&1
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

echo
echo "RESULT: $PASS passed, $FAIL failed, $UNTESTED untested (tool not installed)"
if [ "${KEEP:-0}" = "1" ]; then echo "Test projects kept in: $WORK"; else rm -rf "$WORK"; fi
[ $FAIL -eq 0 ]
