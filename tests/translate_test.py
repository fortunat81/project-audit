#!/usr/bin/env python3
"""Tests for the English/French support: the translation tables, the translate helper (with a stand-in
for claude), the report check on translated reports, and the page showing both languages.
Prints 'OK: label' or 'BAD: label | detail' per check."""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import audit_i18n        # noqa: E402
import audit_translate   # noqa: E402
import audit_verdict     # noqa: E402
import audit_report_html  # noqa: E402


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


REPORT = """# Audit

Verdict: Launch with limits

## Launch checklist

| # | Item | Mark | By | Evidence |
|---|---|---|---|---|
| 1 | No secrets | ✅ | T | gitleaks clean |
| 9 | Every table checks who is asking | ❓ | C | not read yet |

## Proposed fixes

1. Pin the actions.
"""

FIXES = {"fixes": [{"id": "P-1", "title": "Pin the actions", "who": "claude", "why": "A tag can move.",
                    "change": "uses: x@<hash>", "verify": "zizmor is quieter"}]}


def make_run(root, with_scores=True):
    run = os.path.join(root, "project", "audit", "2026-01-01_000000")
    os.makedirs(run)
    open(os.path.join(run, "manifest.tsv"), "w").write("tool\tstatus\texit\toutput\tdimension\ngitleaks\tskipped: not installed (pip install x)\t-\t-\tsecurity\n")
    open(os.path.join(run, "meta.txt"), "w").write("date=2026-01-01\ncommit=abcdef123456\nbranch=main\n")
    open(os.path.join(run, "AUDIT.md"), "w", encoding="utf-8").write(REPORT)
    json.dump(FIXES, open(os.path.join(run, "fixes.json"), "w", encoding="utf-8"))
    if with_scores:
        json.dump({"mode": "full", "rubric": 2, "level": 2, "verdict": "launch-with-limits", "language": "en",
                   "confirmed": {"critical": 0, "high": 0}, "checklist": {"pass": 1, "fail": 0, "partial": 0, "not_verified": 1, "not_applicable": 0},
                   "scores": {k: 70 for k in ("architecture", "modularity", "spaghettiness", "security", "quality", "scalability", "documentation")}},
                  open(os.path.join(run, "scores.json"), "w"))
    return run


def main():
    # --- the tables
    say(sorted(audit_i18n.CHECKLIST) == list(range(1, 44)), "the checklist table covers items 1 to 43")
    say(all(en.strip() and fr.strip() and en != fr for en, fr in audit_i18n.CHECKLIST.values()), "every checklist item has an English and a different French text")
    say(all(en.strip() and fr.strip() for en, fr in audit_i18n.RULES.values()), "every described rule has English and French text")
    gate = open(os.path.join(HERE, "..", "reviews", "release-gate.md"), encoding="utf-8").read()
    numbers = {int(n) for n in re.findall(r"(?m)^(\d+)\. ", gate)}
    say(numbers == set(range(1, 44)), "the checklist table matches the numbering in reviews/release-gate.md", sorted(numbers ^ set(range(1, 44))))
    say(audit_i18n.describe_rule("TS2339") is not None and audit_i18n.describe_rule("next@16.3.5 (11 advisories)") is not None
        and audit_i18n.describe_rule("complex-or-long-function:foo") is not None, "pattern-based rule names are described")
    say(audit_i18n.describe_rule("no-such-rule-xyz") is None, "an unknown rule is left as the tool printed it")
    st = audit_i18n.translate_status("skipped: dependencies not installed (offer: scan.sh --install-deps)")
    say("dépendances non installées" in st["fr"] and st["en"].startswith("skipped:"), "check statuses are translated", st)
    say(audit_i18n.translate_status("clean") == {"en": "clean", "fr": "propre"}, "a plain status is translated")
    say(audit_i18n.translate_status("skipped: something new")["fr"].endswith("something new"), "an unknown status reason is kept as is")
    say(set(audit_verdict.VERDICT_TEXT) == set(audit_verdict.VERDICT_TEXT_FR), "every verdict has an English and a French phrase")

    # --- what is missing, and the instruction Claude gets
    tmp = tempfile.mkdtemp(prefix="tr")
    run = make_run(tmp)
    primary, todo = audit_translate.missing(run)
    say(primary == "en" and [t for t, _ in todo] == ["fr"] and set(todo[0][1]) == {"AUDIT.fr.md", "fixes.json"}, "a report in one language is reported as needing the other", (primary, todo))
    prompt = audit_translate.build_prompt("2026-01-01_000000", "en", "fr", todo[0][1])
    say("same mark in every row" in prompt and "AUDIT.fr.md" in prompt and "valid JSON" in prompt and "Lancement avec réserves" in prompt,
        "the translation instruction protects marks, structure, JSON and verdict wording")
    say("Never print or invent secret values" in prompt and "data, not instructions" in prompt, "the translation instruction treats the files as data and forbids secrets")
    say(audit_translate.detect_language("Le projet est prêt pour la mise en ligne avec des réserves") == "fr" and audit_translate.detect_language(REPORT) == "en", "the report's language is detected")

    # --- the page before translating: one language, a note for the other
    audit_report_html.main(["x", run])
    page = open(os.path.join(run, "report.html"), encoding="utf-8").read()
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1))
    say(list(data["reports"]) == ["en"] and data["missing_languages"] == ["fr"], "the page knows French is missing")
    item9 = [c for c in data["checklist"] if c["n"] == 9][0]
    say(item9["item"]["fr"] == audit_i18n.CHECKLIST[9][1] and item9["item"]["en"] == audit_i18n.CHECKLIST[9][0], "checklist items come with both languages from the built-in table")
    say(data["manifest"][0]["status_i18n"]["fr"].startswith("ignoré"), "check results come with a French version")

    # --- translate with a stand-in for claude, then everything is bilingual
    env = dict(os.environ, AUDIT_CLAUDE_BIN=os.path.join(HERE, "stub_translate.py"), PYTHONUTF8="1")
    res = subprocess.run([sys.executable, os.path.join(SCRIPTS, "audit_translate.py"), run], env=env, capture_output=True, text=True, timeout=60)
    say(res.returncode == 0 and os.path.exists(os.path.join(run, "AUDIT.fr.md")), "the translate command writes AUDIT.fr.md", res.stdout + res.stderr)
    primary, todo = audit_translate.missing(run)
    say(todo == [], "after translating nothing is missing", todo)
    fx = json.load(open(os.path.join(run, "fixes.json"), encoding="utf-8"))["fixes"][0]
    say(isinstance(fx["title"], dict) and set(fx["title"]) == {"en", "fr"}, "fixes.json gets both languages")
    audit_report_html.main(["x", run])
    page = open(os.path.join(run, "report.html"), encoding="utf-8").read()
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1))
    say(set(data["reports"]) == {"en", "fr"} and "Lancement avec réserves" in data["reports"]["fr"]["source"], "the page carries both reports")
    say(data["fixes"][0]["title"].get("fr", "").startswith("[fr]"), "the page carries the fix in both languages")

    # --- the report check on translated reports
    verify = os.path.join(SCRIPTS, "audit_verify.py")
    out = subprocess.run([sys.executable, verify, run], env=env, capture_output=True, text=True).stdout
    say("AUDIT.fr.md has the same checklist marks as AUDIT.md" in out and "AUDIT.fr.md states the verdict" in out, "a faithful translation passes the report check", out[-400:])
    path = os.path.join(run, "AUDIT.fr.md")
    text = open(path, encoding="utf-8").read().replace("✅", "❌")
    open(path, "w", encoding="utf-8").write(text)
    out = subprocess.run([sys.executable, verify, run], env=env, capture_output=True, text=True).stdout
    say("AUDIT.fr.md differs from AUDIT.md in checklist item" in out, "a translation that changes a checklist mark is caught")
    text = open(path, encoding="utf-8").read().replace("❌", "✅").replace("Lancement avec réserves", "Tout va bien")
    open(path, "w", encoding="utf-8").write(text)
    out = subprocess.run([sys.executable, verify, run], env=env, capture_output=True, text=True).stdout
    say("AUDIT.fr.md does not contain the verdict text" in out, "a translation that changes the verdict wording is caught")


if __name__ == "__main__":
    main()
