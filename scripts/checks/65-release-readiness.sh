# Release readiness: things that should not reach production, checked from the files alone.
#   debug mode left on, open CORS, weak cookie flags, leftover test accounts, containers running as
#   root or on an unpinned image, runtimes past end of support, no lockfile, no tests, no automated
#   checks. No external tools. Results in release-checks.txt as FAIL / WARN lines (file:line only,
#   never the matching text). reviews/release-gate.md says how each line feeds the go/no-go call.

mod_applies() { has_trait node || has_trait python || has_trait dart || has_trait php || has_trait static-site || has_trait docker; }

# End-of-support dates (YYYY-MM-DD) for the runtimes projects pin. Refreshed 2026-10; a runtime
# missing from the table is not judged. Update from https://endoflife.date when it gets old.
EOL_TABLE='node 14 2023-04-30
node 16 2023-09-11
node 18 2025-04-30
node 20 2026-04-30
node 22 2027-04-30
node 24 2028-04-30
python 3.7 2023-06-27
python 3.8 2024-10-07
python 3.9 2025-10-31
python 3.10 2026-10-31
python 3.11 2027-10-31
python 3.12 2028-10-31'

# check_pattern <LEVEL> <CODE> <message> <extended regex>   (over the source/config files)
check_pattern() {
  local level="$1" code="$2" msg="$3" re="$4" hits
  hits="$(echo "$RR_FILES" | tr '\n' '\0' | xargs -0 grep -HnIE "$re" 2>/dev/null | cut -d: -f1,2 | sort -u | head -8)"
  [ -n "$hits" ] && echo "$hits" | sed "s|^|$level  $code: $msg: |" >> "$OUT/release-checks.txt"
  return 0
}

# runtime_eol <runtime> <version like 18 or 3.9> <where it was found>
runtime_eol() {
  local eol
  eol="$(echo "$EOL_TABLE" | awk -v r="$1" -v v="$2" '$1==r && $2==v {print $3}')"
  [ -z "$eol" ] && return 0
  if [ "$eol" \< "$(date +%Y-%m-%d)" ] || [ "$eol" = "$(date +%Y-%m-%d)" ]; then
    echo "FAIL  RUNTIME-EOL: $1 $2 reached end of support on $eol (no more security fixes): $3" >> "$OUT/release-checks.txt"
  fi
  return 0
}

mod_run() {
  DIM="security,quality"
  local f v
  : > "$OUT/release-checks.txt"

  RR_FILES="$(project_files | grep -Ev "$NOISE_RE" \
    | grep -Ev '(^|/)(tests?|__tests__|specs?|fixtures?|docs?|examples?|e2e)/|\.(test|spec)\.|\.(md|lock|map)$' \
    | grep -E '\.(py|js|jsx|ts|tsx|mjs|cjs|php|rb|go|java|kt|dart|yml|yaml|json|ini|cfg|toml|conf|properties)$|(^|/)\.env[^/]*$|(^|/)Dockerfile')"

  # Debug mode and test accounts left in
  check_pattern FAIL DEBUG-ON "debug mode switched on, shows internals to visitors" \
    'app\.run\([^)]*debug[[:space:]]*=[[:space:]]*True|^[[:space:]]*DEBUG[[:space:]]*=[[:space:]]*True|FLASK_DEBUG[=: "]+1|APP_DEBUG[[:space:]]*=[[:space:]]*true|WP_DEBUG.{1,12}true'
  check_pattern WARN TEST-ACCOUNT "test or default login left in the code" \
    'password123|admin123|letmein|changeme|(admin|demo|test)@example\.(com|org)'

  # Browser-facing settings
  check_pattern WARN CORS-OPEN "answers requests from every website (fine only for a public read-only API)" \
    "Access-Control-Allow-Origin['\"]?[[:space:]]*[:,][[:space:]]*['\"]\*|origin:[[:space:]]*(['\"]\*['\"]|true)|origins?[[:space:]]*=[[:space:]]*\[?[[:space:]]*['\"]\*|CORS_ALLOW_ALL_ORIGINS[[:space:]]*=[[:space:]]*True|[^A-Za-z]CORS\([A-Za-z_]+\)|[^A-Za-z]cors\(\)"
  check_pattern WARN COOKIE-FLAGS "session cookie without Secure or HttpOnly" \
    'httpOnly:[[:space:]]*false|secure:[[:space:]]*false|SESSION_COOKIE_(SECURE|HTTPONLY)[^=]{0,4}=[[:space:]]*False'

  # Containers: run as root, unpinned base image
  for f in $(project_files | grep -E '(^|/)Dockerfile[^/]*$'); do
    [ -f "$f" ] || continue
    awk -v f="$f" '
      /^[[:space:]]*FROM[[:space:]]/ { i=2; while ($i ~ /^--/) i++; img=$i; if ($(i+1) ~ /^[Aa][Ss]$/) stages[$(i+2)]=1;
        if (img != "scratch" && img !~ /[:@$]/ && !(img in stages)) print "WARN  DOCKER-UNPINNED: base image has no version tag: " f ":" NR }
      /^[[:space:]]*USER[[:space:]]/ { user=$2 }
      END { if (user == "" || user == "root" || user == "0") print "WARN  DOCKER-ROOT: container runs as root: " f }
    ' "$f" >> "$OUT/release-checks.txt"
  done

  # Runtimes past end of support (only versions the project pins)
  for f in .nvmrc .node-version; do
    [ -f "$f" ] || continue
    v="$(tr -d 'v \r' < "$f" | head -1 | cut -d. -f1)"
    runtime_eol node "$v" "$f"
  done
  if [ -f package.json ]; then
    v="$(grep -E '"node"[[:space:]]*:' package.json | head -1 | sed 's/.*"node"[[:space:]]*:[[:space:]]*"//; s/".*//')"
    case "$v" in [0-9]*|v[0-9]*|\^[0-9]*|~[0-9]*) runtime_eol node "$(echo "$v" | tr -d 'v^~' | cut -d. -f1)" "package.json engines" ;; esac
  fi
  for f in .python-version runtime.txt; do
    [ -f "$f" ] || continue
    v="$(tr -d '\r' < "$f" | head -1 | sed 's/^python-//' | cut -d. -f1,2)"
    runtime_eol python "$v" "$f"
  done
  for f in $(project_files | grep -E '(^|/)Dockerfile[^/]*$'); do
    [ -f "$f" ] || continue
    v="$(grep -iE '^[[:space:]]*FROM[[:space:]]+node:[0-9]+' "$f" | head -1 | sed -E 's/.*node:([0-9]+).*/\1/')"
    [ -n "$v" ] && runtime_eol node "$v" "$f"
    v="$(grep -iE '^[[:space:]]*FROM[[:space:]]+python:3\.[0-9]+' "$f" | head -1 | sed -E 's/.*python:(3\.[0-9]+).*/\1/')"
    [ -n "$v" ] && runtime_eol python "$v" "$f"
  done

  # Reproducible installs, tests, automated checks, leaked source maps
  if has_trait node && ! has_trait pm-npm && ! has_trait pm-pnpm && ! has_trait pm-yarn && ! has_trait pm-bun; then
    echo "WARN  NO-LOCKFILE: no package lockfile, so installs are not repeatable and the dependency audit cannot run" >> "$OUT/release-checks.txt"
  fi
  if { has_trait node || has_trait python || has_trait dart; } && [ -z "$(project_files | grep -E '(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]*\.py$|_test\.(py|dart)$' | head -1)" ]; then
    echo "WARN  NO-TESTS: no automated tests found" >> "$OUT/release-checks.txt"
  fi
  if { has_trait node || has_trait python || has_trait dart; } && ! has_trait ci-github \
     && [ ! -f .gitlab-ci.yml ] && [ ! -f bitbucket-pipelines.yml ] && [ ! -f azure-pipelines.yml ] && [ ! -d .circleci ]; then
    echo "WARN  NO-CI: no automated checks run on each change" >> "$OUT/release-checks.txt"
  fi
  project_files | grep -E '\.map$' | grep -Ev '(^|/)node_modules/' | head -3 \
    | sed 's|^|WARN  SOURCEMAPS-COMMITTED: source map file in the repo (can reveal your original code if published): |' >> "$OUT/release-checks.txt"

  result release-checks release-checks.txt
}
