# Known vulnerabilities in dependencies.
#   npm audit     npm projects (all dependencies, and separately only what ships to users)
#   osv-scanner   every lockfile type: npm, pnpm, yarn, Dart/Flutter, Python, PHP, Ruby, Go, Rust...
#   pip-audit     Python, resolving the project's requirements (not whatever Python is installed)

has_lockfile() {
  any_file package-lock.json npm-shrinkwrap.json pnpm-lock.yaml yarn.lock bun.lock pubspec.lock \
    poetry.lock Pipfile.lock 'requirements*.txt' pdm.lock composer.lock Gemfile.lock go.mod Cargo.lock gradle.lockfile mix.lock
}

mod_applies() { has_lockfile || has_trait node || has_trait python || has_trait dart; }

mod_tools() {
  echo osv-scanner
  has_trait python && echo pip-audit
}

mod_run() {
  DIM="security"

  # npm audit
  if has_trait node; then
    if ! has npm; then skip npm-audit "npm not found ($(install_hint npx))"
    elif [ "$UNTRUSTED" = 1 ]; then skip npm-audit "untrusted mode: npm reads the project's own .npmrc (osv-scanner checks the lockfile instead)"
    elif has_trait pm-npm; then
      note_version npm "$(npm --version 2>/dev/null)"
      run --json --match '"auditReportVersion"' npm-audit npm-audit.json npm audit --json
      run --json --match '"auditReportVersion"' npm-audit-shipped npm-audit-shipped.json npm audit --omit=dev --json
    elif has_trait pm-pnpm || has_trait pm-yarn || has_trait pm-bun; then
      skip npm-audit "not an npm lockfile (osv-scanner covers it)"
    else
      skip npm-audit "no lockfile (run: npm i --package-lock-only)"
    fi
  fi

  # osv-scanner
  if ! has_lockfile; then
    skip osv-scanner "no lockfile found"
  elif ! has osv-scanner; then
    skip osv-scanner "not installed ($(install_hint osv-scanner))"
  else
    note_version osv-scanner "$(osv-scanner --version 2>/dev/null | head -1)"
    # exit 1 = vulnerabilities found, 128 = no packages found
    run --json --ok "128" osv-scanner osv-scanner.json osv-scanner scan source -r --format json .
  fi

  # pip-audit
  if has_trait python; then
    if ! has pip-audit; then skip pip-audit "not installed ($(install_hint pip-audit))"
    elif [ "$UNTRUSTED" = 1 ]; then skip pip-audit "untrusted mode: pip-audit installs the packages to check them, which runs their setup code (osv-scanner checks the requirements instead)"
    else
      note_version pip-audit "$(pip-audit --version 2>/dev/null | head -1)"
      if [ -f requirements.txt ]; then run --json pip-audit pip-audit.json pip-audit -r requirements.txt -f json
      elif [ -f pyproject.toml ]; then run --json pip-audit pip-audit.json pip-audit -f json .
      else skip pip-audit "no requirements.txt or pyproject.toml"; fi
    fi
  fi
}
