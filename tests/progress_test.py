#!/usr/bin/env python3
"""Tests for the live progress page (scripts/audit_progress.py): it refreshes itself while the scan runs, lists the
checks done so far, says when Claude is writing the report, and turns into a redirect to report.html once the written
report exists. Prints 'OK: label' or 'BAD: label | detail' per check."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import audit_progress  # noqa: E402


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def read(folder):
    with open(os.path.join(folder, "progress.html"), encoding="utf-8") as f:
        return f.read()


d = tempfile.mkdtemp()
with open(os.path.join(d, "manifest.tsv"), "w", encoding="utf-8", newline="\n") as f:
    f.write("tool\tstatus\texit\toutput\tdimension\ngitleaks\tfindings\t1\tgitleaks.json\tsecurity\nsemgrep\tskipped: no <net>\t-\t-\tsecurity\n")

audit_progress.write(d, "scanning")
page = read(d)
say('http-equiv="refresh"' in page, "while scanning the page refreshes itself")
say("gitleaks" in page and "semgrep" in page, "the checks done so far are listed")
say("&lt;net&gt;" in page and "<net>" not in page, "text from the manifest is escaped")
say("report.html" not in page.split("<body>")[0], "no redirect while scanning")

audit_progress.write(d, "review")
page = read(d)
say('http-equiv="refresh"' in page and "writing the report" in page, "after the scan it says Claude is writing the report and keeps refreshing")

audit_progress.write(d, "done")
page = read(d)
say('url=report.html' in page, "when the report is written the page redirects to report.html")

# the web page builder switches the progress page to the redirect when the written report exists
with open(os.path.join(d, "AUDIT.md"), "w", encoding="utf-8") as f:
    f.write("# x\n")
say(audit_progress.state_for(d) == "done", "a folder with AUDIT.md is in the done state")
os.remove(os.path.join(d, "AUDIT.md"))
say(audit_progress.state_for(d) == "scanning", "a folder without coverage.txt is still scanning")
with open(os.path.join(d, "coverage.txt"), "w", encoding="utf-8") as f:
    f.write("COVERAGE: 0\n")
say(audit_progress.state_for(d) == "review", "a finished scan without AUDIT.md is in the review state")
