#!/usr/bin/env python3
"""The small commands around a scan: --detect, --projects, --check, --install, --install-deps, --status,
--version, --add-gitignore. Each prints plain KEY=value or table lines and returns an exit code.
Standard library only (Python 3.8+)."""
import os
import re
import subprocess
import sys
import time

from audit_checks import load_modules
from audit_core import read_text


def _tools_needed(ctx):
    """Every tool the applicable modules need, in order, without repeats."""
    seen, out = set(), []
    for name, mod, err in load_modules():
        if mod is not None and mod.applies(ctx) and hasattr(mod, "tools"):
            for tool in mod.tools(ctx):
                if tool not in seen:
                    seen.add(tool)
                    out.append(tool)
    return out


def detect(ctx):
    print("TRAITS=%s" % " ".join(ctx.traits))
    print("LANGUAGES=%s" % ctx.langs)
    print("UNHANDLED=%s" % (ctx.unhandled or "none"))
    print("LIVE_URL=%s" % (ctx.audit_url or "none"))
    for name, mod, err in load_modules():
        print("MODULE=%s %s" % (name, "applies" if mod is not None and mod.applies(ctx) else "not-applicable"))
    return 0


def projects(ctx):
    subs = ctx.subprojects.split()
    if ctx.root_is_project:
        print("PROJECT=.")
    for d in subs:
        print("PROJECT=%s" % d)
    if not ctx.root_is_project and not subs:
        print("PROJECT=. (no project files found; only the general checks apply)")
    return 0


def check(ctx):
    """One line per tool the applicable modules need: OK | MISSING <tool> <command> | USER-SKIPPED."""
    print("PROFILE=%s" % " ".join(ctx.traits))
    user_skipped = ctx.skip_file_tools() | ctx.conf_skip
    for tool in _tools_needed(ctx):
        if tool in user_skipped:
            print("USER-SKIPPED\t%s" % tool)
        elif ctx.has(tool):
            print("OK\t%s" % tool)
        else:
            print("MISSING\t%s\t%s" % (tool, ctx.install_hint(tool)))
    return 0


ALL_TOOLS = "gitleaks semgrep osv-scanner pip-audit ruff lizard zizmor mobsfscan".split()


def install(ctx, args):
    """Installs the missing tools with exactly the commands --check prints. Never uses sudo, and never installs a
    language SDK (Node.js, Flutter, Dart): for those it prints the download link."""
    if args and args[0] == "all":
        wanted = ALL_TOOLS
    elif args:
        wanted = args
    else:
        wanted = _tools_needed(ctx)
    user_skipped = ctx.skip_file_tools() | ctx.conf_skip
    ok = new = fail = manual = 0
    need_restart = False
    for tool in dict.fromkeys(wanted):
        if ctx.has(tool):
            print("OK         %s (already installed)" % tool)
            ok += 1
            continue
        if tool in user_skipped:
            print("SKIPPED    %s (you chose not to use it)" % tool)
            continue
        cmd = ctx.install_hint(tool)
        if cmd.startswith(("install", "download")):
            print("MANUAL     %s: %s" % (tool, cmd))
            manual += 1
            continue
        print("INSTALLING %s: %s" % (tool, cmd))
        sys.stdout.flush()
        code = subprocess.call(ctx.command(cmd.split(), dict(os.environ)))
        if code == 0:
            new += 1
            if not ctx.has(tool):
                need_restart = True
        else:
            print("FAILED     %s (the error is above; the audit will skip this tool)" % tool)
            fail += 1
    print()
    print("INSTALL SUMMARY: %d installed, %d already there, %d need a manual install, %d failed" % (new, ok, manual, fail))
    if need_restart:
        print("Some new tools aren't visible in this terminal yet: close it and open a new one.")
        if ctx.has("pipx"):
            print("If they still aren't found after that, run: pipx ensurepath")
    return 0 if fail == 0 else 1


def install_deps(ctx):
    """Installs the project's own packages with install scripts switched off, so a package can't run code during
    the install. Only creates node_modules/; lockfiles are not rewritten. Ask the user first: it downloads packages."""
    if ctx.untrusted:
        print("REFUSED: untrusted mode never installs a project's packages (they can run code)")
        return 1
    if not ctx.isfile("package.json"):
        print("NOTHING: no package.json in this folder")
        return 0
    if ctx.exists("node_modules"):
        print("ALREADY: node_modules exists")
        return 0
    if ctx.isfile("pnpm-lock.yaml"):
        if not ctx.has("pnpm"):
            print("MANUAL: this project uses pnpm, which isn't installed (https://pnpm.io/installation)")
            return 1
        print("RUNNING: pnpm install --frozen-lockfile --ignore-scripts")
        return _call(ctx, ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"])
    if ctx.isfile("yarn.lock") or ctx.isfile("bun.lockb") or ctx.isfile("bun.lock"):
        print("MANUAL: this project uses yarn or bun; install its packages yourself (without running install scripts if you can)")
        return 1
    if not ctx.has("npm"):
        print("MANUAL: npm not found (%s)" % ctx.install_hint("npx"))
        return 1
    if ctx.isfile("package-lock.json") or ctx.isfile("npm-shrinkwrap.json"):
        print("RUNNING: npm ci --ignore-scripts")
        return _call(ctx, ["npm", "ci", "--ignore-scripts"])
    print("RUNNING: npm install --ignore-scripts --no-package-lock")
    return _call(ctx, ["npm", "install", "--ignore-scripts", "--no-package-lock"])


def _call(ctx, argv):
    sys.stdout.flush()
    return subprocess.call(ctx.command(argv, dict(os.environ)), cwd=ctx.root)


def _audit_runs(ctx):
    base = os.path.join(ctx.root, "audit")
    try:
        names = sorted(n for n in os.listdir(base) if re.match(r"^20.*_", n) and os.path.isdir(os.path.join(base, n)))
    except OSError:
        return []
    return [os.path.join(base, n) for n in names]


def status(ctx):
    """Compares the project now with the last saved audit and recommends quick or full.
    Thresholds: AUDIT_DAYS (30), AUDIT_COMMITS (50), AUDIT_LINES (3000)."""
    days_limit = int(os.environ.get("AUDIT_DAYS", "30"))
    commits_limit = int(os.environ.get("AUDIT_COMMITS", "50"))
    lines_limit = int(os.environ.get("AUDIT_LINES", "3000"))
    runs = _audit_runs(ctx)
    last = runs[-1] if runs else ""
    prev = runs[-2] if len(runs) > 1 else ""
    if not last or not os.path.isfile(os.path.join(last, "meta.txt")):
        print("LAST_AUDIT=none")
        print("RECOMMEND=full")
        print("REASON=no previous audit, so this run sets the baseline")
        return 0
    meta = {}
    for line in read_text(os.path.join(last, "meta.txt")).splitlines():
        k, _, v = line.partition("=")
        meta.setdefault(k, v)
    last_epoch = int(meta.get("epoch") or time.time())
    last_commit = meta.get("commit", "")
    days = int((time.time() - last_epoch) // 86400)
    commits, lines, deps_changed = "unknown", "unknown", "no"
    if last_commit and last_commit != "none" and ctx.git("cat-file", "-e", last_commit + "^{commit}")[0] == 0:
        code, text = ctx.git("rev-list", "--count", last_commit + "..HEAD")
        commits = text.strip() if code == 0 else "unknown"
        total = 0
        for row in ctx.git("diff", "--numstat", last_commit, "--", ".", ":!audit")[1].splitlines():
            parts = row.split("\t")
            if len(parts) == 3 and not ctx.noise(parts[2]):
                total += sum(int(p) for p in parts[:2] if p.isdigit())
        for f in ctx.git("ls-files", "--others", "--exclude-standard")[1].splitlines():
            if f and not f.startswith("audit/") and not ctx.noise(f):
                try:
                    with open(os.path.join(ctx.root, f), "rb") as fh:
                        total += fh.read().count(b"\n")
                except OSError:
                    pass
        lines = total
        dep_files = "package.json package-lock.json pnpm-lock.yaml yarn.lock requirements.txt pyproject.toml poetry.lock pubspec.yaml pubspec.lock composer.json composer.lock".split()
        if ctx.git("diff", "--name-only", last_commit, "--", *dep_files)[1].strip():
            deps_changed = "yes"
    holes = sum(1 for ln in read_text(os.path.join(last, "manifest.tsv")).splitlines()[1:]
                if len(ln.split("\t")) > 1 and (ln.split("\t")[1].startswith("failed-to-run") or ln.split("\t")[1] == "timeout"))
    now_traits = " ".join(t for t in ctx.traits if t != "live-url")
    print("LAST_AUDIT=%s" % meta.get("date", ""))
    print("LAST_FOLDER=%s" % last.replace("\\", "/"))
    print("PREV_FOLDER=%s" % prev.replace("\\", "/"))
    print("DAYS_SINCE=%d" % days)
    print("COMMITS_SINCE=%s" % commits)
    print("LINES_CHANGED_SINCE=%s   (committed, staged, unstaged and new files)" % lines)
    print("DEPENDENCY_FILES_CHANGED=%s" % deps_changed)
    print("LAST_AUDIT_FAILED_CHECKS=%d" % holes)
    reasons = []
    last_traits = meta.get("traits", "")
    if last_traits and last_traits != now_traits:
        print("PROFILE_CHANGED=yes (was: %s)" % last_traits)
        reasons.append("the project's makeup changed since the last audit (new framework, backend or feature)")
    if deps_changed == "yes":
        reasons.append("dependency files changed since the last audit")
    if holes > 0:
        reasons.append("the last audit had %d check(s) that failed or timed out, so it left gaps" % holes)
    if days >= days_limit:
        reasons.append("%d days since the last audit (limit %d)" % (days, days_limit))
    if commits != "unknown" and int(commits) >= commits_limit:
        reasons.append("%s commits since the last audit (limit %d)" % (commits, commits_limit))
    if lines != "unknown" and int(lines) >= lines_limit:
        reasons.append("%s lines changed since the last audit (limit %d)" % (lines, lines_limit))
    if reasons:
        print("RECOMMEND=full")
        for r in reasons:
            print("REASON=%s" % r)
    else:
        print("RECOMMEND=quick")
        print("REASON=only %d days since the last audit (no git history to measure changes)" % days if commits == "unknown" else "REASON=small change since the last audit")
    return 0


def version(ctx):
    """Branch, behind/ahead of GitHub, uncommitted files (runs git fetch only)."""
    if not ctx.is_git():
        print("IS_GIT=no")
        return 0
    print("IS_GIT=yes")
    print("BRANCH=%s" % ctx.git("rev-parse", "--abbrev-ref", "HEAD")[1].strip())
    code, short = ctx.git("rev-parse", "--short", "HEAD")
    print("COMMIT=%s" % (short.strip() if code == 0 else "none"))
    code, upstream = ctx.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream = upstream.strip() if code == 0 else ""
    print("UPSTREAM=%s" % (upstream or "none"))
    modified = len([ln for ln in ctx.git("status", "--porcelain", "--untracked-files=no")[1].splitlines() if ln])
    untracked = len([ln for ln in ctx.git("ls-files", "--others", "--exclude-standard")[1].splitlines() if ln and not ln.startswith("audit/")])
    print("UNCOMMITTED_FILES=%d" % modified)
    print("UNTRACKED_FILES=%d" % untracked)
    if not upstream:
        print("FETCH=no-upstream")
        print("AHEAD=unknown")
        print("BEHIND=unknown")
        print("CAN_FAST_FORWARD=no")
        return 0
    if os.environ.get("AUDIT_NO_FETCH") == "1":
        print("FETCH=skipped")
    else:
        try:
            fetched = subprocess.run(["git", "fetch", "--quiet"], cwd=ctx.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            fetched = False
        print("FETCH=%s" % ("ok" if fetched else "failed"))
    code, counts = ctx.git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    ahead, behind = (counts.split() + ["0", "0"])[:2] if code == 0 else ("0", "0")
    print("AHEAD=%s" % ahead)
    print("BEHIND=%s" % behind)
    print("CAN_FAST_FORWARD=%s" % ("yes" if int(behind) > 0 and int(ahead) == 0 and modified == 0 else "no"))
    return 0


def add_gitignore(ctx):
    path = os.path.join(ctx.root, ".gitignore")
    text = read_text(path) if os.path.isfile(path) else None
    if text is not None and "audit/" in text.splitlines():
        print("ALREADY: audit/ is in .gitignore")
        return 0
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if text and not text.endswith("\n"):
            f.write("\n")
        f.write("audit/\n")
    print("ADDED: audit/ to %s" % path.replace("\\", "/"))
    return 0
