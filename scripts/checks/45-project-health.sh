# Project health for JavaScript/TypeScript: dead code and unused dependencies (knip),
# and for Expo apps, SDK/library mismatches and deprecated packages (expo-doctor).

mod_applies() { has_trait node; }
mod_tools() { echo npx; }

mod_run() {
  DIM="quality,spaghettiness"
  if ! has npx; then
    skip knip "npx not found ($(install_hint npx))"
    has_trait expo && skip expo-doctor "npx not found"
    return
  fi

  # Unused files, exports and dependencies. Needs installed dependencies to read the project's config.
  if [ ! -d node_modules ]; then skip knip "dependencies not installed (offer: scan.sh --install-deps)"
  else
    note_version knip "$KNIP_PKG"
    run --json knip knip.json npx --yes "$KNIP_PKG" --reporter json --no-progress
  fi

  # Expo: checks the project against its SDK version (needs network)
  if has_trait expo; then
    DIM="quality"
    if [ ! -d node_modules ]; then skip expo-doctor "dependencies not installed (offer: scan.sh --install-deps)"
    else
    note_version expo-doctor "latest via npx (follows the Expo SDK)"
    run --match 'checks? (passed|failed)|[0-9]+/[0-9]+ checks' expo-doctor expo-doctor.txt npx --yes expo-doctor
    fi
  fi
}
