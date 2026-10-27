"""Secrets in git history, and in files not committed yet (gitleaks). Applies to every project.
Values are redacted, so no report ever contains a secret."""
import glob
import os
import shutil
import tempfile

NAME = "10-secrets"


def applies(ctx):
    return True


def tools(ctx):
    return ["gitleaks"]


def _detect_args(config, report, history):
    args = ["gitleaks", "detect", "--source", "."]
    if not history:
        args.insert(2, "--no-git")
    return args + ["--config", config, "--redact", "--report-format", "json", "--report-path", report, "--no-banner"]


def _stage_uncommitted(ctx):
    """Copies staged, unstaged and brand-new files (and ignored .env files) into a temp folder for gitleaks."""
    tmp = tempfile.mkdtemp(prefix="auditscan")
    names = set()
    has_head = ctx.git("rev-parse", "--verify", "-q", "HEAD")[0] == 0
    if has_head:
        names.update(ctx.git("diff", "--name-only", "-z", "--relative", "HEAD")[1].split("\0"))
    else:
        names.update(ctx.git("diff", "--name-only", "-z", "--relative", "--cached")[1].split("\0"))
    names.update(ctx.git("ls-files", "-z", "--others", "--exclude-standard")[1].split("\0"))
    # .env files are usually git-ignored, so the lists above miss them. They still matter:
    # an ignored .env can be synced, zipped or pasted somewhere. Scan them too.
    for pattern in (".env", ".env.*"):
        names.update(os.path.basename(p) for p in glob.glob(os.path.join(ctx.root, pattern)))
    count = 0
    for name in sorted(n for n in names if n):
        if name.startswith("audit/"):
            continue
        src = os.path.join(ctx.root, name)
        try:
            if not os.path.isfile(src) or os.path.getsize(src) >= 1000000:
                continue
            dest = os.path.join(tmp, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(src, dest)
            count += 1
        except OSError:
            continue
    return tmp, count


def run(ctx):
    ctx.dim = "security"
    if not ctx.has("gitleaks"):
        ctx.skip("gitleaks", "not installed (%s)" % ctx.install_hint("gitleaks"))
        ctx.skip("gitleaks-uncommitted", "gitleaks not installed")
        return
    ctx.note_version("gitleaks", ctx.run_text(["gitleaks", "version"]))
    # gitleaks' own rules plus one for NAME=value secrets (scripts/gitleaks-extra.toml)
    config = os.path.join(ctx.script_dir, "gitleaks-extra.toml")

    if not ctx.is_git():
        # No history to read: scan the folder as it is.
        ctx.run("gitleaks", "gitleaks.json", _detect_args(config, ctx.path("gitleaks.json"), history=False), json=True, stdout="gitleaks.stdout")
        ctx.record("gitleaks-uncommitted", "skipped: not a git repo (the folder scan above covers all files)", "-", "-")
        return

    # 1. Every commit in history
    ctx.run("gitleaks", "gitleaks.json", _detect_args(config, ctx.path("gitleaks.json"), history=True), json=True, stdout="gitleaks.stdout")

    # 2. Staged, unstaged and brand-new files (a history scan can't see them)
    tmp, count = _stage_uncommitted(ctx)
    try:
        if count:
            ctx.run("gitleaks-uncommitted", "gitleaks-uncommitted.json",
                    _detect_args(config, ctx.path("gitleaks-uncommitted.json"), history=False), json=True,
                    stdout="gitleaks-uncommitted.stdout", cwd=tmp)
        else:
            ctx.record("gitleaks-uncommitted", "clean", "-", "-")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
