#!/usr/bin/env python3
"""The release verdict, computed from rules instead of judged.

    python audit_verdict.py <audit-run-folder>      prints the verdict and the reason for it
    python audit_verdict.py --level 2 --mode full --critical 0 --high 0 --marks 1:pass,2:fail

The rules are the ones in reviews/release-gate.md ("The verdict"). Inputs:
    level       1, 2 or 3                      (scores.json: "level")
    mode        quick or full                  (scores.json: "mode")
    critical    confirmed critical findings    (scores.json: "confirmed": {"critical": n})
    high        confirmed high findings        (scores.json: "confirmed": {"high": n})
    marks       checklist item number -> mark  (the checklist table in AUDIT.md)
Marks are pass, fail, partial, unverified or na. Standard library only (Python 3.8+).
"""
import os
import re
import sys
import json

# Checklist item numbers by group, as in reviews/release-gate.md
GROUPS = {"A": (1, 4), "B": (5, 8), "C": (9, 12), "D": (13, 17), "E": (18, 21), "F": (22, 26),
          "G": (27, 30), "H": (31, 34), "I": (35, 39), "J": (40, 43)}
BLOCKING_GROUPS = "ABCD"       # a failed item here means "don't launch yet"

EMOJI_MARKS = (("✅", "pass"), ("❌", "fail"), ("⚠", "partial"), ("❓", "unverified"), ("➖", "na"))
VERDICT_TEXT = {"dont-launch": "Don't launch yet", "launch-with-limits": "Launch with limits",
                "no-blocking-problems": "No blocking problems found"}


def group_of(number):
    for name, (lo, hi) in GROUPS.items():
        if lo <= number <= hi:
            return name
    return "?"


def mark_from_cell(cell):
    for emoji, name in EMOJI_MARKS:
        if emoji in cell:
            return name
    return None


def read_marks(audit_md_text):
    """Item number -> mark, from the rows of the checklist table in AUDIT.md."""
    marks = {}
    for line in audit_md_text.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|(.*)$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        mark = mark_from_cell(cells[1]) if len(cells) > 1 else None   # columns: item | mark | by | evidence
        if mark:
            marks[int(m.group(1))] = mark
    return marks


def compute_verdict(level, mode, critical, high, marks):
    """Returns (verdict, [reasons]). The first matching rule wins."""
    blockers = []
    if critical > 0:
        blockers.append("%d confirmed critical finding(s)" % critical)
    if high > 0:
        blockers.append("%d confirmed high finding(s)" % high)
    failed_blocking = sorted(n for n, m in marks.items() if m == "fail" and group_of(n) in BLOCKING_GROUPS)
    if failed_blocking:
        blockers.append("failed checklist item(s) in groups A to D: %s" % ", ".join(map(str, failed_blocking)))
    if blockers:
        return "dont-launch", blockers

    reasons = []
    others = sorted(n for n, m in marks.items() if m == "fail" and group_of(n) not in BLOCKING_GROUPS)
    if others:
        reasons.append("failed checklist item(s) outside groups A to D: %s" % ", ".join(map(str, others)))
    open_items = sorted(n for n, m in marks.items() if m in ("partial", "unverified"))
    if open_items:
        reasons.append("%d checklist item(s) partly done or not verified: %s" % (len(open_items), ", ".join(map(str, open_items))))
    if level == 3:
        reasons.append("Level 3 cannot be green without the specialist items (threat model, penetration test, restore exercise, legal review)")
    if mode == "quick" and level >= 2:
        reasons.append("a quick audit of a Level 2 or 3 project leaves the Claude-checked items unverified")
    if not marks:
        reasons.append("no checklist marks were found, so nothing supports a green verdict")
    if reasons:
        return "launch-with-limits", reasons
    return "no-blocking-problems", ["no blocking findings, and every checklist item is passed or not applicable"]


def from_folder(folder):
    with open(os.path.join(folder, "scores.json"), encoding="utf-8") as f:
        scores = json.load(f)
    try:
        with open(os.path.join(folder, "AUDIT.md"), encoding="utf-8") as f:
            marks = read_marks(f.read())
    except OSError:
        marks = {}
    confirmed = scores.get("confirmed") or {}
    return (int(scores.get("level") or 0), scores.get("mode"), int(confirmed.get("critical") or 0),
            int(confirmed.get("high") or 0), marks)


def main(argv):
    args = argv[1:]
    if len(args) == 1 and os.path.isdir(args[0]):
        try:
            level, mode, critical, high, marks = from_folder(args[0])
        except (OSError, ValueError) as exc:
            sys.stderr.write("cannot read the audit folder: %s\n" % exc)
            return 2
    else:
        opts = {}
        for i in range(0, len(args) - 1, 2):
            opts[args[i]] = args[i + 1]
        if not {"--level", "--mode"} <= set(opts):
            sys.stderr.write(__doc__)
            return 2
        level, mode = int(opts["--level"]), opts["--mode"]
        critical, high = int(opts.get("--critical", 0)), int(opts.get("--high", 0))
        marks = {}
        for pair in filter(None, opts.get("--marks", "").split(",")):
            n, _, name = pair.partition(":")
            marks[int(n)] = name
    verdict, reasons = compute_verdict(level, mode, critical, high, marks)
    print("VERDICT=%s" % verdict)
    print("TEXT=%s" % VERDICT_TEXT[verdict])
    for r in reasons:
        print("REASON=%s" % r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
