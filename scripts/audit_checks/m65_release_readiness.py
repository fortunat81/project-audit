"""Release readiness: things that should not reach production, checked from the files alone.
  debug mode left on, open CORS, weak cookie flags, leftover test accounts, containers running as
  root or on an unpinned image, runtimes past end of support, no lockfile, no tests, no automated
  checks. No external tools. Results in release-checks.txt as FAIL / WARN lines (file:line only,
  never the matching text). reviews/release-gate.md says how each line feeds the go/no-go call."""
import os
import re
import time

from audit_core import read_text

NAME = "65-release-readiness"

# End-of-support dates (YYYY-MM-DD) for the runtimes projects pin. Refreshed 2026-10; a runtime
# missing from the table is not judged. Update from https://endoflife.date when it gets old.
EOL = {
    ("node", "14"): "2023-04-30", ("node", "16"): "2023-09-11", ("node", "18"): "2025-04-30", ("node", "20"): "2026-04-30",
    ("node", "22"): "2027-04-30", ("node", "24"): "2028-04-30", ("python", "3.7"): "2023-06-27", ("python", "3.8"): "2024-10-07",
    ("python", "3.9"): "2025-10-31", ("python", "3.10"): "2026-10-31", ("python", "3.11"): "2027-10-31", ("python", "3.12"): "2028-10-31",
}

FILE_FILTER_OUT = re.compile(r"(^|/)(tests?|__tests__|specs?|fixtures?|docs?|examples?|e2e)/|\.(test|spec)\.|\.(md|lock|map)$")
FILE_FILTER_IN = re.compile(r"\.(py|js|jsx|ts|tsx|mjs|cjs|php|rb|go|java|kt|dart|yml|yaml|json|ini|cfg|toml|conf|properties)$|(^|/)\.env[^/]*$|(^|/)Dockerfile")

DEBUG_ON = re.compile(r"app\.run\([^)]*debug\s*=\s*True|^\s*DEBUG\s*=\s*True|FLASK_DEBUG[=: \"]+1|APP_DEBUG\s*=\s*true|WP_DEBUG.{1,12}true")
TEST_ACCOUNT = re.compile(r"(^|[^A-Za-z])(password123|admin123|letmein|changeme)([^A-Za-z]|$)|(admin|demo|test)@example\.(com|org)")
CORS_OPEN = re.compile(r"""Access-Control-Allow-Origin['"]?\s*[:,]\s*['"]\*|origin:\s*(['"]\*['"]|true)|origins?\s*=\s*\[?\s*['"]\*"""
                       r"""|CORS_ALLOW_ALL_ORIGINS\s*=\s*True|[^A-Za-z]CORS\([A-Za-z_]+\)|[^A-Za-z]cors\(\)""")
COOKIE_FLAGS = re.compile(r"httpOnly:\s*false|secure:\s*false|SESSION_COOKIE_(SECURE|HTTPONLY)[^=]{0,4}=\s*False")
TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[a-z]+$|(^|/)test_[^/]*\.py$|_test\.(py|dart)$")
DOCKERFILE = re.compile(r"(^|/)Dockerfile[^/]*$")


def applies(ctx):
    return any(ctx.has_trait(t) for t in ("node", "python", "dart", "php", "static-site", "docker"))


def _check_pattern(ctx, files, lines, level, code, message, regex):
    """Adds up to 8 file:line hits for the pattern (never the matching text)."""
    hits = set()
    for f in files:
        for n, line in enumerate(read_text(os.path.join(ctx.root, f), 2000000).splitlines(), 1):
            if regex.search(line):
                hits.add("%s:%d" % (f, n))
    for h in sorted(hits)[:8]:
        lines.append("%s  %s: %s: %s" % (level, code, message, h))


def _runtime_eol(lines, runtime, version, where):
    eol = EOL.get((runtime, version))
    if eol and eol <= time.strftime("%Y-%m-%d"):
        lines.append("FAIL  RUNTIME-EOL: %s %s reached end of support on %s (no more security fixes): %s" % (runtime, version, eol, where))


def _dockerfile(ctx, f, lines):
    stages, user = set(), ""
    for n, raw in enumerate(read_text(os.path.join(ctx.root, f)).splitlines(), 1):
        parts = raw.split()
        if not parts:
            continue
        if parts[0].upper() == "FROM" or (re.match(r"^\s*FROM\s", raw)):
            i = 1
            while i < len(parts) and parts[i].startswith("--"):
                i += 1
            img = parts[i] if i < len(parts) else ""
            if i + 1 < len(parts) and parts[i + 1].lower() == "as" and i + 2 < len(parts):
                stages.add(parts[i + 2])
            if img and img != "scratch" and not re.search(r"[:@$]", img) and img not in stages:
                lines.append("WARN  DOCKER-UNPINNED: base image has no version tag: %s:%d" % (f, n))
        elif parts[0].upper() == "USER" and len(parts) > 1:
            user = parts[1]
    if user in ("", "root", "0"):
        lines.append("WARN  DOCKER-ROOT: container runs as root: %s" % f)


def run(ctx):
    ctx.dim = "security,quality"
    lines = []
    files = [f for f in ctx.source_files() if not FILE_FILTER_OUT.search(f) and FILE_FILTER_IN.search(f)]

    # Debug mode and test accounts left in
    _check_pattern(ctx, files, lines, "FAIL", "DEBUG-ON", "debug mode switched on, shows internals to visitors", DEBUG_ON)
    _check_pattern(ctx, files, lines, "WARN", "TEST-ACCOUNT", "test or default login left in the code", TEST_ACCOUNT)
    # Browser-facing settings
    _check_pattern(ctx, files, lines, "WARN", "CORS-OPEN", "answers requests from every website (fine only for a public read-only API)", CORS_OPEN)
    _check_pattern(ctx, files, lines, "WARN", "COOKIE-FLAGS", "session cookie without Secure or HttpOnly", COOKIE_FLAGS)

    # Containers: run as root, unpinned base image
    dockerfiles = [f for f in ctx.project_files() if DOCKERFILE.search(f) and ctx.isfile(f)]
    for f in dockerfiles:
        _dockerfile(ctx, f, lines)

    # Runtimes past end of support (only versions the project pins)
    for f in (".nvmrc", ".node-version"):
        if ctx.isfile(f):
            first = (ctx.read(f).splitlines() or [""])[0].replace("v", "").replace(" ", "").replace("\r", "")
            _runtime_eol(lines, "node", first.split(".")[0], f)
    if ctx.isfile("package.json"):
        m = re.search(r'"node"\s*:\s*"([^"]*)"', ctx.read("package.json"))
        if m and re.match(r"^(v|\^|~)?[0-9]", m.group(1)):
            _runtime_eol(lines, "node", re.sub(r"[v^~]", "", m.group(1)).split(".")[0], "package.json engines")
    for f in (".python-version", "runtime.txt"):
        if ctx.isfile(f):
            first = (ctx.read(f).splitlines() or [""])[0].replace("\r", "")
            first = re.sub(r"^python-", "", first)
            _runtime_eol(lines, "python", ".".join(first.split(".")[:2]), f)
    for f in dockerfiles:
        text = ctx.read(f)
        m = re.search(r"(?im)^\s*FROM\s+node:([0-9]+)", text)
        if m:
            _runtime_eol(lines, "node", m.group(1), f)
        m = re.search(r"(?im)^\s*FROM\s+python:(3\.[0-9]+)", text)
        if m:
            _runtime_eol(lines, "python", m.group(1), f)

    # Reproducible installs, tests, automated checks, leaked source maps
    code_project = ctx.has_trait("node") or ctx.has_trait("python") or ctx.has_trait("dart")
    if ctx.has_trait("node") and not any(ctx.has_trait(t) for t in ("pm-npm", "pm-pnpm", "pm-yarn", "pm-bun")):
        lines.append("WARN  NO-LOCKFILE: no package lockfile, so installs are not repeatable and the dependency audit cannot run")
    if code_project and not any(TEST_FILE.search(f) for f in ctx.project_files()):
        lines.append("WARN  NO-TESTS: no automated tests found")
    if code_project and not ctx.has_trait("ci-github") and not any(ctx.isfile(f) for f in (".gitlab-ci.yml", "bitbucket-pipelines.yml", "azure-pipelines.yml")) \
            and not os.path.isdir(os.path.join(ctx.root, ".circleci")):
        lines.append("WARN  NO-CI: no automated checks run on each change")
    maps = [f for f in ctx.project_files() if f.endswith(".map") and not re.search(r"(^|/)node_modules/", f)][:3]
    for f in maps:
        lines.append("WARN  SOURCEMAPS-COMMITTED: source map file in the repo (can reveal your original code if published): %s" % f)

    ctx.write("release-checks.txt", "".join(ln + "\n" for ln in lines))
    ctx.result("release-checks", "release-checks.txt")
