#!/usr/bin/env python3
"""Tests for scripts/audit_serve.py: the local server that starts Claude on approved fixes.
Runs the real server on a random port with a stand-in for the claude program (tests/stub_claude.py), so
no real Claude run is started. Prints 'OK: label' or 'BAD: label | detail' per check."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVE = os.path.join(HERE, "..", "scripts", "audit_serve.py")
STUB = os.path.join(HERE, "stub_claude.py")
CALLED = os.path.join(HERE, "stub-called.txt")

FIXES = {"fixes": [
    {"id": "P-1", "finding": "F-aaaaaa", "title": "Rotate the key", "who": "you"},
    {"id": "P-2", "finding": "C-001", "title": "Pin the actions", "who": "claude", "file": "deploy.yml",
     "change": "uses: x@<hash>", "verify": "zizmor is quieter"},
    {"id": "P-3", "title": "Remove the token from the job env", "who": "claude"},
]}


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def make_run(root, untrusted=False, fixes=True):
    run = os.path.join(root, "project", "audit", "2026-01-01_000000")
    os.makedirs(run)
    with open(os.path.join(run, "manifest.tsv"), "w") as f:
        f.write("tool\tstatus\texit\toutput\tdimension\ngitleaks\tclean\t0\tg.json\tsecurity\n")
    with open(os.path.join(run, "meta.txt"), "w") as f:
        f.write("date=2026-01-01\ncommit=abc\nuntrusted=%s\n" % ("yes" if untrusted else "no"))
    if fixes:
        with open(os.path.join(run, "fixes.json"), "w") as f:
            json.dump(FIXES, f)
    return run


def start_server(run):
    env = dict(os.environ, AUDIT_CLAUDE_BIN=STUB, PYTHONUTF8="1")
    env.pop("AUDIT_PORT", None)
    proc = subprocess.Popen([sys.executable, SERVE, run], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    port = None
    for _ in range(100):
        line = proc.stdout.readline()
        m = re.search(r"127\.0\.0\.1:(\d+)", line)
        if m:
            port = int(m.group(1))
            break
    return proc, port


def call(port, path, method="GET", token=None, body=None, headers=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Audit-Token", token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def token_of(page):
    m = re.search(r'"token":\s*"([^"]+)"', page)
    return m.group(1) if m else None


def main():
    if os.path.exists(CALLED):
        os.remove(CALLED)
    tmp = tempfile.mkdtemp(prefix="serve")
    run = make_run(tmp)
    proc, port = start_server(run)
    try:
        if not port:
            say(False, "the server starts", "no port printed")
            return
        say(True, "the server starts on a local port")
        code, page = call(port, "/")
        token = token_of(page)
        say(code == 200 and token is not None, "the served page carries a token", "code %s" % code)
        on_disk = open(os.path.join(run, "report.html"), encoding="utf-8").read()
        say(token is not None and token not in on_disk, "the token is not written into report.html on disk")

        say(call(port, "/api/status")[0] == 403, "status without the token is refused")
        say(call(port, "/api/status", token="wrong")[0] == 403, "status with a wrong token is refused")
        say(call(port, "/api/start", "POST", token, {"ids": ["P-2"]}, {"Host": "evil.example"})[0] == 403, "a request with a foreign Host header is refused")
        say(call(port, "/api/start", "POST", token, {"ids": ["P-2"]}, {"Origin": "http://evil.example"})[0] == 403, "a request from another site (Origin) is refused")
        say(call(port, "/api/start", "OPTIONS")[0] == 403, "cross-site preflight requests are refused")
        say(call(port, "/anything-else", token=token)[0] == 404, "no other files are served")
        say(call(port, "/api/start", "POST", token, {"ids": ["P-1"]})[0] == 400, "a fix marked 'you do this' cannot be started")
        say(call(port, "/api/start", "POST", token, {"ids": ["P-99"]})[0] == 400, "an unknown fix id is refused")
        say(call(port, "/api/start", "POST", token, {"ids": []})[0] == 400, "starting with nothing selected is refused")
        say(not os.path.exists(CALLED), "nothing was started by the refused requests")

        long_note = "A" * 2000 + "\x00\x07 end"
        code, body = call(port, "/api/start", "POST", token, {"ids": ["P-2", "P-3"], "notes": {"P-2": long_note, "P-1": "ignored"}})
        say(code == 200, "approved fixes start Claude", "%s %s" % (code, body))
        for _ in range(60):
            if os.path.exists(CALLED) and "Approved fixes" in open(CALLED, encoding="utf-8").read():
                break
            time.sleep(0.1)
        text = open(CALLED, encoding="utf-8").read() if os.path.exists(CALLED) else ""
        say("--disallowedTools" in text and "Bash(git push:*)" in text, "git push is blocked in the Claude run")
        say("--permission-mode acceptEdits" in text and "--allowedTools" in text, "Claude gets a short list of allowed tools")
        listed = text.split("Approved fixes:")[1] if "Approved fixes:" in text else ""
        say("[1] P-2" in listed and "[2] P-3" in listed and "P-1" not in listed, "the prompt lists exactly the approved Claude fixes")
        say("audit-fix/2026-01-01_000000" in text and "Never push" in text, "the prompt makes Claude use a new branch and never push")
        note_line = [l for l in text.splitlines() if "User note" in l]
        say(bool(note_line) and len(note_line[0]) < 700 and "\x00" not in text, "the note is length-limited and cleaned")
        approved = json.load(open(os.path.join(run, "approved-fixes.json"), encoding="utf-8"))
        say(approved.get("approved") == ["P-2", "P-3"], "approved-fixes.json records the approved ids")
        code, body = call(port, "/api/start", "POST", token, {"ids": ["P-2"]})
        st = json.loads(call(port, "/api/status", token=token)[1])
        say(code == 409 or st["state"] != "running", "a second start while one runs is refused", "%s %s" % (code, st["state"]))
        for _ in range(60):
            st = json.loads(call(port, "/api/status", token=token)[1])
            if st["state"] != "running":
                break
            time.sleep(0.5)
        say(st["state"] == "done" and any("Applied P-3" in l for l in st["log"]), "progress is readable and the run finishes", st["state"])
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        if os.path.exists(CALLED):
            os.remove(CALLED)

    # a run made in untrusted mode must never be edited from here
    run2 = make_run(tempfile.mkdtemp(prefix="serve"), untrusted=True)
    proc2, port2 = start_server(run2)
    try:
        token2 = token_of(call(port2, "/")[1])
        code, body = call(port2, "/api/start", "POST", token2, {"ids": ["P-2"]})
        say(code == 409 and "untrusted" in body, "an untrusted-mode run cannot start Claude", "%s %s" % (code, body))
    finally:
        proc2.terminate()
        proc2.wait(timeout=10)

    run3 = make_run(tempfile.mkdtemp(prefix="serve"), fixes=False)
    proc3, port3 = start_server(run3)
    try:
        token3 = token_of(call(port3, "/")[1])
        code, body = call(port3, "/api/start", "POST", token3, {"ids": ["P-2"]})
        say(code == 409, "a run without fixes.json cannot start Claude", code)
    finally:
        proc3.terminate()
        proc3.wait(timeout=10)


if __name__ == "__main__":
    main()
