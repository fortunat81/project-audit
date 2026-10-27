"""Known vulnerabilities in dependencies.
  npm audit     npm projects (all dependencies, and separately only what ships to users)
  osv-scanner   every lockfile type: npm, pnpm, yarn, Dart/Flutter, Python, PHP, Ruby, Go, Rust...
  pip-audit     Python, resolving the project's requirements (not whatever Python is installed)"""
NAME = "20-dependencies"

LOCKFILES = ["package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "pubspec.lock", "poetry.lock",
             "Pipfile.lock", "requirements*.txt", "pdm.lock", "composer.lock", "Gemfile.lock", "go.mod", "Cargo.lock", "gradle.lockfile", "mix.lock"]


def has_lockfile(ctx):
    return ctx.any_file(*LOCKFILES)


def applies(ctx):
    return has_lockfile(ctx) or ctx.has_trait("node") or ctx.has_trait("python") or ctx.has_trait("dart")


def tools(ctx):
    out = ["osv-scanner"]
    if ctx.has_trait("python"):
        out.append("pip-audit")
    return out


def run(ctx):
    ctx.dim = "security"

    # npm audit
    if ctx.has_trait("node"):
        if not ctx.has("npm"):
            ctx.skip("npm-audit", "npm not found (%s)" % ctx.install_hint("npx"))
        elif ctx.untrusted:
            ctx.skip("npm-audit", "untrusted mode: npm reads the project's own .npmrc (osv-scanner checks the lockfile instead)")
        elif ctx.has_trait("pm-npm"):
            ctx.note_version("npm", ctx.run_text(["npm", "--version"]))
            ctx.run("npm-audit", "npm-audit.json", ["npm", "audit", "--json"], json=True, match=r'"auditReportVersion"')
            ctx.run("npm-audit-shipped", "npm-audit-shipped.json", ["npm", "audit", "--omit=dev", "--json"], json=True, match=r'"auditReportVersion"')
        elif any(ctx.has_trait(t) for t in ("pm-pnpm", "pm-yarn", "pm-bun")):
            ctx.skip("npm-audit", "not an npm lockfile (osv-scanner covers it)")
        else:
            ctx.skip("npm-audit", "no lockfile (run: npm i --package-lock-only)")

    # osv-scanner
    if not has_lockfile(ctx):
        ctx.skip("osv-scanner", "no lockfile found")
    elif not ctx.has("osv-scanner"):
        ctx.skip("osv-scanner", "not installed (%s)" % ctx.install_hint("osv-scanner"))
    else:
        ctx.note_version("osv-scanner", ctx.run_text(["osv-scanner", "--version"]))
        # exit 1 = vulnerabilities found, 128 = no packages found
        ctx.run("osv-scanner", "osv-scanner.json", ["osv-scanner", "scan", "source", "-r", "--format", "json", "."], json=True, ok=(128,))

    # pip-audit
    if ctx.has_trait("python"):
        if not ctx.has("pip-audit"):
            ctx.skip("pip-audit", "not installed (%s)" % ctx.install_hint("pip-audit"))
        elif ctx.untrusted:
            ctx.skip("pip-audit", "untrusted mode: pip-audit installs the packages to check them, which runs their setup code (osv-scanner checks the requirements instead)")
        else:
            ctx.note_version("pip-audit", ctx.run_text(["pip-audit", "--version"]))
            if ctx.isfile("requirements.txt"):
                ctx.run("pip-audit", "pip-audit.json", ["pip-audit", "-r", "requirements.txt", "-f", "json"], json=True)
            elif ctx.isfile("pyproject.toml"):
                ctx.run("pip-audit", "pip-audit.json", ["pip-audit", "-f", "json", "."], json=True)
            else:
                ctx.skip("pip-audit", "no requirements.txt or pyproject.toml")
