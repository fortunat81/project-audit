# Bugs and quality: type errors and lint, with each stack's own tools.
#   TypeScript -> tsc     JavaScript/TypeScript -> ESLint (only if the project has a config)
#   Python -> ruff        Flutter -> flutter analyze      Dart -> dart analyze

mod_applies() { has_trait node || has_trait python || has_trait dart; }
mod_tools() {
  has_trait python && echo ruff
  if has_trait flutter; then echo flutter; elif has_trait dart; then echo dart; fi
}

# Is there an ESLint config? Flat config, classic .eslintrc, or "eslintConfig" in package.json.
eslint_config_found() {
  any_file 'eslint.config.*' '.eslintrc' '.eslintrc.*' && return 0
  [ -f package.json ] && grep -q '"eslintConfig"' package.json
}

mod_run() {
  DIM="quality"

  # TypeScript: use the project's own compiler so versions and settings match
  if has_trait typescript; then
    if has_trait node && [ ! -d node_modules ]; then skip tsc "dependencies not installed (run: npm install)"
    elif [ -f node_modules/.bin/tsc ]; then
      note_version tsc "$(node_modules/.bin/tsc --version 2>/dev/null)"
      run --codes "1 2" --match 'error TS' tsc tsc.txt node_modules/.bin/tsc --noEmit
    elif has npx; then run --codes "1 2" --match 'error TS' tsc tsc.txt npx --yes -p typescript tsc --noEmit
    else skip tsc "npx not found"; fi
  fi

  # ESLint: the project's own binary so its plugins and config load
  if has_trait node; then
    if ! eslint_config_found; then skip eslint "no ESLint config in the project (looked for eslint.config.*, .eslintrc*, package.json)"
    elif [ ! -d node_modules ]; then skip eslint "dependencies not installed (run: npm install)"
    elif [ -f node_modules/.bin/eslint ]; then
      note_version eslint "$(node_modules/.bin/eslint --version 2>/dev/null)"
      run --json eslint eslint.json node_modules/.bin/eslint . -f json
    elif has npx; then run --json eslint eslint.json npx --yes eslint . -f json
    else skip eslint "npx not found"; fi
  fi

  # Python
  if has_trait python; then
    if has ruff; then
      note_version ruff "$(ruff --version 2>/dev/null)"
      run --json ruff ruff.json ruff check . --output-format json
    else skip ruff "not installed ($(install_hint ruff))"; fi
  fi

  # Dart / Flutter
  if has_trait flutter; then
    if has flutter; then
      note_version flutter "$(flutter --version 2>/dev/null | head -1)"
      run --codes "1" --match ' • ' flutter-analyze flutter-analyze.txt flutter analyze --no-pub
    else skip flutter-analyze "Flutter SDK not found ($(install_hint flutter))"; fi
  elif has_trait dart; then
    if has dart; then
      note_version dart "$(dart --version 2>&1 | head -1)"
      run --codes "1 2 3" --match ' - ' dart-analyze dart-analyze.txt dart analyze
    else skip dart-analyze "Dart SDK not found"; fi
  fi
}
