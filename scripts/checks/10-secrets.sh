# Secrets in git history, and in files not committed yet (gitleaks). Applies to every project.
# Values are redacted, so no report ever contains a secret.

mod_applies() { return 0; }
mod_tools() { echo gitleaks; }

mod_run() {
  DIM="security"
  if ! has gitleaks; then
    skip gitleaks "not installed ($(install_hint gitleaks))"
    skip gitleaks-uncommitted "gitleaks not installed"
    return
  fi
  note_version gitleaks "$(gitleaks version 2>/dev/null | head -1)"
  # gitleaks' own rules plus one for NAME=value secrets (scripts/gitleaks-extra.toml)
  local CFG="$SCRIPT_DIR/gitleaks-extra.toml"

  if ! is_git; then
    # No history to read: scan the folder as it is.
    run --json --stdout gitleaks.stdout gitleaks gitleaks.json \
      gitleaks detect --no-git --source . --config "$CFG" --redact --report-format json --report-path "$OUT/gitleaks.json" --no-banner
    record gitleaks-uncommitted "skipped: not a git repo (the folder scan above covers all files)" "-" "-"
    return
  fi

  # 1. Every commit in history
  run --json --stdout gitleaks.stdout gitleaks gitleaks.json \
    gitleaks detect --source . --config "$CFG" --redact --report-format json --report-path "$OUT/gitleaks.json" --no-banner

  # 2. Staged, unstaged and brand-new files (a history scan can't see them)
  local UNC f
  UNC="$(mktemp -d 2>/dev/null || mktemp -d -t auditscan)"
  {
    if git rev-parse --verify -q HEAD >/dev/null; then git diff --name-only -z --relative HEAD
    else git diff --name-only -z --relative --cached; fi
    git ls-files -z --others --exclude-standard
  } | while IFS= read -r -d '' f; do
    case "$f" in audit/*) continue ;; esac
    [ -f "$f" ] && [ "$(wc -c < "$f" | tr -d ' ')" -lt 1000000 ] || continue
    mkdir -p "$UNC/$(dirname "$f")" && cp "$f" "$UNC/$f" 2>/dev/null
  done
  # .env files are usually git-ignored, so the lists above miss them. They still matter:
  # an ignored .env can be synced, zipped or pasted somewhere. Scan them too.
  for f in .env .env.*; do
    [ -f "$f" ] && cp "$f" "$UNC/$f" 2>/dev/null
  done
  if [ -n "$(find "$UNC" -type f 2>/dev/null | head -1)" ]; then
    run --json --stdout gitleaks-uncommitted.stdout gitleaks-uncommitted gitleaks-uncommitted.json bash -c \
      'cd "$1" && gitleaks detect --no-git --source . --config "$3" --redact --report-format json --report-path "$2" --no-banner' \
      _ "$UNC" "$OUT/gitleaks-uncommitted.json" "$CFG"
  else
    record gitleaks-uncommitted "clean" "-" "-"
  fi
  rm -rf "$UNC"
}
