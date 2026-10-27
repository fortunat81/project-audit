#!/usr/bin/env python3
"""Checks a finished audit report for mistakes a person (or Claude) can make while writing it.

    python audit_verify.py [audit-folder]        default: the latest run in ./audit/

Looks at AUDIT.md, scores.json and manifest.tsv in that folder. Prints PASS / WARN / FAIL lines and
exits 1 if anything FAILED. Changes nothing. It never prints the text it matched (a secret would end
up in the output), only where it was found.
    1. scores.json is valid and has every field, with sensible values
    2. the verdict equals the one computed from the rules (audit_verdict.py)
    3. AUDIT.md names the same verdict, and its checklist marks add up to the counts in scores.json
    4. every tool named with a status in AUDIT.md exists in manifest.tsv with that status
    5. no secret-looking text in AUDIT.md or scores.json
Standard library only (Python 3.8+).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_verdict  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DIMENSIONS = ["architecture", "modularity", "spaghettiness", "security", "quality", "scalability", "documentation"]
VERDICTS = ("dont-launch", "launch-with-limits", "no-blocking-problems")
SECRET_SHAPES = re.compile(
    r"sk_live_[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z2-7]{16}|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
TOOL_STATUS = re.compile(r"([a-z][a-z0-9-]+) \((clean|findings|done|partial|skipped|failed-to-run|timeout|unavailable)[^)]*\)")


class Report:
    def __init__(self):
        self.fails = 0

    def ok(self, msg):
        print("PASS: " + msg)

    def warn(self, msg):
        print("WARN: " + msg)

    def fail(self, msg):
        print("FAIL: " + msg)
        self.fails += 1


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def check_fields(r, scores):
    mode, level, verdict = scores.get("mode"), scores.get("level"), scores.get("verdict")
    if mode in ("quick", "full"):
        r.ok("mode is %s" % mode)
    else:
        r.fail("mode must be quick or full (found: %s)" % (mode if mode is not None else "none"))
    if level in (1, 2, 3):
        r.ok("level is %s" % level)
    else:
        r.fail("level must be 1, 2 or 3 (found: %s)" % (level if level is not None else "none"))
    if verdict in VERDICTS:
        r.ok("verdict is %s" % verdict)
    else:
        r.fail("verdict must be dont-launch, launch-with-limits or no-blocking-problems (found: %s)" % (verdict if verdict is not None else "none"))
    if scores.get("rubric") is None:
        r.fail("rubric is missing")
    else:
        r.ok("rubric is %s" % scores["rubric"])
    values = scores.get("scores") or {}
    bad = [k for k in DIMENSIONS if not (k in values and (values[k] is None or (isinstance(values[k], int) and 0 <= values[k] <= 100)))]
    if bad:
        r.fail("scores missing or out of range: " + ",".join(bad))
    else:
        r.ok("all seven scores are 0-100 or null")
    keys = ("pass", "fail", "partial", "not_verified", "not_applicable")
    checklist = scores.get("checklist") or {}
    if all(isinstance(checklist.get(k), int) for k in keys):
        r.ok("checklist counts present (%s)" % " ".join(str(checklist[k]) for k in keys))
        counts = [checklist[k] for k in keys]
    else:
        r.fail("checklist counts are missing in scores.json")
        counts = [0] * 5
    confirmed = scores.get("confirmed")
    if isinstance(confirmed, dict) and all(isinstance(confirmed.get(k), int) for k in ("critical", "high")):
        r.ok("confirmed finding counts present (critical %d, high %d)" % (confirmed["critical"], confirmed["high"]))
    else:
        r.fail('scores.json needs "confirmed": {"critical": n, "high": n} (the verdict depends on it)')
    return mode, level, verdict, counts


def check_report(r, scores, report_text, manifest_text, counts, verdict, mode, level):
    phrase = audit_verdict.VERDICT_TEXT.get(verdict)
    if phrase:
        if phrase in report_text:
            r.ok("AUDIT.md states the verdict (%s)" % phrase)
        else:
            r.fail("AUDIT.md does not contain the verdict text '%s'" % phrase)

    marks = audit_verdict.read_marks(report_text)
    if marks:
        tally = {"pass": 0, "fail": 0, "partial": 0, "unverified": 0, "na": 0}
        for m in marks.values():
            tally[m] += 1
        in_report = [tally["pass"], tally["fail"], tally["partial"], tally["unverified"], tally["na"]]
        if in_report == counts:
            r.ok("checklist marks in AUDIT.md match scores.json")
        else:
            r.fail("checklist marks in AUDIT.md (%d pass, %d fail, %d partial, %d unverified, %d n/a) differ from scores.json (%s)"
                   % (tuple(in_report) + (", ".join(map(str, counts)),)))
    else:
        r.warn("no checklist table rows found in AUDIT.md")

    # 2. the verdict is the one the rules give
    confirmed = scores.get("confirmed") or {}
    if mode in ("quick", "full") and level in (1, 2, 3) and isinstance(confirmed.get("critical"), int) and isinstance(confirmed.get("high"), int):
        computed, reasons = audit_verdict.compute_verdict(level, mode, confirmed["critical"], confirmed["high"], marks)
        if computed == verdict:
            r.ok("verdict matches the rules (%s)" % computed)
        else:
            r.fail("verdict is %s but the rules give %s: %s" % (verdict, computed, "; ".join(reasons)))
        sec = (scores.get("scores") or {}).get("security")
        if verdict == "no-blocking-problems" and isinstance(sec, int) and sec < 60:
            r.fail("green verdict but Security is %d (below 60)" % sec)

    # 4. tool names with a status in brackets must match the manifest
    if manifest_text is not None:
        statuses = {}
        for line in manifest_text.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) > 1:
                statuses.setdefault(parts[0], parts[1])
        problems = 0
        for tool, claimed in sorted(set(TOOL_STATUS.findall(report_text))):
            actual = statuses.get(tool)
            if actual is None:
                r.fail("AUDIT.md lists '%s' but it is not in manifest.tsv (a tool that did not run must not be listed as a source)" % tool)
                problems += 1
            elif not actual.startswith(claimed):
                r.fail("AUDIT.md says %s (%s) but manifest.tsv says: %s" % (tool, claimed, actual))
                problems += 1
        if not problems:
            r.ok("tool statuses in AUDIT.md match manifest.tsv")


def check_secrets(r, report_path, scores_path):
    leak = False
    for path in (report_path, scores_path):
        text = read(path)
        if text and SECRET_SHAPES.search(text):
            r.fail("%s contains text shaped like a secret (key, token or private key); remove it, never print values" % os.path.basename(path))
            leak = True
    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        tmp = tempfile.mkdtemp(prefix="verify")
        try:
            for path in (report_path, scores_path):
                if os.path.exists(path):
                    shutil.copy(path, tmp)
            cfg = os.path.join(HERE, "gitleaks-extra.toml")
            res = subprocess.run([gitleaks, "detect", "--no-git", "--source", ".", "--config", cfg, "--redact",
                                  "--report-format", "json", "--report-path", os.path.join(tmp, "out.json"), "--no-banner"],
                                 cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 1:
                r.fail("gitleaks found something secret-like in the report files; find and remove it")
                leak = True
            elif res.returncode != 0:
                r.warn("gitleaks could not check the report (exit %d)" % res.returncode)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        r.warn("gitleaks not installed: only the built-in key-shape check ran on the report")
    if not leak:
        r.ok("no secret-looking text in the report")


def main(argv):
    folder = argv[1] if len(argv) > 1 else None
    if not folder:
        latest = read(os.path.join("audit", "latest.txt"))
        folder = latest.strip() if latest else None
    r = Report()
    if not folder or not os.path.isdir(folder):
        r.fail("no audit folder (pass one, or run the scan first)")
        return 1
    report_path, scores_path = os.path.join(folder, "AUDIT.md"), os.path.join(folder, "scores.json")
    report_text = read(report_path)
    if report_text is not None:
        r.ok("AUDIT.md exists")
    else:
        r.fail("AUDIT.md is missing in %s" % folder)
    scores_text = read(scores_path)
    if scores_text is None:
        r.fail("scores.json is missing in %s" % folder)
        return 1
    try:
        scores = json.loads(scores_text)
        if not isinstance(scores, dict):
            raise ValueError("not an object")
    except ValueError:
        r.fail("scores.json is not valid JSON")
        return 1
    r.ok("scores.json is valid JSON")

    mode, level, verdict, counts = check_fields(r, scores)
    if report_text is not None:
        check_report(r, scores, report_text, read(os.path.join(folder, "manifest.tsv")), counts, verdict, mode, level)
    check_secrets(r, report_path, scores_path)

    print()
    print("REPORT OK" if r.fails == 0 else "REPORT HAS %d PROBLEM(S): fix them before showing it" % r.fails)
    return 0 if r.fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
