# Secrets that get bundled into the app or website, and .env hygiene.
# Variables with these prefixes are copied into the code users download (EXPO_PUBLIC_, NEXT_PUBLIC_,
# VITE_, REACT_APP_, ...). A secret there is readable by anyone. Only NAMES are reported, never values.

mod_applies() { return 0; }

CLIENT_PREFIX='(EXPO_PUBLIC_|NEXT_PUBLIC_|VITE_|REACT_APP_|NUXT_PUBLIC_|PUBLIC_|GATSBY_|STORYBOOK_)'
SECRETISH='(SECRET|PRIVATE|SERVICE_ROLE|PASSWORD|PASSWD|OPENAI|ANTHROPIC|CLAUDE|GEMINI|GROQ|MISTRAL|COHERE|REPLICATE|STRIPE_SECRET|SK_LIVE|TOKEN|API_KEY|APIKEY|ADMIN|WEBHOOK)'

mod_run() {
  DIM="security"
  local f

  # 1. Client-bundled variable names that look like secrets (names only: grep -o prints just the match)
  : > "$OUT/exposed-keys.txt"
  {
    project_files | grep -Ev "$NOISE_RE" | grep -Ev '\.(md|lock)$'
    for f in .env .env.*; do [ -f "$f" ] && echo "$f"; done   # ignored .env files are still bundled
  } | sort -u | tr '\n' '\0' \
    | xargs -0 grep -HnoIE "${CLIENT_PREFIX}[A-Z0-9_]*${SECRETISH}[A-Z0-9_]*" 2>/dev/null \
    | sort -u | sed 's/^/CLIENT-VISIBLE: /' >> "$OUT/exposed-keys.txt"

  # 2. Expo config "extra" is bundled into the app too
  for f in app.json app.config.js app.config.ts; do
    [ -f "$f" ] || continue
    grep -noiE '"?[A-Za-z0-9_]*(secret|api_?key|token|password|private)[A-Za-z0-9_]*"?[[:space:]]*:' "$f" 2>/dev/null \
      | sed "s|^|IN APP CONFIG (bundled): $f:|" >> "$OUT/exposed-keys.txt"
  done
  result exposed-keys exposed-keys.txt

  # 3. .env hygiene: committed .env files, and .env files git would pick up
  : > "$OUT/env-files.txt"
  if is_git; then
    git ls-files | grep -E '(^|/)\.env(\.[A-Za-z0-9_-]+)?$' | grep -Ev '\.(example|sample|template|dist|defaults)$' \
      | sed 's/^/COMMITTED TO GIT (rotate what it held): /' >> "$OUT/env-files.txt"
    for f in .env .env.local .env.production .env.development; do
      [ -f "$f" ] || continue
      git ls-files --error-unmatch "$f" >/dev/null 2>&1 && continue   # already reported as committed
      git check-ignore -q "$f" 2>/dev/null || echo "NOT GIT-IGNORED (one 'git add .' from being committed): $f" >> "$OUT/env-files.txt"
    done
  fi
  result env-files env-files.txt
}
