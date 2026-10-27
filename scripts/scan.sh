#!/usr/bin/env bash
# Project audit runner. Detects what the project is, then runs only the check modules
# in scripts/checks/ that apply to it. Saves raw output and records what happened.
# Never aborts: scanners exit non-zero when they find problems, which is normal.
#
# Usage (run from the project root):
#   bash scan.sh                  run the scan
#   bash scan.sh --detect         show what was detected and which modules apply (changes nothing)
#   bash scan.sh --all            scan this folder and every project folder in it, each with its own checks
#   bash scan.sh --projects       list project folders (this one and any in subfolders); audit each (changes nothing)
#   bash scan.sh --verify-report  check the finished AUDIT.md and scores.json for mistakes (changes nothing)
#   bash scan.sh --check          list missing tools and how to install them (changes nothing)
#   bash scan.sh --install        install the missing tools this project needs (see below)
#   bash scan.sh --install-deps   install this project's own packages (no install scripts) so tsc/eslint/knip can run
#   bash scan.sh --status         compare with the last audit and recommend quick or full (changes nothing)
#   bash scan.sh --version        branch, behind/ahead of GitHub, uncommitted files (runs git fetch only)
#   bash scan.sh --add-gitignore  add "audit/" to this folder's .gitignore (the scan never edits it on its own)
#
# Optional per-project settings in .audit.conf (plain key=value lines, never executed):
#   url=https://example.com       also check the live site (or set AUDIT_URL for one run)
#   skip=lizard,knip              tools to leave out
#   ignore=legacy/**,vendor/**    extra paths to leave out of duplication checks

set -u

ROOT="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKS_DIR="$SCRIPT_DIR/checks"
SKIPFILE="$ROOT/audit/.skip-tools"   # tools the user asked never to be offered again

# Tools fetched with npx are pinned so results don't change between audits just because a
# new version came out. Bump these on purpose; every run records the versions in versions.txt.
MADGE_PKG="madge@8.0.0"
JSCPD_PKG="jscpd@5.4.1"
KNIP_PKG="knip@6.9.0"
LIGHTHOUSE_PKG="lighthouse@13.4.1"

# ---------------------------------------------------------------- helpers ----

has() { command -v "$1" >/dev/null 2>&1; }
is_git() { git rev-parse --git-dir >/dev/null 2>&1; }

# Windows (Git Bash / MSYS / Cygwin)?
is_windows() { case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) return 0 ;; *) return 1 ;; esac; }

# A tool just installed with winget or "pip --user" may not be on PATH until the terminal
# restarts (or ever). Look in the places those installers use. Added at the END of PATH, so
# nothing already installed gets replaced.
add_path() { [ -d "$1" ] && case ":$PATH:" in *":$1:"*) ;; *) PATH="$PATH:$1" ;; esac; return 0; }
if is_windows && has cygpath; then
  if [ -n "${LOCALAPPDATA:-}" ]; then
    WINGET_DIR="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null)/Microsoft/WinGet"
    add_path "$WINGET_DIR/Links"
    # Some winget packages are not linked and stay in their own folder under Packages/
    for d in "$WINGET_DIR"/Packages/Gitleaks.Gitleaks_* "$WINGET_DIR"/Packages/Google.OSVScanner_*; do add_path "$d"; done
  fi
  if [ -n "${APPDATA:-}" ]; then
    for d in "$(cygpath -u "$APPDATA" 2>/dev/null)"/Python/Python*/Scripts; do add_path "$d"; done
  fi
fi
add_path "$HOME/.local/bin"                                  # pip --user on Linux and pipx
for d in "$HOME"/Library/Python/*/bin; do add_path "$d"; done # pip --user on macOS

# A usable GNU-style timeout, printed as e.g. "timeout 300" (or nothing).
# Windows has a different timeout.exe that only waits, so accept only GNU coreutils.
timeout_prefix() {
  if has timeout && timeout --version 2>&1 | grep -qi coreutils; then echo "timeout $1"
  elif has gtimeout; then echo "gtimeout $1"
  fi
}

# Read one value from .audit.conf. The file is read as text, never executed.
conf_get() { [ -f "$ROOT/.audit.conf" ] && grep -E "^[[:space:]]*$1[[:space:]]*=" "$ROOT/.audit.conf" | tail -1 | cut -d= -f2- | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }

AUDIT_URL="${AUDIT_URL:-$(conf_get url)}"
CONF_SKIP=",$(conf_get skip | tr -d ' '),"
CONF_IGNORE="$(conf_get ignore | tr -d ' ')"
conf_skipped() { case "$CONF_SKIP" in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

# Install command for a Python-based tool, using whatever Python installer exists here.
py_install_cmd() {
  if has pipx; then echo "pipx install $1"
  elif has pip3; then echo "pip3 install --user $1"
  elif has pip; then echo "pip install --user $1"
  elif has py; then echo "py -m pip install --user $1"
  else echo "install Python 3 first (https://www.python.org/downloads/), then: pipx install $1"; fi
}

install_hint() {
  case "$1" in
    semgrep)
      if has pipx; then echo "pipx install semgrep"; elif has brew; then echo "brew install semgrep"
      else py_install_cmd semgrep; fi ;;
    gitleaks)
      if is_windows && has winget; then echo "winget install -e --id Gitleaks.Gitleaks"
      elif has brew; then echo "brew install gitleaks"
      elif has go; then echo "go install github.com/gitleaks/gitleaks/v8@latest"
      else echo "download the release for your system from https://github.com/gitleaks/gitleaks/releases and put the gitleaks file in a folder on your PATH"; fi ;;
    osv-scanner)
      if is_windows && has winget; then echo "winget install -e --id Google.OSVScanner"
      elif has brew; then echo "brew install osv-scanner"
      elif has go; then echo "go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest"
      else echo "download the release for your system from https://github.com/google/osv-scanner/releases and put it on your PATH"; fi ;;
    ruff|zizmor)
      if has pipx; then echo "pipx install $1"; elif has brew; then echo "brew install $1"; else py_install_cmd "$1"; fi ;;
    pip-audit|lizard|mobsfscan)
      py_install_cmd "$1" ;;
    npx)
      echo "install Node.js from https://nodejs.org (it provides npm and npx)" ;;
    flutter)
      echo "install the Flutter SDK from https://docs.flutter.dev/get-started/install" ;;
    dart)
      echo "install the Dart SDK from https://dart.dev/get-dart" ;;
    curl)
      echo "install curl (it ships with Git for Windows and macOS)" ;;
  esac
}

# Every file that counts as part of the project: tracked plus new files git doesn't ignore.
# The audit's own output folder is never part of the project.
project_files() { git -c core.quotepath=false ls-files --cached --others --exclude-standard 2>/dev/null | grep -v '^audit/'; }

# ---------------------------------------------------------------- detection --
# Sets TRAITS (space-separated words), LANGS (top file extensions) and UNHANDLED
# (languages with many files but no dedicated module, so only generic checks apply).

TRAITS=" "
add_trait() { case "$TRAITS" in *" $1 "*) ;; *) TRAITS="$TRAITS$1 " ;; esac; }
has_trait() { case "$TRAITS" in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
pkg_has() { [ -f package.json ] && grep -Eq "\"$1\"[[:space:]]*:" package.json; }
pkg_has_prefix() { [ -f package.json ] && grep -Eq "\"$1[^\"]*\"[[:space:]]*:" package.json; }
py_has() { cat pyproject.toml requirements*.txt Pipfile setup.py 2>/dev/null | grep -Eiq "(^|[^a-z0-9_-])$1([^a-z0-9_-]|$)"; }
pub_has() { [ -f pubspec.yaml ] && grep -Eq "^[[:space:]]+$1[[:space:]]*:" pubspec.yaml; }
any_file() { local p; for p in "$@"; do compgen -G "$p" >/dev/null 2>&1 && return 0; done; return 1; }

detect() {
  is_git && add_trait git

  # JavaScript / TypeScript
  if [ -f package.json ]; then
    add_trait node
    if [ -f package-lock.json ] || [ -f npm-shrinkwrap.json ]; then add_trait pm-npm; fi
    [ -f pnpm-lock.yaml ] && add_trait pm-pnpm
    [ -f yarn.lock ] && add_trait pm-yarn
    if [ -f bun.lockb ] || [ -f bun.lock ]; then add_trait pm-bun; fi
    [ -f tsconfig.json ] && add_trait typescript
    if [ -f pnpm-workspace.yaml ] || [ -f turbo.json ] || [ -f nx.json ] || [ -f lerna.json ] || grep -q '"workspaces"' package.json; then add_trait monorepo; fi
    pkg_has expo && add_trait expo
    pkg_has react-native && add_trait react-native
    pkg_has next && add_trait next
    pkg_has astro && add_trait astro
    pkg_has vite && add_trait vite
    pkg_has nuxt && add_trait nuxt
    pkg_has vue && add_trait vue
    if pkg_has svelte || pkg_has @sveltejs/kit; then add_trait svelte; fi
    pkg_has_prefix @remix-run/ && add_trait remix
    pkg_has react && add_trait react
    for s in express fastify hono koa @nestjs/core; do pkg_has "$s" && add_trait server-framework; done
    for s in openai @anthropic-ai/sdk ai @google/generative-ai @google/genai groq-sdk cohere-ai replicate ollama @mistralai/mistralai langchain; do pkg_has "$s" && add_trait ai; done
    { pkg_has_prefix @ai-sdk/ || pkg_has_prefix @langchain/; } && add_trait ai
    for s in stripe @stripe/stripe-js @stripe/stripe-react-native @paypal/react-paypal-js square; do pkg_has "$s" && add_trait payments; done
    pkg_has @supabase/supabase-js && add_trait supabase
    for s in firebase firebase-admin @react-native-firebase/app; do pkg_has "$s" && add_trait firebase; done
  fi

  # Python
  if [ -f pyproject.toml ] || any_file 'requirements*.txt' || [ -f Pipfile ] || [ -f setup.py ]; then
    add_trait python
    for s in django flask fastapi; do py_has "$s" && add_trait server-framework; done
    for s in openai anthropic langchain google-generativeai google-genai; do py_has "$s" && add_trait ai; done
    py_has stripe && add_trait payments
    py_has supabase && add_trait supabase
    py_has firebase-admin && add_trait firebase
  fi

  # Dart / Flutter
  if [ -f pubspec.yaml ]; then
    add_trait dart
    grep -q 'sdk:[[:space:]]*flutter' pubspec.yaml && add_trait flutter
    for s in google_generative_ai dart_openai firebase_vertexai firebase_ai anthropic_sdk_dart; do pub_has "$s" && add_trait ai; done
    pub_has supabase_flutter && add_trait supabase
    pub_has firebase_core && add_trait firebase
    pub_has flutter_stripe && add_trait payments
  fi

  # PHP / WordPress
  if [ -f composer.json ] || [ -n "$(project_files | grep -m1 '\.php$')" ]; then
    add_trait php
    if [ -f wp-config.php ] || [ -d wp-content ]; then add_trait wordpress; fi
  fi

  # Backends configured by files rather than packages
  [ -d supabase ] && add_trait supabase
  if [ -f firebase.json ] || [ -f firestore.rules ] || [ -f database.rules.json ] || [ -f storage.rules ]; then add_trait firebase; fi

  # AI used through a plain HTTP call: no SDK in the dependencies, but the code talks to an AI provider
  if ! has_trait ai; then
    local ai_hosts='api\.openai\.com|api\.anthropic\.com|openrouter\.ai|generativelanguage\.googleapis\.com|api\.groq\.com|api\.mistral\.ai|api\.cohere\.(ai|com)|api\.together\.(xyz|ai)|api\.replicate\.com|api\.deepseek\.com|api\.x\.ai|api\.perplexity\.ai'
    if [ -n "$(project_files | grep -Ev "$NOISE_RE" | grep -E '\.(ts|tsx|js|jsx|mjs|cjs|py|dart|php)$' | tr '\n' '\0' | xargs -0 grep -lE "$ai_hosts" 2>/dev/null | head -1)" ]; then add_trait ai; fi
  fi

  # Native mobile code that is really yours (Expo and Flutter generate android/ and ios/)
  if ! has_trait expo && ! has_trait flutter; then
    if [ -d android ] && any_file 'android/build.gradle*' 'android/app/build.gradle*'; then add_trait native-android; fi
    if any_file '*.xcodeproj' 'ios/*.xcodeproj' 'Podfile' 'ios/Podfile'; then add_trait native-ios; fi
  fi
  for t in expo react-native flutter native-android native-ios; do has_trait "$t" && add_trait mobile; done

  # Websites
  if ! has_trait node && { [ -f index.html ] || [ -f public/index.html ]; }; then add_trait static-site; fi
  for t in next astro vite nuxt vue svelte remix static-site wordpress; do has_trait "$t" && add_trait web; done
  if has_trait react && ! has_trait react-native && ! has_trait expo; then add_trait web; fi

  # Code that runs on a server (API routes, serverless functions, backend frameworks)
  has_trait server-framework && add_trait server-code
  if has_trait next && any_file 'app/api' 'src/app/api' 'pages/api' 'src/pages/api'; then add_trait server-code; fi
  if [ -d supabase/functions ] || [ -f functions/package.json ] || [ -d netlify/functions ] || [ -d api ]; then add_trait server-code; fi
  has_trait php && add_trait server-code

  # Other
  any_file '.github/workflows/*.yml' '.github/workflows/*.yaml' && add_trait ci-github
  any_file 'Dockerfile' '*/Dockerfile' 'docker-compose*.yml' 'compose*.yml' && add_trait docker
  [ -n "$AUDIT_URL" ] && add_trait live-url

  # Language census by file extension
  LANGS="$(project_files | grep -E '\.[A-Za-z0-9]+$' | sed 's/.*\.//' | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn | head -8 | awk '{printf "%s%s(%s)", (NR>1?" ":""), $2, $1}')"
  UNHANDLED=""
  for ext in go rb php cs rs c cpp scala ex lua java kt swift; do
    case "$ext" in
      php) has_trait wordpress && continue ;;
      java|kt) has_trait native-android && continue ;;
      swift) has_trait native-ios && continue ;;
    esac
    n="$(project_files | grep -c "\.$ext\$")"
    [ "${n:-0}" -ge 5 ] && UNHANDLED="$UNHANDLED $ext($n)"
  done
  UNHANDLED="${UNHANDLED# }"
}

# Lines in lockfiles, minified, binary or generated files are noise when measuring size or change.
# Whole-name matches, so Clock.tsx or blocks/list.ts are NOT mistaken for lockfiles.
NOISE_RE='(^|/)(package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Cargo\.lock|Gemfile\.lock|poetry\.lock|composer\.lock|Podfile\.lock|pubspec\.lock)$|\.min\.(js|css)$|\.(svg|png|jpe?g|gif|ico|webp|ttf|otf|woff2?|pdf|mp4|mov|mp3|wav|zip)$|\.(g|freezed|gen|mocks)\.dart$|(^|/)(\.expo|\.next|\.nuxt|\.svelte-kit|\.astro|\.dart_tool|dist|build|out|coverage|Pods|vendor)/'
JSCPD_IGNORE='**/node_modules/**,**/dist/**,**/build/**,**/out/**,**/coverage/**,**/.expo/**,**/.next/**,**/.nuxt/**,**/.svelte-kit/**,**/.astro/**,**/.dart_tool/**,**/Pods/**,**/vendor/**,**/audit/**,**/*.min.js,**/*.g.dart,**/*.freezed.dart,**/*.gen.dart,**/*.lock,**/package-lock.json,**/pnpm-lock.yaml'

finish_detect() {
  # Expo and Flutter generate android/ and ios/; that code isn't the user's.
  if has_trait expo || has_trait flutter; then
    NOISE_RE="$NOISE_RE|^(android|ios)/"
    JSCPD_IGNORE="$JSCPD_IGNORE,**/android/**,**/ios/**"
  fi
  [ -n "$CONF_IGNORE" ] && JSCPD_IGNORE="$JSCPD_IGNORE,$CONF_IGNORE"
}

detect
finish_detect

# ------------------------------------------------------------ subprojects ----
# Project files can sit in subfolders (backend/, app/, web/) instead of the folder you run
# this from. Tools that need to run inside a project (dependency audit, tsc, eslint, pip-audit)
# only see the one they are started in, so list the others and tell the user to audit each.
ROOT_IS_PROJECT=no
if [ -f package.json ] || [ -f pyproject.toml ] || [ -f Pipfile ] || [ -f setup.py ] \
   || [ -f pubspec.yaml ] || [ -f composer.json ] || any_file 'requirements*.txt'; then ROOT_IS_PROJECT=yes; fi

PROJECT_FILE_RE='(^|/)(package\.json|pyproject\.toml|requirements[^/]*\.txt|Pipfile|setup\.py|pubspec\.yaml|composer\.json)$'
NOT_PRODUCT_RE='(^|/)(node_modules|test|tests|__tests__|e2e|example|examples|sample|samples|doc|docs|fixtures|fixture|demo|demos|vendor|android|ios)(/|$)'

# Folders up to 3 levels down that hold project files, one per line (empty if none).
# When this folder is itself a project, test/example/docs folders and monorepo packages are
# left out: they are covered from here or aren't the product.
find_subprojects() {
  local files dirs
  if is_git; then files="$(project_files)"
  else files="$(find . -maxdepth 4 -type f -not -path '*/node_modules/*' -not -path './audit/*' 2>/dev/null | sed 's|^\./||')"; fi
  dirs="$(echo "$files" | grep -E "$PROJECT_FILE_RE" | grep '/' | sed 's|/[^/]*$||' | awk -F/ 'NF<=3' | sort -u)"
  [ -z "$dirs" ] && return 0
  if [ "$ROOT_IS_PROJECT" = yes ]; then
    dirs="$(echo "$dirs" | grep -Ev "$NOT_PRODUCT_RE")"
    if has_trait monorepo; then dirs="$(echo "$dirs" | grep -Ev '^(packages|apps|libs|services)/')"; fi
  fi
  [ -n "$dirs" ] && echo "$dirs"
  return 0
}
SUBPROJECTS="$(find_subprojects | head -20 | tr '\n' ' ' | sed 's/ $//')"

# ---------------------------------------------------------------- modules ----
# Each file in checks/ defines:
#   mod_applies   return 0 if this module is relevant to the detected project
#   mod_tools     print the tools it needs (for --check); optional
#   mod_run       run the checks with run/skip/note (see below)

module_files() { ls "$CHECKS_DIR"/*.sh 2>/dev/null | sort; }
load_module() { unset -f mod_applies mod_tools mod_run 2>/dev/null; MOD_NAME="$(basename "$1" .sh)"; . "$1"; }

if [ "${1:-}" = "--detect" ]; then
  echo "TRAITS=$(echo $TRAITS)"
  echo "LANGUAGES=$LANGS"
  echo "UNHANDLED=${UNHANDLED:-none}"
  echo "LIVE_URL=${AUDIT_URL:-none}"
  for f in $(module_files); do
    load_module "$f"
    if mod_applies; then echo "MODULE=$MOD_NAME applies"; else echo "MODULE=$MOD_NAME not-applicable"; fi
  done
  exit 0
fi

if [ "${1:-}" = "--projects" ]; then
  [ "$ROOT_IS_PROJECT" = yes ] && echo "PROJECT=."
  for d in $SUBPROJECTS; do echo "PROJECT=$d"; done
  [ "$ROOT_IS_PROJECT" = no ] && [ -z "$SUBPROJECTS" ] && echo "PROJECT=. (no project files found; only the general checks apply)"
  exit 0
fi

# --- All-projects mode -------------------------------------------------------
#   bash scan.sh --all     scan this folder (secrets, history and every other general check cover the
#                          whole tree) and then every project folder from --projects, each in its own
#                          audit/ folder, so each one's stack is detected and gets its own checks.
if [ "${1:-}" = "--all" ]; then
  shift
  ALL_SUMMARY="$ROOT/audit/all-latest.txt"
  mkdir -p "$ROOT/audit"; : > "$ALL_SUMMARY"
  echo "##### . (whole folder)"
  AUDIT_ALL=1 bash "$SCRIPT_DIR/scan.sh" "$@"
  for d in $SUBPROJECTS; do
    echo; echo "##### $d"
    (cd "$ROOT/$d" && AUDIT_ALL=1 AUDIT_SUB=1 bash "$SCRIPT_DIR/scan.sh" "$@")
  done
  {
    printf "folder\tfindings\tpartial\tfailed\tskipped\ttraits\n"
    for d in . $SUBPROJECTS; do
      latest="$ROOT/$d/audit/latest.txt"; [ -f "$latest" ] || continue
      m="$(cat "$latest")/manifest.tsv"
      awk -F'\t' -v d="$d" -v tr="$(grep '^traits=' "$(cat "$latest")/meta.txt" | cut -d= -f2-)" \
        'NR>1 { if ($2=="findings") f++; else if ($2 ~ /^partial/) p++; else if ($2 ~ /^failed-to-run/ || $2=="timeout") x++; else if ($2 ~ /^skipped|^unavailable/) s++ }
         END { printf "%s\t%d\t%d\t%d\t%d\t%s\n", d, f, p, x, s, tr }' "$m"
    done
  } | tee "$ALL_SUMMARY"
  echo "Combined summary saved in: $ALL_SUMMARY"
  exit 0
fi

if [ "${1:-}" = "--verify-report" ]; then
  shift; exec bash "$SCRIPT_DIR/verify-report.sh" "$@"   # checks AUDIT.md and scores.json; changes nothing
fi

# --- Check mode --------------------------------------------------------------
# One line per tool the applicable modules need: OK | MISSING <tool> <command> | USER-SKIPPED
if [ "${1:-}" = "--check" ]; then
  echo "PROFILE=$(echo $TRAITS)"
  SEEN=" "
  want() {
    case "$SEEN" in *" $1 "*) return ;; esac
    SEEN="$SEEN$1 "
    if { [ -f "$SKIPFILE" ] && grep -qx "$1" "$SKIPFILE"; } || conf_skipped "$1"; then printf "USER-SKIPPED\t%s\n" "$1"
    elif has "$1"; then printf "OK\t%s\n" "$1"
    else printf "MISSING\t%s\t%s\n" "$1" "$(install_hint "$1")"; fi
  }
  for f in $(module_files); do
    load_module "$f"
    if mod_applies && type mod_tools >/dev/null 2>&1; then
      for t in $(mod_tools); do want "$t"; done
    fi
  done
  exit 0
fi

# --- Install mode ------------------------------------------------------------
#   bash scan.sh --install                    install every MISSING tool this project needs
#   bash scan.sh --install all                install every tool any module can use (for the tests)
#   bash scan.sh --install semgrep gitleaks   install just these
# Uses exactly the commands --check prints. Never uses sudo, and never installs a language
# SDK (Node.js, Flutter, Dart): for those it prints the download link. The first time,
# winget may ask you to accept its terms in the terminal; that's your choice to make.
if [ "${1:-}" = "--install" ]; then
  shift
  ALL_TOOLS="gitleaks semgrep osv-scanner pip-audit ruff lizard zizmor mobsfscan"
  if [ "${1:-}" = "all" ]; then WANT="$ALL_TOOLS"
  elif [ $# -gt 0 ]; then WANT="$*"
  else
    WANT=""
    for f in $(module_files); do
      load_module "$f"
      if mod_applies && type mod_tools >/dev/null 2>&1; then WANT="$WANT $(mod_tools)"; fi
    done
  fi
  N_OK=0; N_NEW=0; N_FAIL=0; N_MANUAL=0; NEED_RESTART=0
  for t in $(echo $WANT | tr ' ' '\n' | awk 'NF && !seen[$0]++'); do
    if has "$t"; then echo "OK         $t (already installed)"; N_OK=$((N_OK+1)); continue; fi
    if { [ -f "$SKIPFILE" ] && grep -qx "$t" "$SKIPFILE"; } || conf_skipped "$t"; then
      echo "SKIPPED    $t (you chose not to use it)"; continue
    fi
    cmd="$(install_hint "$t")"
    case "$cmd" in
      install*|download*) echo "MANUAL     $t: $cmd"; N_MANUAL=$((N_MANUAL+1)); continue ;;
    esac
    echo "INSTALLING $t: $cmd"
    # shellcheck disable=SC2086
    if $cmd; then
      N_NEW=$((N_NEW+1))
      has "$t" || NEED_RESTART=1
    else
      echo "FAILED     $t (the error is above; the audit will skip this tool)"; N_FAIL=$((N_FAIL+1))
    fi
  done
  echo
  echo "INSTALL SUMMARY: $N_NEW installed, $N_OK already there, $N_MANUAL need a manual install, $N_FAIL failed"
  if [ $NEED_RESTART -eq 1 ]; then
    echo "Some new tools aren't visible in this terminal yet: close it and open a new one."
    has pipx && echo "If they still aren't found after that, run: pipx ensurepath"
  fi
  [ $N_FAIL -eq 0 ]; exit $?
fi
# -----------------------------------------------------------------------------

# --- Install-deps mode -------------------------------------------------------
#   bash scan.sh --install-deps    install this project's own packages so tsc, eslint and knip can run
# Only creates node_modules/. Install scripts are switched off (--ignore-scripts) so a package
# can't run code during the install, and package-lock.json / pnpm-lock.yaml are not rewritten.
# Ask the user first: it downloads packages.
if [ "${1:-}" = "--install-deps" ]; then
  [ -f package.json ] || { echo "NOTHING: no package.json in this folder"; exit 0; }
  [ -d node_modules ] && { echo "ALREADY: node_modules exists"; exit 0; }
  if [ -f pnpm-lock.yaml ]; then
    has pnpm || { echo "MANUAL: this project uses pnpm, which isn't installed (https://pnpm.io/installation)"; exit 1; }
    echo "RUNNING: pnpm install --frozen-lockfile --ignore-scripts"
    pnpm install --frozen-lockfile --ignore-scripts; exit $?
  elif [ -f yarn.lock ] || [ -f bun.lockb ] || [ -f bun.lock ]; then
    echo "MANUAL: this project uses yarn or bun; install its packages yourself (without running install scripts if you can)"; exit 1
  fi
  has npm || { echo "MANUAL: npm not found ($(install_hint npx))"; exit 1; }
  if [ -f package-lock.json ] || [ -f npm-shrinkwrap.json ]; then
    echo "RUNNING: npm ci --ignore-scripts"; npm ci --ignore-scripts; exit $?
  fi
  echo "RUNNING: npm install --ignore-scripts --no-package-lock"
  npm install --ignore-scripts --no-package-lock; exit $?
fi

# --- Status mode -------------------------------------------------------------
# Compares the project now with the last saved audit and recommends quick or full.
# Thresholds: AUDIT_DAYS (30), AUDIT_COMMITS (50), AUDIT_LINES (3000).
if [ "${1:-}" = "--status" ]; then
  DAYS_LIMIT="${AUDIT_DAYS:-30}"; COMMITS_LIMIT="${AUDIT_COMMITS:-50}"; LINES_LIMIT="${AUDIT_LINES:-3000}"
  LAST="$(ls -d "$ROOT"/audit/20*_* 2>/dev/null | sort | tail -1)"
  PREV="$(ls -d "$ROOT"/audit/20*_* 2>/dev/null | sort | tail -2 | head -1)"
  [ "$PREV" = "$LAST" ] && PREV=""
  if [ -z "$LAST" ] || [ ! -f "$LAST/meta.txt" ]; then
    echo "LAST_AUDIT=none"; echo "RECOMMEND=full"; echo "REASON=no previous audit, so this run sets the baseline"; exit 0
  fi
  meta() { grep "^$1=" "$LAST/meta.txt" 2>/dev/null | head -1 | cut -d= -f2-; }
  LAST_DATE="$(meta date)"; LAST_EPOCH="$(meta epoch)"; LAST_COMMIT="$(meta commit)"; LAST_TRAITS="$(meta traits)"
  NOW="$(date +%s)"; DAYS=$(( (NOW - ${LAST_EPOCH:-$NOW}) / 86400 ))
  COMMITS="unknown"; LINES="unknown"; DEPS_CHANGED="no"
  if [ -n "$LAST_COMMIT" ] && [ "$LAST_COMMIT" != "none" ] && git cat-file -e "$LAST_COMMIT^{commit}" 2>/dev/null; then
    COMMITS="$(git rev-list --count "$LAST_COMMIT"..HEAD 2>/dev/null || echo unknown)"
    TRACKED_LINES="$(git -c core.quotepath=false diff --numstat "$LAST_COMMIT" -- . ':!audit' 2>/dev/null \
      | RE="$NOISE_RE" awk -F'\t' '$3 !~ ENVIRON["RE"] {a+=$1; d+=$2} END{print a+d+0}')"
    NEW_LINES="$(git ls-files -z --others --exclude-standard 2>/dev/null | tr '\0' '\n' | grep -v '^audit/' | grep -Ev "$NOISE_RE" \
      | tr '\n' '\0' | xargs -0 cat 2>/dev/null | wc -l | tr -d ' ')"
    LINES=$(( TRACKED_LINES + ${NEW_LINES:-0} ))
    if [ -n "$(git diff --name-only "$LAST_COMMIT" -- package.json package-lock.json pnpm-lock.yaml yarn.lock requirements.txt pyproject.toml poetry.lock pubspec.yaml pubspec.lock composer.json composer.lock 2>/dev/null)" ]; then DEPS_CHANGED="yes"; fi
  fi
  LAST_HOLES="$(awk -F'\t' 'NR>1 && ($2 ~ /^failed-to-run/ || $2=="timeout") {n++} END{print n+0}' "$LAST/manifest.tsv" 2>/dev/null)"
  NOW_TRAITS="$(echo $TRAITS | sed 's/ *live-url//')"
  echo "LAST_AUDIT=$LAST_DATE"; echo "LAST_FOLDER=$LAST"; echo "PREV_FOLDER=$PREV"
  echo "DAYS_SINCE=$DAYS"; echo "COMMITS_SINCE=$COMMITS"
  echo "LINES_CHANGED_SINCE=$LINES   (committed, staged, unstaged and new files)"
  echo "DEPENDENCY_FILES_CHANGED=$DEPS_CHANGED"
  echo "LAST_AUDIT_FAILED_CHECKS=$LAST_HOLES"
  REASONS=()
  if [ -n "$LAST_TRAITS" ] && [ "$LAST_TRAITS" != "$NOW_TRAITS" ]; then
    echo "PROFILE_CHANGED=yes (was: $LAST_TRAITS)"
    REASONS+=("the project's makeup changed since the last audit (new framework, backend or feature)")
  fi
  [ "$DEPS_CHANGED" = "yes" ] && REASONS+=("dependency files changed since the last audit")
  [ "${LAST_HOLES:-0}" -gt 0 ] && REASONS+=("the last audit had $LAST_HOLES check(s) that failed or timed out, so it left gaps")
  [ "$DAYS" -ge "$DAYS_LIMIT" ] && REASONS+=("$DAYS days since the last audit (limit $DAYS_LIMIT)")
  if [ "$COMMITS" != "unknown" ] && [ "$COMMITS" -ge "$COMMITS_LIMIT" ]; then REASONS+=("$COMMITS commits since the last audit (limit $COMMITS_LIMIT)"); fi
  if [ "$LINES" != "unknown" ] && [ "$LINES" -ge "$LINES_LIMIT" ]; then REASONS+=("$LINES lines changed since the last audit (limit $LINES_LIMIT)"); fi
  if [ ${#REASONS[@]} -gt 0 ]; then
    echo "RECOMMEND=full"; for r in "${REASONS[@]}"; do echo "REASON=$r"; done
  else
    echo "RECOMMEND=quick"
    if [ "$COMMITS" = "unknown" ]; then echo "REASON=only $DAYS days since the last audit (no git history to measure changes)"
    else echo "REASON=small change since the last audit"; fi
  fi
  exit 0
fi

# --- Version mode ------------------------------------------------------------
if [ "${1:-}" = "--version" ]; then
  if ! is_git; then echo "IS_GIT=no"; exit 0; fi
  echo "IS_GIT=yes"
  echo "BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  echo "COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo none)"
  UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  echo "UPSTREAM=${UPSTREAM:-none}"
  MODIFIED="$(git status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
  UNTRACKED="$(git ls-files --others --exclude-standard 2>/dev/null | grep -vc '^audit/' | tr -d ' ')"
  echo "UNCOMMITTED_FILES=$MODIFIED"; echo "UNTRACKED_FILES=$UNTRACKED"
  if [ -z "$UPSTREAM" ]; then echo "FETCH=no-upstream"; echo "AHEAD=unknown"; echo "BEHIND=unknown"; echo "CAN_FAST_FORWARD=no"; exit 0; fi
  FT="$(timeout_prefix 30)"
  if [ "${AUDIT_NO_FETCH:-0}" = "1" ]; then echo "FETCH=skipped"
  elif $FT git fetch --quiet 2>/dev/null; then echo "FETCH=ok"; else echo "FETCH=failed"; fi
  COUNTS="$(git rev-list --left-right --count HEAD...@{u} 2>/dev/null || echo "0 0")"
  read -r AHEAD BEHIND <<< "$COUNTS"
  echo "AHEAD=$AHEAD"; echo "BEHIND=$BEHIND"
  if [ "$BEHIND" -gt 0 ] && [ "$AHEAD" -eq 0 ] && [ "$MODIFIED" -eq 0 ]; then echo "CAN_FAST_FORWARD=yes"; else echo "CAN_FAST_FORWARD=no"; fi
  exit 0
fi

# --- Add-gitignore mode ------------------------------------------------------
if [ "${1:-}" = "--add-gitignore" ]; then
  if [ -f .gitignore ] && grep -qx 'audit/' .gitignore; then echo "ALREADY: audit/ is in .gitignore"
  else
    [ -f .gitignore ] && [ -n "$(tail -c1 .gitignore)" ] && echo >> .gitignore
    echo 'audit/' >> .gitignore && echo "ADDED: audit/ to $ROOT/.gitignore"
  fi
  exit 0
fi

# ================================================================= scan =====

# Unique folder per run (seconds, plus a counter if two runs start in the same second)
STAMP="$(date +%Y-%m-%d_%H%M%S)"
OUT="$ROOT/audit/$STAMP"; n=1
while [ -e "$OUT" ]; do n=$((n+1)); OUT="$ROOT/audit/$STAMP-$n"; done
mkdir -p "$OUT"
MANIFEST="$OUT/manifest.tsv"
printf "tool\tstatus\texit\toutput\tdimension\n" > "$MANIFEST"
: > "$OUT/versions.txt"

{
  echo "date=$(date +%Y-%m-%d)"
  echo "epoch=$(date +%s)"
  echo "traits=$(echo $TRAITS | sed 's/ *live-url//')"
  echo "languages=$LANGS"
  echo "unhandled_languages=${UNHANDLED:-none}"
  echo "live_url=${AUDIT_URL:-none}"
  if is_git; then
    echo "commit=$(git rev-parse --verify -q HEAD || echo none)"
    echo "branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo none)"
    echo "uncommitted_files=$(git status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
    echo "untracked_files=$(git ls-files --others --exclude-standard 2>/dev/null | grep -vc '^audit/' | tr -d ' ')"
    echo "ahead_behind_upstream=$(git rev-list --left-right --count HEAD...@{u} 2>/dev/null | tr '\t' '/' || echo unknown)"
    echo "audit_folder_ignored=$(git check-ignore -q audit/ 2>/dev/null && echo yes || echo no)"
  else
    echo "commit=none"
  fi
} > "$OUT/meta.txt"

# --- Provenance: what exactly was audited, with which settings, and did it stay the same? ---
# hash_stdin prints a short hash of whatever it reads (whichever hash tool this machine has).
hash_stdin() {
  if has sha1sum; then sha1sum | cut -c1-12
  elif has shasum; then shasum | cut -c1-12
  elif has md5sum; then md5sum | cut -c1-12
  elif has md5; then md5 | cut -c1-12
  else cksum | tr ' ' '-'; fi
}
# A fingerprint of the project files as they are right now (commit, edits, new files and their sizes).
# The audit's own folder is left out.
fingerprint() {
  {
    if is_git; then
      git rev-parse HEAD 2>/dev/null
      git diff HEAD -- . ':!audit' 2>/dev/null
      git ls-files --others --exclude-standard 2>/dev/null | grep -v '^audit/' | while IFS= read -r f; do [ -f "$f" ] && printf '%s %s
' "$f" "$(wc -c < "$f" | tr -d ' ')"; done
    else
      find . -type f -not -path './audit/*' -not -path '*/node_modules/*' -not -path './.git/*' 2>/dev/null | head -5000 | sort | while IFS= read -r f; do printf '%s %s
' "$f" "$(wc -c < "$f" | tr -d ' ')"; done
    fi
  } | hash_stdin
}
{
  echo "fingerprint_start=$(fingerprint)"
  echo "methodology_commit=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "settings_hash=$({ cat "$SCRIPT_DIR/gitleaks-extra.toml" "$ROOT/.audit.conf" 2>/dev/null; echo "semgrep_config=p/default"; } | hash_stdin)"
  echo "semgrep_rules=p/default, downloaded at scan time (not pinned): results can change when the rules are updated"
  echo "os=$(uname -s 2>/dev/null) $(uname -m 2>/dev/null)"
} >> "$OUT/meta.txt"

TO="$(timeout_prefix 300)"

# DIM is the score dimension the next rows feed; modules set it before each run.
DIM="general"
record() { printf "%s\t%s\t%s\t%s\t%s\n" "$1" "$2" "$3" "$4" "$DIM" >> "$MANIFEST"; }
skip() { echo "==> $1 (skipped: $2)"; record "$1" "skipped: $2" "-" "-"; }
note_version() { [ -n "$2" ] && printf "%s\t%s\n" "$1" "$2" >> "$OUT/versions.txt"; }

if [ -z "$TO" ]; then
  echo "WARNING: no GNU timeout found, so scanners run WITHOUT a time limit (macOS: brew install coreutils)."
  record time-limit "unavailable: no GNU timeout/gtimeout, scanners ran without a time limit" "-" "-"
  echo "time_limit=unavailable" >> "$OUT/meta.txt"
else
  echo "time_limit=300s" >> "$OUT/meta.txt"
fi
if is_git && ! git check-ignore -q audit/ 2>/dev/null; then
  echo "WARNING: audit/ is not git-ignored. Don't commit it. Run: bash scan.sh --add-gitignore"
fi

# Evaluate a small expression over a JSON file with node, or Python if there's no node.
#   json_eval <file> <js expression using d> <python expression using d>
json_eval() {
  if has node; then node -e 'const d=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));console.log(('"$2"'))' "$1" 2>/dev/null; return; fi
  local py; for py in python3 python; do
    if has "$py" && "$py" -c 'import json' >/dev/null 2>&1; then
      "$py" -c 'import json,sys;d=json.load(open(sys.argv[1],encoding="utf-8"));print('"$3"')' "$1" 2>/dev/null; return
    fi
  done
}

# Does the file start like JSON?
json_looking() { [ -s "$1" ] && tr -d ' \t\r\n' < "$1" | head -c 1 | grep -q '[{[]'; }

# run [options] <name> <outfile> <command...>
#   --codes "1 2"   exit codes that mean "ran and found problems" (default: 1)
#   --json          the output must look like JSON, or the run counts as failed
#   --match RE      on a findings exit code, the output must match RE (e.g. 'error TS')
#   --empty RE      decide by content instead of exit code: output matching RE means clean
#   --stdout FILE   send console text to FILE (for tools that write their own report to <outfile>)
#   --ok "128"      extra exit codes that mean "ran, nothing to report" (recorded as clean)
#   --done          the tool measures rather than judges: success is recorded as "done"
# stderr always goes to <outfile>.err. Respects skip= in .audit.conf.
run() {
  local codes=" 1 " okc=" " json=0 match="" empty="" so="" done=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --codes) codes=" $2 "; shift 2 ;;
      --ok) okc=" $2 "; shift 2 ;;
      --json) json=1; shift ;;
      --match) match="$2"; shift 2 ;;
      --empty) empty="$2"; shift 2 ;;
      --stdout) so="$2"; shift 2 ;;
      --done) done=1; codes=" "; shift ;;   # measurements have no "findings" exit code
      *) break ;;
    esac
  done
  local name="$1" file="$2"; shift 2
  if conf_skipped "$name"; then skip "$name" "turned off in .audit.conf"; return; fi
  echo "==> $name"
  $TO "$@" > "$OUT/${so:-$file}" 2> "$OUT/$file.err"
  local code=$? status=""
  local f="$OUT/$file"
  if [ $code -eq 124 ]; then status="timeout"
  elif [[ "$okc" == *" $code "* ]]; then status="clean"
  elif [ -n "$empty" ] && { [ $code -eq 0 ] || [[ "$codes" == *" $code "* ]]; }; then
    if [ $json -eq 1 ] && ! json_looking "$f"; then status="failed"
    elif grep -Eq "$empty" "$f"; then status="clean"; else status="findings"; fi
  elif [ $code -eq 0 ]; then
    if [ $json -eq 1 ] && ! json_looking "$f"; then status="failed"
    elif [ $done -eq 1 ]; then status="done"; else status="clean"; fi
  elif [[ "$codes" == *" $code "* ]]; then
    if [ $json -eq 1 ] && ! json_looking "$f"; then status="failed"
    elif [ -n "$match" ] && ! grep -Eq "$match" "$f"; then status="failed"
    else status="findings"; fi
  else status="failed"; fi
  [ "$status" = failed ] && status="failed-to-run (see $file.err)"
  record "$name" "$status" "$code" "$file"
}

# Record the result of a check done by the script itself (no external tool):
#   result <name> <outfile>   -> findings if outfile has content, clean if empty
result() {
  if [ -s "$OUT/$2" ]; then record "$1" "findings" "-" "$2"; else record "$1" "clean" "-" "$2"; fi
}

# Project folders this run does not cover must show up as a gap, not vanish silently
if [ -n "$SUBPROJECTS" ] && [ "${AUDIT_ALL:-0}" = 1 ] && [ "$ROOT" = "$(pwd)" ] && [ -z "${AUDIT_SUB:-}" ]; then
  DIM="general"
  echo "==> subprojects (scanned separately by --all)"
  record subprojects "done: each project folder was scanned separately by --all: $SUBPROJECTS" "-" "-"
  echo "subprojects=$SUBPROJECTS" >> "$OUT/meta.txt"
elif [ -n "$SUBPROJECTS" ]; then
  DIM="general"
  echo "==> subprojects (partial: not scanned)"
  record subprojects "partial: more project folders found: $SUBPROJECTS (the checks that need a project folder ran only here; audit each folder separately)" "-" "-"
  echo "subprojects=$SUBPROJECTS" >> "$OUT/meta.txt"
fi

# Run every applicable module
APPLIED=""; NOT_APPLIED=""
for f in $(module_files); do
  load_module "$f"
  if ! type mod_applies >/dev/null 2>&1 || ! type mod_run >/dev/null 2>&1; then
    # A broken module must show up as a gap, not vanish silently
    DIM="general"; record "module:$MOD_NAME" "failed-to-run (module file is broken: $(basename "$f"))" "-" "-"
    continue
  fi
  if mod_applies; then
    APPLIED="$APPLIED $MOD_NAME"
    DIM="general"
    mod_run
  else
    NOT_APPLIED="$NOT_APPLIED $MOD_NAME"
  fi
done
echo "modules_run=${APPLIED# }" >> "$OUT/meta.txt"
echo "modules_not_applicable=${NOT_APPLIED# }" >> "$OUT/meta.txt"

# Did the project change while the scanners were running? Then the results may mix two versions.
FP_START="$(grep '^fingerprint_start=' "$OUT/meta.txt" | cut -d= -f2-)"; FP_END="$(fingerprint)"
echo "fingerprint_end=$FP_END" >> "$OUT/meta.txt"
if [ "$FP_START" = "$FP_END" ]; then echo "consistent=yes" >> "$OUT/meta.txt"
else
  echo "consistent=no" >> "$OUT/meta.txt"
  DIM="general"; record consistency "partial: project files changed while the scan was running, so results may mix two versions (run the scan again)" "-" "-"
fi
if is_git; then echo "commit_end=$(git rev-parse --verify -q HEAD || echo none)" >> "$OUT/meta.txt"; fi

echo "$OUT" > "$ROOT/audit/latest.txt"

# Coverage summary: how much of the audit actually ran
awk -F'\t' 'NR>1 {
  if ($2=="clean") c++; else if ($2=="findings") f++; else if ($2=="done") d++;
  else if ($2=="timeout") t++; else if ($2 ~ /^failed-to-run/) x++; else if ($2 ~ /^partial/) p++;
  else s++; n++ }
  END { printf "COVERAGE: %d checks: %d clean, %d with findings, %d measured, %d partial, %d failed, %d timed out, %d skipped/unavailable\n", n, c, f, d, p, x, t, s }' "$MANIFEST" | tee "$OUT/coverage.txt"
if awk -F'\t' 'NR>1 && ($2 ~ /^failed-to-run/ || $2=="timeout" || $2 ~ /^skipped/ || $2 ~ /^unavailable/ || $2 ~ /^partial/) {found=1} END{exit !found}' "$MANIFEST"; then
  echo "INCOMPLETE: some checks did not run fully. A clean result does not cover them:" | tee -a "$OUT/coverage.txt"
  awk -F'\t' 'NR>1 && ($2 ~ /^failed-to-run/ || $2=="timeout" || $2 ~ /^skipped/ || $2 ~ /^unavailable/ || $2 ~ /^partial/) {print "  - " $1 ": " $2}' "$MANIFEST" | tee -a "$OUT/coverage.txt"
fi
[ -n "$UNHANDLED" ] && echo "NO DEDICATED CHECKS for: $UNHANDLED (only the generic security, secret and dependency checks cover these files)" | tee -a "$OUT/coverage.txt"
echo
echo "Profile: $(echo $TRAITS)"
echo "Done. Results saved in: $OUT"
cat "$MANIFEST"
