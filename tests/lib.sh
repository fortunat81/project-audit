# Shared helpers for the test runner. Sourced by run-tests.sh and by the checks it starts.
# Results are printed as lines the runner counts: "  PASS ...", "  FAIL ...", "  UNTESTED ...".

HERE="${HERE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
REPO="${REPO:-$(cd "$HERE/.." && pwd)}"
SCAN="$REPO/scripts/scan.sh"
WORK="${AUDIT_TEST_WORK:-$REPO/.test-work}"

rand_alnum() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"; }
# AWS key ids use base32 (A-Z, 2-7); gitleaks' aws-access-token rule only matches those
rand_upper() { LC_ALL=C tr -dc 'A-Z2-7' < /dev/urandom | head -c "$1"; }
export -f rand_alnum rand_upper

# Lets a test check that untrusted mode hides secret-looking variables
export FAKE_SECRET_TOKEN_FOR_TESTS="not-a-real-secret"

# Portable in-place edit: BSD sed (macOS) needs a different -i syntax than GNU sed, so avoid -i.  sedi 's/a/b/' file
sedi() { local f="$2"; sed "$1" "$f" > "$f.tmp" && mv "$f.tmp" "$f"; }

ok()   { printf "  PASS      %s\n" "$1"; }
bad()  { printf "  FAIL      %s\n" "$1"; [ -n "${2:-}" ] && printf "            %s\n" "$2"; return 0; }
skip() { printf "  UNTESTED  %s\n" "$1"; }

# A fresh, correct report folder for the report, verdict and web-page tests.
#   make_report <dir> <verdict> <level> <mode> <failed-item-count>
make_report() {
  local d="$1"; mkdir -p "$d"
  printf 'tool\tstatus\texit\toutput\tdimension\nsemgrep\tfindings\t0\ts.json\tsecurity\ngitleaks\tclean\t0\tg.json\tsecurity\n' > "$d/manifest.tsv"
  local mark="✅"; [ "$5" -gt 0 ] && mark="❌"
  printf '# Audit\n\nVerdict: Launch with limits\n\n| 1 | No secrets | %s | T | gitleaks clean |\n| 2 | Backups | ❓ | Y | not answered |\n\n| Security | 70 | medium | semgrep (findings), gitleaks (clean) | ok |\n' "$mark" > "$d/AUDIT.md"
  printf '{"date":"2026-01-01","mode":"%s","rubric":2,"level":%s,"verdict":"%s","confirmed":{"critical":0,"high":0},"checklist":{"pass":%s,"fail":%s,"partial":0,"not_verified":1,"not_applicable":0},"scores":{"architecture":80,"modularity":80,"spaghettiness":80,"security":70,"quality":80,"scalability":null,"documentation":60}}' \
    "$4" "$3" "$2" "$([ "$5" -gt 0 ] && echo 0 || echo 1)" "$5" > "$d/scores.json"
}
