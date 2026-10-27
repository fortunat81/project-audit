#!/usr/bin/env python3
"""Tests for the findings digest (scripts/audit_digest.py): scanner output in, findings out.
The sample outputs have the shape of each tool's real output (gitleaks, semgrep, zizmor, osv-scanner,
npm audit, ESLint, tsc, lizard and the script's own pattern checks). Checks severity mapping, stable IDs,
path cleaning, that a secret value never reaches the digest or the web page, and that one broken file
does not lose the others. Prints 'OK: label' or 'BAD: label | detail' per check."""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import audit_digest       # noqa: E402
import audit_report_html  # noqa: E402

SECRET = "FAKE-SECRET-VALUE-DO-NOT-LEAK-0123456789"


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def run_folder(files, root=None):
    root = root or tempfile.mkdtemp(prefix="digest")
    run = os.path.join(root, "audit", "2026-01-01_000000")
    os.makedirs(run)
    for name, content in files.items():
        with open(os.path.join(run, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))
    return root, run


def rows(findings):
    return {(f["source"], f["rule"], f["file"]): f for f in findings}


GITLEAKS = [
    {"RuleID": "env-style-secret", "File": ".txt", "StartLine": 3, "Secret": SECRET, "Match": "RESEND_API_KEY=" + SECRET, "Commit": "abc123"},
    {"RuleID": "env-style-secret", "File": ".txt", "StartLine": 4, "Secret": SECRET, "Match": "TURNSTILE_SECRET_KEY=" + SECRET},
    {"RuleID": "aws-access-token", "File": "lib\\config.ts", "StartLine": 9, "Secret": SECRET, "Match": SECRET},
]
SEMGREP = {"results": [
    {"check_id": "javascript.lang.security.audit.eval-detected.eval-detected", "path": "src\\a.ts", "start": {"line": 5}, "extra": {"severity": "ERROR", "lines": SECRET}},
    {"check_id": "yaml.github-actions.security.mutable-tag.github-actions-mutable-action-tag", "path": ".github/workflows/x.yml", "start": {"line": 7}, "extra": {"severity": "WARNING"}},
    {"check_id": "x.y.some-hint", "path": "./b.py", "start": {"line": 1}, "extra": {"severity": "INFO"}},
], "errors": [], "paths": {"scanned": ["src/a.ts"]}}
ZIZMOR = [{"ident": "unpinned-uses", "determinations": {"severity": "High"},
           "locations": [{"symbolic": {"key": {"Local": {"verbatim_path": ".\\.github\\workflows\\deploy.yml"}}}, "concrete": {"location": {"start_point": {"row": 46, "column": 8}}}}]}]
OSV = {"results": [{"source": {"path": "C:/proj/package-lock.json", "type": "lockfile"}, "packages": [
    {"package": {"name": "next", "version": "16.3.5"}, "vulnerabilities": [{"id": "A"}, {"id": "B"}], "groups": [{"max_severity": "9.8"}]},
    {"package": {"name": "vite", "version": "8.3.0"}, "vulnerabilities": [{"id": "C"}], "groups": [{"max_severity": "7.5"}]},
    {"package": {"name": "zod", "version": "3.0.0"}, "vulnerabilities": [{"id": "D"}], "groups": [{"max_severity": "5.0"}]},
    {"package": {"name": "uuid", "version": "7.0.3"}, "vulnerabilities": [{"id": "E"}]},
    {"package": {"name": "clean-pkg", "version": "1.0.0"}},
]}]}
NPM_AUDIT = {"auditReportVersion": 2, "vulnerabilities": {"lodash": {"severity": "high"}, "minimist": {"severity": "moderate"}}}
ESLINT = [{"filePath": "C:/proj/src/a.ts", "messages": [{"ruleId": "no-unused-vars", "severity": 2, "line": 3}, {"ruleId": None, "severity": 2, "line": 1}, {"ruleId": "semi", "severity": 1, "line": 9}]}]
TSC = "src/a.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.\nsrc/b.ts(2,1): error TS2304: Cannot find name 'x'.\nnoise line\n"
LIZARD = "./src/big.py:10: warning: big_function has 80 NLOC, 25 CCN, 600 token, 1 PARAM, 90 length, 0 ND\n"
RELEASE = "FAIL  DEBUG-ON: debug mode switched on, shows internals to visitors: src/app.py:9\nWARN  CORS-OPEN: answers requests from every website (fine only for a public read-only API): src/app.py:5\nWARN  NO-TESTS: no automated tests found\n"
ENV_FILES = "COMMITTED TO GIT (rotate what it held): apps/web/.env\n"
EXPOSED = "CLIENT-VISIBLE: src/lib/ai.ts:6:EXPO_PUBLIC_OPENAI_API_KEY\n"
MANIFEST = ("tool\tstatus\texit\toutput\tdimension\n"
            "gitleaks\tfindings\t1\tgitleaks.json\tsecurity\nsemgrep\tfindings\t0\tsemgrep.json\tsecurity\n"
            "npm-audit\tskipped: no lockfile\t-\t-\tsecurity\nlizard\tpartial: JavaScript files left out\t0\tlizard.txt\tspaghettiness\n")


def main():
    everything = {"gitleaks.json": GITLEAKS, "semgrep.json": SEMGREP, "zizmor.json": ZIZMOR, "osv-scanner.json": OSV, "npm-audit.json": NPM_AUDIT,
                  "eslint.json": ESLINT, "tsc.txt": TSC, "lizard.txt": LIZARD, "release-checks.txt": RELEASE, "env-files.txt": ENV_FILES,
                  "exposed-keys.txt": EXPOSED, "manifest.tsv": MANIFEST}
    project = tempfile.mkdtemp(prefix="digest")
    osv = json.loads(json.dumps(OSV))
    osv["results"][0]["source"]["path"] = project.replace("\\", "/") + "/package-lock.json"   # an absolute path inside the project
    everything["osv-scanner.json"] = osv
    root, run = run_folder(everything, project)
    findings = audit_digest.Collector(run).collect()
    by = rows(findings)

    # severity mapping per tool
    say(by[("gitleaks", "env-style-secret", ".txt")]["severity"] == "high", "a secret found by gitleaks is high")
    say(by[("semgrep", "eval-detected", "src/a.ts")]["severity"] == "high", "Semgrep ERROR is high")
    say(by[("semgrep", "github-actions-mutable-action-tag", ".github/workflows/x.yml")]["severity"] == "medium", "Semgrep WARNING is medium")
    say(by[("semgrep", "some-hint", "b.py")]["severity"] == "info", "Semgrep INFO is info")
    say(by[("zizmor", "unpinned-uses", ".github/workflows/deploy.yml")]["severity"] == "high", "zizmor High is high")
    osv = {f["rule"].split("@")[0]: f["severity"] for f in findings if f["source"] == "osv-scanner"}
    say(osv == {"next": "critical", "vite": "high", "zod": "medium", "uuid": "medium"}, "osv-scanner severity comes from the advisory score (9.8 critical, 7.5 high, 5 medium, unknown medium)", osv)
    say("clean-pkg" not in " ".join(osv), "a package with no advisories is not a finding")
    npm = {f["rule"]: f["severity"] for f in findings if f["source"] == "npm-audit"}
    say(npm == {"lodash": "high", "minimist": "medium"}, "npm audit severities map (moderate is medium)", npm)
    eslint = [f for f in findings if f["source"] == "eslint"]
    say(len(eslint) == 3 and {f["severity"] for f in eslint} == {"medium", "low"}, "ESLint errors are medium and warnings low, including parse errors without a rule", eslint)
    tsc = {f["rule"]: f["line"] for f in findings if f["source"] == "tsc"}
    say(tsc == {"TS2322": "10", "TS2304": "2"}, "tsc errors are read with their line numbers", tsc)
    say(by[("lizard", "complex-or-long-function:big_function", "src/big.py")]["severity"] == "low", "a long or complex function is low")
    rc = {f["rule"]: f for f in findings if f["source"] == "release-checks"}
    say(rc["DEBUG-ON"]["severity"] == "high" and rc["CORS-OPEN"]["severity"] == "medium" and rc["NO-TESTS"]["file"] == "", "release checks: FAIL is high, WARN is medium, file is kept when there is one", rc)
    say(by[("env-files", "COMMITTED TO GIT", "apps/web/.env")]["severity"] == "high", "a committed .env file is high")
    say(by[("exposed-keys", "CLIENT-VISIBLE", "src/lib/ai.ts")]["severity"] == "high", "a secret-looking variable in the client bundle is high")

    # same finding in several places collapses, with a count
    leak = by[("gitleaks", "env-style-secret", ".txt")]
    say(leak["count"] == 2, "two hits of one rule in one file become one finding with a count of 2", leak)

    # paths are cleaned
    say(("gitleaks", "aws-access-token", "lib/config.ts") in by, "backslashes in paths become slashes")
    say(("semgrep", "some-hint", "b.py") in by, "a leading ./ is removed")
    say(any(f["file"] == "package-lock.json" for f in findings if f["source"] == "osv-scanner"), "absolute paths inside the project are shown relative to it", [f["file"] for f in findings if f["source"] == "osv-scanner"])
    astro = {"semgrep-astro.json": {"results": [{"check_id": "a.b.eval-detected", "path": "C:\\tmp\\astro-extract\\src\\pages\\index.astro.script.ts", "start": {"line": 10}, "extra": {"severity": "ERROR"}},
                                                  {"check_id": "a.b.exec", "path": "/tmp/x/astro-extract/src/pages/index.astro.ts", "start": {"line": 4}, "extra": {"severity": "ERROR"}}]}}
    _, arun = run_folder(astro)
    names = {f["file"] for f in audit_digest.Collector(arun).collect()}
    say(names == {"src/pages/index.astro"}, "findings in extracted Astro code are shown on the original .astro file", names)

    # IDs are stable
    again = audit_digest.Collector(run).collect()
    say({f["id"] for f in findings} == {f["id"] for f in again}, "the same scan gives the same finding IDs")
    moved = dict(everything)
    moved["semgrep.json"] = json.loads(json.dumps(SEMGREP))
    moved["semgrep.json"]["results"][0]["start"]["line"] = 99
    _, mrun = run_folder(moved)
    m = rows(audit_digest.Collector(mrun).collect())
    say(m[("semgrep", "eval-detected", "src/a.ts")]["id"] == by[("semgrep", "eval-detected", "src/a.ts")]["id"], "a finding keeps its ID when its line number changes")
    say(len({f["id"] for f in findings}) == len(findings), "every finding has its own ID")
    say(all(re.match(r"^F-[0-9a-f]{6}$", f["id"]) for f in findings), "IDs look like F-xxxxxx")

    # no secret value anywhere
    audit_digest.write_outputs(run, findings, audit_digest.read_manifest(run))
    audit_report_html.main(["x", run])
    texts = [open(os.path.join(run, n), encoding="utf-8").read() for n in ("findings.tsv", "digest.txt", "report.html")]
    say(not any(SECRET in t for t in texts), "a secret value in a tool's output never reaches findings.tsv, digest.txt or the web page")

    # digest content
    digest = texts[1]
    say("NEEDS ATTENTION FIRST" in digest and "critical" in digest.split("\n")[1], "the digest starts with counts and the worst findings", digest.split("\n")[:3])
    say("NOT FULLY COVERED" in digest and "npm-audit: skipped: no lockfile" in digest and "lizard: partial" in digest, "the digest lists what was not covered")
    order = [f["severity"] for f in findings]
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    say(order == sorted(order, key=lambda s: ranks[s]), "findings are sorted from most to least serious")

    # a broken result file does not lose the others
    broken = dict(everything)
    broken["semgrep.json"] = "{not json at all"
    broken["zizmor.json"] = ""
    _, brun = run_folder(broken)
    b = audit_digest.Collector(brun).collect()
    say(any(f["source"] == "gitleaks" for f in b) and not any(f["source"] == "semgrep" for f in b), "an unreadable result file is skipped and the others still count")
    _, erun = run_folder({})
    say(audit_digest.Collector(erun).collect() == [], "an empty run folder gives no findings and no crash")


if __name__ == "__main__":
    main()
