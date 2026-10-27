# Checks that are not scenarios: the report checker, the verdict rules, the web page, the local server
# and the translation code. Each unit_* function prints PASS/FAIL/UNTESTED lines like a scenario.
# Sourced by run-tests.sh (uses ok/bad/skip, make_report, WORK, HERE from lib.sh).

UNITS="report-check verdict-check html-check serve-check translate-check engine-check core-check detect-check digest-check modes-check helpers-check progress-check"

# Runs a Python test file that prints "OK: label" / "BAD: label | detail" and turns each line into PASS/FAIL
run_python_lines() {   # run_python_lines <prefix> <file>
  local prefix="$1" file="$2" line
  while IFS= read -r line; do
    case "$line" in
      "OK: "*) ok "$prefix: ${line#OK: }" ;;
      "BAD: "*) bad "$prefix: ${line#BAD: }" ;;
    esac
  done < <(PYTHONUTF8=1 $PYTHON "$HERE/$file" 2>&1)
}

need_python() {   # need_python <what>
  . "$REPO/scripts/find-python.sh"
  if find_python; then return 0; fi
  skip "$1 (no Python 3.8+ found)"; return 1
}

# --- Report checker: a good report passes, each kind of mistake is caught
unit_report_check() {
  echo "=== report-check (scripts/verify-report.sh)"
  local VR="$REPO/scripts/verify-report.sh" RC="$WORK/report-check"
  expect_report() {   # expect_report <label> <dir> <ok|fail>
    local got
    if bash "$VR" "$2" >"$2/verify.out" 2>&1; then got=ok; else got=fail; fi
    if [ "$got" = "$3" ]; then ok "report-check: $1"; else bad "report-check: $1" "expected $3, got $got: $(grep -E '^(FAIL|WARN)' "$2/verify.out" | head -3 | tr '\n' ' ')"; fi
  }
  rm -rf "$RC"
  make_report "$RC/good" launch-with-limits 2 full 0
  expect_report "a correct report passes" "$RC/good" ok
  make_report "$RC/note" launch-with-limits 2 full 0; sedi 's/semgrep (findings)/semgrep (findings, see note)/' "$RC/note/AUDIT.md"
  expect_report "a status followed by a note is read correctly" "$RC/note" ok
  make_report "$RC/fixok" launch-with-limits 2 full 0; printf '{"fixes":[{"id":"P-1","title":"Pin actions","who":"claude","change":"x","verify":"y"}]}' > "$RC/fixok/fixes.json"
  expect_report "a well-formed fixes.json passes" "$RC/fixok" ok
  make_report "$RC/fixbad" launch-with-limits 2 full 0; printf '{"fixes":[{"id":"P-1","title":"a","who":"robot"},{"id":"P-1","title":"b","who":"claude"}]}' > "$RC/fixbad/fixes.json"
  expect_report "a bad 'who' and a repeated fix id are caught" "$RC/fixbad" fail
  make_report "$RC/fixsecret" launch-with-limits 2 full 0; printf '{"fixes":[{"id":"P-1","title":"a","who":"you","change":"use ghp_%s"}]}' "$(rand_alnum 36)" > "$RC/fixsecret/fixes.json"
  expect_report "a secret-looking value inside fixes.json is caught" "$RC/fixsecret" fail
  make_report "$RC/counts" launch-with-limits 2 full 0; sedi 's/"pass":1/"pass":3/' "$RC/counts/scores.json"
  expect_report "marks that differ from scores.json are caught" "$RC/counts" fail
  make_report "$RC/status" launch-with-limits 2 full 0; sedi 's/gitleaks (clean)/gitleaks (findings)/' "$RC/status/AUDIT.md"
  expect_report "a tool status that differs from the manifest is caught" "$RC/status" fail
  make_report "$RC/ghost" launch-with-limits 2 full 0; printf '| Quality | 80 | low | madge (clean) | x |\n' >> "$RC/ghost/AUDIT.md"
  expect_report "a tool that never ran listed as a source is caught" "$RC/ghost" fail
  make_report "$RC/secret" launch-with-limits 2 full 0; printf 'token ghp_%s\n' "$(rand_alnum 36)" >> "$RC/secret/AUDIT.md"
  expect_report "a secret-looking value in the report is caught" "$RC/secret" fail
  make_report "$RC/green3" no-blocking-problems 3 full 0; sedi 's/Launch with limits/No blocking problems found/' "$RC/green3/AUDIT.md"
  expect_report "a green verdict at Level 3 is caught" "$RC/green3" fail
  make_report "$RC/greenfail" no-blocking-problems 1 full 1; sedi 's/Launch with limits/No blocking problems found/' "$RC/greenfail/AUDIT.md"
  expect_report "a green verdict with a failed item is caught" "$RC/greenfail" fail
  make_report "$RC/phrase" launch-with-limits 2 full 0; sedi 's/Launch with limits/Looks fine/' "$RC/phrase/AUDIT.md"
  expect_report "a report that does not state the verdict is caught" "$RC/phrase" fail
  # independent review: full mode needs the record, the three agents and a section in the report
  make_report "$RC/noreview" launch-with-limits 2 full 0; sedi 's/,"independent_review":{[^}]*}//' "$RC/noreview/scores.json"
  expect_report "a full review with no independent-review record is caught" "$RC/noreview" fail
  make_report "$RC/twoagents" launch-with-limits 2 full 0; sedi 's/"security","architecture","scalability"/"security","architecture"/' "$RC/twoagents/scores.json"
  expect_report "an independent review missing one of the three agents is caught" "$RC/twoagents" fail
  make_report "$RC/nosection" launch-with-limits 2 full 0; sedi 's/## Independent review/## Notes/' "$RC/nosection/AUDIT.md"
  expect_report "an independent review not shown in the report is caught" "$RC/nosection" fail
  make_report "$RC/skipped" launch-with-limits 2 full 0
  sedi 's/"independent_review":{[^}]*}/"independent_review":{"status":"not_done","reason":"subagents unavailable in this session"}/' "$RC/skipped/scores.json"
  sedi 's/## Independent review/## Notes/' "$RC/skipped/AUDIT.md"
  expect_report "an honest 'not done, and why' is allowed (with a warning)" "$RC/skipped" ok
  make_report "$RC/noreason" launch-with-limits 2 full 0; sedi 's/"independent_review":{[^}]*}/"independent_review":{"status":"not_done"}/' "$RC/noreason/scores.json"
  expect_report "'not done' with no reason is caught" "$RC/noreason" fail
  make_report "$RC/quickok" launch-with-limits 2 quick 0
  expect_report "a quick scan needs no independent review" "$RC/quickok" ok
}

# --- Verdict rules: the same inputs always give the same verdict (scripts/audit_verdict.py)
unit_verdict_check() {
  echo "=== verdict-check (scripts/audit_verdict.py)"
  need_python "verdict rules" || return 0
  expect_verdict() {   # expect_verdict <label> <expected> <args...>
    local label="$1" want="$2" got; shift 2
    got="$(PYTHONUTF8=1 $PYTHON "$REPO/scripts/audit_verdict.py" "$@" 2>&1 | sed -n 's/^VERDICT=//p')"
    if [ "$got" = "$want" ]; then ok "verdict: $label"; else bad "verdict: $label" "expected $want, got ${got:-nothing}"; fi
  }
  local ALLPASS="1:pass,2:pass,9:pass,13:pass,19:pass,22:pass"
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
}

# --- Web page: hostile text in a report or finding must be shown as text, never run
unit_html_check() {
  echo "=== html-check (scripts/audit_report_html.py)"
  need_python "web page" || return 0
  local H="$WORK/html-check" H2="$WORK/html-check2" bs
  rm -rf "$H" "$H2"; make_report "$H" launch-with-limits 2 full 0
  printf 'WARN  X-RULE: bad <img src=x onerror=alert(1)>: src/<script>alert(2)</script>.js:3\n' > "$H/release-checks.txt"
  printf '\n<script>alert(3)</script> and <img src=x onerror=alert(4)>\n' >> "$H/AUDIT.md"
  PYTHONUTF8=1 $PYTHON "$REPO/scripts/audit_report_html.py" "$H" > /dev/null 2>&1
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
  if PYTHONUTF8=1 $PYTHON -c "import sys; sys.path.insert(0, sys.argv[1]); import audit_report_html as m; sys.exit(0 if set(m.I18N['en']) == set(m.I18N['fr']) else 1)" "$REPO/scripts"; then ok "French and English have the same labels"; else bad "French and English have the same labels" "keys differ"; fi
  # Hostile text in the report and in proposed fixes is shown as text
  make_report "$H2" launch-with-limits 2 full 0
  printf '\n[click](javascript:alert(7)) and **bold** and `code`\n\n```\n<script>alert(8)</script>\n```\n' >> "$H2/AUDIT.md"
  printf '{"fixes":[{"id":"P-1","title":"<img src=x onerror=alert(9)>","who":"claude","change":"<script>alert(10)</script>","why":"<b>x</b>"}]}' > "$H2/fixes.json"
  PYTHONUTF8=1 $PYTHON "$REPO/scripts/audit_report_html.py" "$H2" > /dev/null 2>&1
  bs="$(printf '\\')"   # one backslash
  # The page keeps its data as JSON with "<" written as <, so look for the escaped forms
  if grep -Fq 'href='"$bs"'"javascript' "$H2/report.html" || grep -Fq '<script>alert' "$H2/report.html" || grep -Fq '<img src=x onerror' "$H2/report.html"; then bad "report and fixes are escaped" "raw or unsafe markup found"; else ok "report and fixes are escaped"; fi
  if grep -Fq "$bs"'u0026lt;script' "$H2/report.html"; then ok "script text in the report is shown as text"; else bad "script text in the report is shown as text" "escaped form not found"; fi
  if grep -Fq "$bs"'u003cstrong'"$bs"'u003ebold' "$H2/report.html" && grep -Fq "$bs"'u003ccode'"$bs"'u003ecode' "$H2/report.html"; then ok "the report is shown formatted"; else bad "the report is shown formatted" "no formatting found"; fi
  if grep -q 'AUDIT_SERVER' "$H2/report.html"; then ok "the page has a place for the local server controls"; else bad "the page has a place for the local server controls" "placeholder missing"; fi
  if grep -Eq 'https?://[^"'"'"' )]*\.(js|css)' "$H/report.html"; then bad "web page needs no internet" "an external file is referenced"; else ok "web page needs no internet"; fi
}

# --- Local server that starts Claude on approved fixes (serve_test.py, with a stand-in for claude)
unit_serve_check() {
  echo "=== serve-check (scripts/audit_serve.py)"
  need_python "local server" || return 0
  run_python_lines "server" serve_test.py
}

# --- English and French: tables, translate helper (with a stand-in for claude), report check on translations
unit_translate_check() {
  echo "=== translate-check (scripts/audit_i18n.py, audit_translate.py)"
  need_python "translations" || return 0
  run_python_lines "translate" translate_test.py
}

# --- The small commands of scan.sh (--detect, --projects, --check, --status, --version, --add-gitignore, ...)
unit_engine_check() {
  echo "=== engine-check (scripts/audit_scan.py modes)"
  local P="$WORK/engine-check" out cr
  rm -rf "$P"; mkdir -p "$P/backend" "$P/web"
  printf '{ "name": "web", "version": "1.0.0", "dependencies": { "react": "18.2.0" } }\n' > "$P/web/package.json"
  printf 'flask==3.0.0\n' > "$P/backend/requirements.txt"
  printf '{ "name": "root", "version": "1.0.0", "dependencies": { "express": "4.21.2" } }\n' > "$P/package.json"
  ( cd "$P" && git init -q && git config user.email t@example.com && git config user.name t && git add -A && git commit -qm init )
  cr="$(printf '\r')"
  out="$(cd "$P" && bash "$SCAN" --detect 2>&1)"
  case "$out" in *"$cr"*) bad "output has plain line endings" "a carriage return (\\r) was found in --detect output" ;; *) ok "output has plain line endings" ;; esac
  case "$out" in *"TRAITS="*"node"*"server-code"*) ok "--detect lists the traits" ;; *) bad "--detect lists the traits" "$out" ;; esac
  case "$out" in *"MODULE=10-secrets applies"*"MODULE=80-live-site not-applicable"*) ok "--detect lists which modules apply" ;; *) bad "--detect lists which modules apply" "$out" ;; esac
  out="$(cd "$P" && bash "$SCAN" --projects 2>&1)"
  case "$out" in *"PROJECT=."*"PROJECT=backend"*"PROJECT=web"*) ok "--projects lists the folders" ;; *) bad "--projects lists the folders" "$out" ;; esac
  out="$(cd "$P" && bash "$SCAN" --check 2>&1)"
  case "$out" in "PROFILE="*) ok "--check starts with the profile" ;; *) bad "--check starts with the profile" "$out" ;; esac
  out="$(cd "$P" && bash "$SCAN" --status 2>&1)"
  case "$out" in *"RECOMMEND=full"*"no previous audit"*) ok "--status without an earlier audit recommends a full one" ;; *) bad "--status without an earlier audit recommends a full one" "$out" ;; esac
  out="$(cd "$P" && AUDIT_NO_FETCH=1 bash "$SCAN" --version 2>&1)"
  case "$out" in *"IS_GIT=yes"*"UPSTREAM=none"*"CAN_FAST_FORWARD=no"*) ok "--version reports a repo without GitHub" ;; *) bad "--version reports a repo without GitHub" "$out" ;; esac
  out="$(cd "$P" && bash "$SCAN" --add-gitignore 2>&1; bash "$SCAN" --add-gitignore 2>&1)"
  case "$out" in *"ADDED"*"ALREADY"*) ok "--add-gitignore adds the line once" ;; *) bad "--add-gitignore adds the line once" "$out" ;; esac
  out="$(cd "$P" && bash "$SCAN" --untrusted --install-deps 2>&1)"
  case "$out" in *"REFUSED"*) ok "untrusted mode refuses to install packages" ;; *) bad "untrusted mode refuses to install packages" "$out" ;; esac
  out="$(cd "$P" && bash "$SCAN" --no-such-mode 2>&1)"; code=$?
  if [ $code -eq 2 ] && case "$out" in *"Unknown option"*) true ;; *) false ;; esac; then ok "an unknown option is refused"; else bad "an unknown option is refused" "exit $code: $out"; fi
}

# --- One function at a time: the tool runner, trait detection and the findings digest (Python test files)
unit_core_check() {
  echo "=== core-check (scripts/audit_core.py: how a tool's result becomes a status)"
  need_python "tool runner" || return 0
  run_python_lines "core" core_test.py
}

unit_detect_check() {
  echo "=== detect-check (scripts/audit_detect.py: what each kind of project is recognised as)"
  need_python "trait detection" || return 0
  run_python_lines "detect" detect_test.py
}

unit_digest_check() {
  echo "=== digest-check (scripts/audit_digest.py: scanner output in, findings out)"
  need_python "findings digest" || return 0
  run_python_lines "digest" digest_test.py
}

unit_modes_check() {
  echo "=== modes-check (scripts/audit_modes.py: when --status recommends a full audit)"
  need_python "status mode" || return 0
  run_python_lines "modes" modes_test.py
}

unit_progress_check() {
  echo "=== progress-check (scripts/audit_progress.py: the live progress page)"
  need_python "progress page" || return 0
  run_python_lines "progress" progress_test.py
}

unit_helpers_check() {
  echo "=== helpers-check (live-site rules, the Markdown renderer, the digest text)"
  need_python "helper functions" || return 0
  run_python_lines "helpers" helpers_test.py
}
