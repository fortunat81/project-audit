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

    root = project()
    fake_audit(root, git(root, "rev-parse", "--short", "HEAD"))
    out = run_status(root)
    say("LAST_AUDIT_REPORT=none" in out, "an earlier run with no scores.json is said to have nothing to compare with", out)

    # the helper commands find the run folder from the project root, from inside the run folder, or from a subfolder
    import audit_scan
    root = project()
    folder = fake_audit(root, "abc")
    with open(os.path.join(root, "audit", "latest.txt"), "w", newline="\n") as f:
        f.write(folder.replace("\\", "/") + "\n")

    def same(a, b):
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    sub = os.path.join(root, "src")
    os.makedirs(sub)
    say(same(audit_scan.find_run_dir([], root), folder), "no argument: the latest run from the project root")
    say(same(audit_scan.find_run_dir([], folder), folder), "no argument, inside the run folder: that folder")
    say(same(audit_scan.find_run_dir([], sub), folder), "no argument, inside a subfolder: the latest run of the project")
    say(same(audit_scan.find_run_dir([folder], sub), folder), "an explicit folder wins")
    say(audit_scan.find_run_dir([], tempfile.mkdtemp()) == "", "nothing found: empty")

    # the report opens in its own app-style window (no tabs, no address bar) when Chrome or Edge is there
    page = os.path.join(root, "report.html")
    cmd = audit_scan.app_window_command(page, lambda names: "/bin/" + names[0])
    say(bool(cmd) and cmd[0].endswith(audit_scan.BROWSER_NAMES[0]) and any(a.startswith("--app=file:") for a in cmd),
        "with a Chromium browser the page opens as an app window", cmd)
    say(audit_scan.app_window_command(page, lambda names: None) == [], "no Chromium browser: no app command, the default opener is used")
    cmd = audit_scan.app_window_command(page, lambda names: "/bin/" + names[-1])
    say(bool(cmd) and cmd[0].endswith(audit_scan.BROWSER_NAMES[-1]), "the first browser found in the list is used")

    isolated_tools_checks()

    # one window per run: the progress page opened at the start already turns into the report, so --open must not
    # open a second window after it; a later --open (the window was closed) opens again
    opened = []
    run = os.path.join(root, "run")
    os.makedirs(run)
    audit_scan.open_report(run, opened.append)
    say(len(opened) == 1, "--open with no progress window opens the report", opened)
    del opened[:]
    audit_scan.open_progress(run, opened.append)
    say(len(opened) == 1 and opened[0].endswith("progress.html"), "the scan opens the progress page", opened)
    del opened[:]
    audit_scan.open_report(run, opened.append)
    say(opened == [], "--open right after the progress page opened does not open a second window", opened)
    audit_scan.open_report(run, opened.append)
    say(len(opened) == 1 and opened[0].endswith("report.html"), "the next --open opens the report again", opened)


def isolated_tools_checks():
    """mobsfscan brings its own semgrep, which can clash with the one the audit uses. The skill keeps it in its own
    virtual environment (under AUDIT_TOOLS_DIR, default ~/.project-audit/tools) and uses it only for that tool."""
    home = tempfile.mkdtemp(prefix="tools")
    saved = {k: os.environ.get(k) for k in ("AUDIT_TOOLS_DIR", "PATH")}
    os.environ["AUDIT_TOOLS_DIR"] = home
    try:
        say(audit_core.isolated_exe("mobsfscan") is None, "no isolated mobsfscan before it is installed")
        say(all(t in audit_core.ISOLATED_TOOLS for t in ("semgrep", "ruff", "zizmor", "pip-audit", "lizard", "mobsfscan"))
            and not any(t in audit_core.ISOLATED_TOOLS for t in ("gitleaks", "osv-scanner", "git", "npx")),
            "every Python tool is kept in its own environment; programs that are not Python packages are not")

        calls = []

        def fake(argv):
            calls.append(list(argv))
            if "venv" in argv:   # what python -m venv leaves behind
                bindir = audit_core.isolated_bin("mobsfscan")
                os.makedirs(bindir)
                open(os.path.join(bindir, "python.exe" if audit_core.is_windows() else "python"), "w").close()
            return 0
        code = audit_modes.install_isolated("mobsfscan", fake)
        venv_dir = os.path.join(home, "mobsfscan")
        say(code == 0 and len(calls) == 2 and calls[0][1:3] == ["-m", "venv"] and calls[0][3] == venv_dir,
            "installing creates a virtual environment in its own folder", calls)
        say(len(calls) == 2 and calls[1][0].startswith(audit_core.isolated_bin("mobsfscan")) and calls[1][1:4] == ["-m", "pip", "install"]
            and calls[1][-1] == "mobsfscan", "then installs the tool with that environment's own pip", calls)
        say(not any("--user" in c or "pipx" in c for call in calls for c in call), "nothing goes into the shared user packages")

        failing = audit_modes.install_isolated("mobsfscan", lambda argv: 1)
        say(failing != 0, "a failed install is reported as a failure")

        exe = os.path.join(audit_core.isolated_bin("mobsfscan"), "mobsfscan.exe" if audit_core.is_windows() else "mobsfscan")
        open(exe, "w").close()
        say(audit_core.isolated_exe("mobsfscan") == exe, "once installed the isolated copy is found", audit_core.isolated_exe("mobsfscan"))
        os.environ["PATH"] = os.pathsep.join([home, os.environ.get("PATH", "")])
        env = audit_core.isolated_env("mobsfscan")
        say(env["PATH"].split(os.pathsep)[0] == audit_core.isolated_bin("mobsfscan"),
            "that tool runs with its own folder first, so it uses its own semgrep", env["PATH"][:120])
        say(audit_core.isolated_env("gitleaks") == {}, "other tools run with the normal PATH")
        say(audit_core.isolated_bin("mobsfscan") not in os.environ["PATH"].split(os.pathsep),
            "the environment's folder is not added to the audit's own PATH")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    main()
