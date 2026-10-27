#!/usr/bin/env python3
"""Tests for the --status mode (scripts/audit_modes.py): when does the tool recommend a full audit and when a quick one.
The decision itself is a plain function (_reasons); the rest is checked on a small git project with a fake
earlier audit folder. Prints 'OK: label' or 'BAD: label | detail' per check."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import audit_core   # noqa: E402
import audit_modes  # noqa: E402

LIMITS = (30, 50, 3000)


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def git(root, *args):
    return subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True).stdout.strip()


def project():
    root = tempfile.mkdtemp(prefix="modes")
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"]):
        git(root, *cmd)
    with open(os.path.join(root, "a.txt"), "w", newline="\n") as f:
        f.write("one\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "first")
    return root


def fake_audit(root, commit, days_ago=1, traits="git", manifest_rows=()):
    folder = os.path.join(root, "audit", "2026-01-01_000000")
    os.makedirs(folder)
    meta = "date=2026-01-01\nepoch=%d\ncommit=%s\ntraits=%s\n" % (time.time() - days_ago * 86400, commit, traits)
    with open(os.path.join(folder, "meta.txt"), "w", newline="\n") as f:
        f.write(meta)
    with open(os.path.join(folder, "manifest.tsv"), "w", newline="\n") as f:
        f.write("tool\tstatus\texit\toutput\tdimension\n" + "".join(r + "\n" for r in manifest_rows))
    return folder


def run_status(root):
    ctx = audit_core.Ctx(root, SCRIPTS)
    ctx.traits = ["git"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        audit_modes.status(ctx)
    return out.getvalue()


def main():
    reasons = audit_modes._reasons
    say(reasons(1, "3", 10, "no", 0, False, LIMITS) == [], "a small, recent change needs no full audit")
    say(len(reasons(30, "3", 10, "no", 0, False, LIMITS)) == 1, "30 days since the last audit is a reason")
    say(len(reasons(29, "3", 10, "no", 0, False, LIMITS)) == 0, "29 days is not")
    say(len(reasons(1, "50", 10, "no", 0, False, LIMITS)) == 1, "50 commits is a reason")
    say(len(reasons(1, "49", 10, "no", 0, False, LIMITS)) == 0, "49 commits is not")
    say(len(reasons(1, "3", 3000, "no", 0, False, LIMITS)) == 1, "3000 changed lines is a reason")
    say(len(reasons(1, "unknown", "unknown", "no", 0, False, LIMITS)) == 0, "unknown commits and lines are not a reason by themselves")
    say(len(reasons(1, "3", 10, "yes", 0, False, LIMITS)) == 1, "changed dependency files are a reason")
    say(len(reasons(1, "3", 10, "no", 2, False, LIMITS)) == 1, "checks that failed last time are a reason")
    say(len(reasons(1, "3", 10, "no", 0, True, LIMITS)) == 1, "a changed project makeup is a reason")
    say(len(reasons(99, "99", 9999, "yes", 1, True, LIMITS)) == 6, "every reason is listed when all apply")

    root = project()
    out = run_status(root)
    say("LAST_AUDIT=none" in out and "RECOMMEND=full" in out, "no earlier audit means a full one", out)

    head = git(root, "rev-parse", "--short", "HEAD")
    fake_audit(root, head)
    out = run_status(root)
    say("RECOMMEND=quick" in out and "COMMITS_SINCE=0" in out and "DEPENDENCY_FILES_CHANGED=no" in out,
        "an unchanged project right after an audit means a quick one", out)

    with open(os.path.join(root, "new.txt"), "w", newline="\n") as f:
        f.write("a\nb\nc\n")
    out = run_status(root)
    say("LINES_CHANGED_SINCE=3 " in out, "new files count by their lines", out)

    with open(os.path.join(root, "package.json"), "w", newline="\n") as f:
        f.write("{}\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "deps")
    out = run_status(root)
    say("DEPENDENCY_FILES_CHANGED=yes" in out and "COMMITS_SINCE=1" in out and "RECOMMEND=full" in out,
        "a committed dependency file change is noticed", out)

    root = project()
    fake_audit(root, git(root, "rev-parse", "--short", "HEAD"), manifest_rows=["semgrep\tfailed-to-run\t2\ts.json\tsecurity", "gitleaks\tclean\t0\tg.json\tsecurity", "slow\ttimeout\t124\tx\tgeneral"])
    out = run_status(root)
    say("LAST_AUDIT_FAILED_CHECKS=2" in out and "RECOMMEND=full" in out, "failed and timed-out checks from the last audit are counted", out)

    root = project()
    fake_audit(root, "none", days_ago=2)
    out = run_status(root)
    say("COMMITS_SINCE=unknown" in out and "no git history" in out and "RECOMMEND=quick" in out,
        "without a usable commit the days since the audit are all it can say", out)

    root = project()
    fake_audit(root, git(root, "rev-parse", "--short", "HEAD"), traits="git node")
    out = run_status(root)
    say("PROFILE_CHANGED=yes" in out and "RECOMMEND=full" in out, "a different set of traits since the last audit is noticed", out)


if __name__ == "__main__":
    main()
