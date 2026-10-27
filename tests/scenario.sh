# Runs one test scenario: scans a fake project and compares the result with its expected.tsv.
# Sourced by run-tests.sh (uses ok/bad/skip, WORK, SCAN, HERE from lib.sh).
#
# Each scenario folder has:
#   files/         the fake project (copied to a temp folder and committed to a fresh git repo)
#   bin/           optional: stand-in commands put first on PATH during the scan
#   setup.sh       optional: runs after the first commit (history secrets, staged files, .env...)
#                  Fake secrets are generated here at test time, so none are ever committed.
#   scan-args      optional: extra arguments for scan.sh (for example --all or --untrusted)
#   expected.tsv   one check per line, tab-separated:
#                    <tool>  <status>  <output must contain>  <output must NOT contain>
#                  status: a regex on the manifest status, or "ran" (clean/findings/done/partial)
#                  or "absent" (the row must not exist). Use - for "no condition".
#                  Also: @traits <words>  @not-traits <words>  @coverage <regex>  @file <paths>
#                  @no-file <paths>  @meta <regex>  @digest <regex>  @not-digest <regex>
#                  @html <regex>  @not-html <regex>

run_scenario() {
  local name="$1" src dest OUT M TRAITS tool want contains notcontains t row status file label re f
  src="$HERE/scenarios/$name"
  echo "=== $name"
  [ -d "$src" ] || { bad "scenario exists" "no such scenario: $name"; return; }
  dest="$WORK/$name"
  mkdir -p "$dest"
  [ -d "$src/files" ] && cp -R "$src/files/." "$dest/"
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
    bad "scan ran" "no results folder; see $WORK/$name.log"; return
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
}
