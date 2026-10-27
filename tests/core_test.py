#!/usr/bin/env python3
"""Tests for the tool runner in scripts/audit_core.py: how a tool's exit code and output become one status.
A crash must never look like "findings", and "findings" must never look like "clean". Uses small Python
commands as stand-in tools. Prints 'OK: label' or 'BAD: label | detail' per check."""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import audit_core  # noqa: E402


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def tool(code, text="", err=""):
    """A stand-in tool: prints `text`, writes `err` to stderr, exits with `code`."""
    script = "import sys; sys.stdout.write(%r); sys.stderr.write(%r); sys.exit(%d)" % (text, err, code)
    return [sys.executable, "-c", script]


def fresh_ctx():
    root = tempfile.mkdtemp(prefix="core")
    ctx = audit_core.Ctx(root, SCRIPTS)
    ctx.out = os.path.join(root, "audit", "run")
    os.makedirs(ctx.out)
    ctx.write("manifest.tsv", "tool\tstatus\texit\toutput\tdimension\n")
    return ctx


def last_row(ctx):
    return ctx.last_record()


def main():
    ctx = fresh_ctx()
    quiet = sys.stdout
    # (label, kwargs for run, argv, expected status prefix, expected exit code)
    cases = [
        ("exit 0 is clean", {}, tool(0, "all good"), "clean", "0"),
        ("exit 1 is findings", {}, tool(1, "something"), "findings", "1"),
        ("exit 2 is a failure, not findings", {}, tool(2, "boom", "traceback"), "failed-to-run", "2"),
        ("a listed code means findings", {"codes": (1, 2)}, tool(2, "x"), "findings", "2"),
        ("an unlisted code is a failure", {"codes": (10, 11)}, tool(1, "x"), "failed-to-run", "1"),
        ("an extra ok code means clean", {"ok": (128,)}, tool(128, "no packages"), "clean", "128"),
        ("json output that is not json is a failure", {"json": True}, tool(0, "Segmentation fault"), "failed-to-run", "0"),
        ("json output that is json is clean at exit 0", {"json": True}, tool(0, '{"results": []}'), "clean", "0"),
        ("json output at a findings code is findings", {"json": True}, tool(1, "[1]"), "findings", "1"),
        ("json findings with garbage output is a failure", {"json": True}, tool(1, "oops"), "failed-to-run", "1"),
        ("a leading BOM or spaces before json still counts", {"json": True}, tool(0, '  \n{"a": 1}'), "clean", "0"),
        ("findings exit needs the expected text when match is set", {"match": "error TS"}, tool(1, "nothing useful"), "failed-to-run", "1"),
        ("findings exit with the expected text is findings", {"match": "error TS"}, tool(1, "a.ts(1,1): error TS2322"), "findings", "1"),
        ("empty-results text means clean", {"json": True, "empty": r'"results": *\[ *\]'}, tool(0, '{"results": []}'), "clean", "0"),
        ("results present means findings, even at exit 0", {"json": True, "empty": r'"results": *\[ *\]'}, tool(0, '{"results": [{"a": 1}]}'), "findings", "0"),
        ("a measurement is done at exit 0", {"done": True}, tool(0, "42 lines"), "done", "0"),
        ("a measurement that exits 1 is a failure", {"done": True}, tool(1, "42 lines"), "failed-to-run", "1"),
        ("a tool that cannot start is a failure", {}, ["no-such-tool-xyz-123"], "failed-to-run", "127"),
    ]
    for label, kwargs, argv, want_status, want_code in cases:
        sys.stdout = open(os.devnull, "w")
        try:
            ctx.run("t", "t.out", argv, **kwargs)
        finally:
            sys.stdout.close()
            sys.stdout = quiet
        row = last_row(ctx)
        ok = len(row) == 5 and row[1].startswith(want_status) and row[2] == want_code
        say(ok, label, row)

    row = last_row(ctx)
    say(row[3] == "t.out" and row[4] == "general", "a row has the tool, status, exit code, output file and dimension", row)

    # stderr goes to <file>.err, console text can go to another file
    sys.stdout = open(os.devnull, "w")
    ctx.run("e", "e.json", tool(0, "{}", "warning text"), json=True, stdout="e.console")
    sys.stdout.close()
    sys.stdout = quiet
    say("warning text" in audit_core.read_text(ctx.path("e.json.err")), "stderr is saved next to the output as <file>.err")
    say(audit_core.read_text(ctx.path("e.console")) == "{}", "console output can be sent to a different file")

    # a tool turned off in .audit.conf is recorded as skipped, not silently dropped
    ctx.conf_skip = {"off"}
    sys.stdout = open(os.devnull, "w")
    status = ctx.run("off", "off.out", tool(0, "x"))
    sys.stdout.close()
    sys.stdout = quiet
    say(status == "skipped" and "turned off in .audit.conf" in "\t".join(last_row(ctx)), "a tool turned off in .audit.conf is recorded as skipped", last_row(ctx))

    # a hung tool is stopped and recorded as a timeout
    old = audit_core.TIMEOUT_SECONDS
    audit_core.TIMEOUT_SECONDS = 1
    start = time.time()
    sys.stdout = open(os.devnull, "w")
    ctx.run("slow", "slow.out", [sys.executable, "-c", "import time; time.sleep(30)"])
    sys.stdout.close()
    sys.stdout = quiet
    audit_core.TIMEOUT_SECONDS = old
    row = last_row(ctx)
    say(row[1] == "timeout" and row[2] == "124" and time.time() - start < 15, "a hung tool is stopped and recorded as a timeout", (row, time.time() - start))

    # manifest helpers used when a tool is run again
    ctx.record("again", "failed-to-run", 1, "a.out")
    ctx.drop_last_record()
    say(last_row(ctx)[0] == "slow", "the last manifest row can be dropped")
    ctx.record("again", "clean", 0, "a.out")
    ctx.amend_last_status("partial: left out; ")
    say(last_row(ctx)[1] == "partial: left out; clean", "the last manifest row's status can be amended", last_row(ctx))

    # json_looking
    d = tempfile.mkdtemp(prefix="jl")
    cases = [("{}", True), ("[1]", True), ("  \r\n[", True), ("", False), ("error", False), ("<html>", False)]
    for text, want in cases:
        p = os.path.join(d, "f")
        with open(p, "w") as f:
            f.write(text)
        say(audit_core.json_looking(p) == want, "json_looking(%r) is %s" % (text, want))

    # the install hints exist for every tool a module can ask for
    for name in ("semgrep", "gitleaks", "osv-scanner", "ruff", "zizmor", "pip-audit", "lizard", "mobsfscan", "npx", "flutter", "dart", "curl"):
        say(bool(ctx.install_hint(name)), "there is an install hint for %s" % name)

    # untrusted mode removes secret-looking variables and keeps the audit's own settings
    os.environ["MY_API_TOKEN"] = "x"
    os.environ["AUDIT_KEEP_ME"] = "y"
    os.environ["PLAIN_SETTING"] = "z"
    ctx.set_untrusted(True)
    say("MY_API_TOKEN" not in os.environ and os.environ.get("AUDIT_KEEP_ME") == "y" and os.environ.get("PLAIN_SETTING") == "z",
        "untrusted mode removes secret-looking variables and nothing else")
    say(ctx.npx_env.get("npm_config_ignore_scripts") == "true", "untrusted mode switches off install scripts for npx tools")
    os.environ.pop("AUDIT_UNTRUSTED", None)


def pip_user_scripts_lookup():
    """pip install --user puts tools in a Scripts folder that is often not on PATH. On Windows that folder is under
    the Python's own user base, which for the Microsoft Store Python is inside LOCALAPPDATA\\Packages (not APPDATA)."""
    import site
    saved = (dict(os.environ), audit_core.is_windows, site.getuserbase)
    try:
        home = tempfile.mkdtemp(prefix="winhome")
        store = os.path.join(home, "Local", "Packages", "PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0",
                             "LocalCache", "local-packages", "Python313", "Scripts")
        custom_base = os.path.join(home, "custom-base")
        custom = os.path.join(custom_base, "Scripts")
        for d in (store, custom):
            os.makedirs(d)
        os.environ["LOCALAPPDATA"] = os.path.join(home, "Local")
        os.environ["APPDATA"] = os.path.join(home, "Roaming")
        os.environ["PATH"] = os.path.join(home, "nothing")
        audit_core.is_windows = lambda: True
        site.getuserbase = lambda: custom_base
        audit_core.extend_path()
        parts = os.environ["PATH"].split(os.pathsep)
        say(store in parts, "the Microsoft Store Python's pip --user Scripts folder is added to PATH", parts)
        say(custom in parts, "the running Python's own user Scripts folder is added to PATH", parts)
    finally:
        os.environ.clear()
        os.environ.update(saved[0])
        audit_core.is_windows, site.getuserbase = saved[1], saved[2]


if __name__ == "__main__":
    main()
    pip_user_scripts_lookup()
