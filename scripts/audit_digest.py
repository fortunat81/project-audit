#!/usr/bin/env python3
"""Builds a compact digest of one scan run, so the report can be written without reading every raw
tool output.

    python audit_digest.py <audit-run-folder>

Writes in that folder:
    findings.tsv   one line per finding: id, source, severity, rule, file, line, count
    digest.txt     counts, the findings that need attention first, files several tools flagged,
                   and what was NOT covered

Reads only the tools' own result files. It never reads or prints a secret value: secret findings
carry the rule name and the location, nothing else. Full raw outputs stay in the folder.
Finding IDs are stable between runs: they come from source + rule + file, not from line numbers.
Standard library only (Python 3.8+).
"""
import hashlib
import json
import os
import re
import sys

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
TEXT_SOURCES = ["release-checks", "astro-set-html", "exposed-keys", "env-files", "supabase-rls",
                "firebase-rules", "supabase-service-role", "live-site"]


def norm(p):
    p = str(p or "").replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def severity(s):
    s = str(s or "").lower()
    if s in ("error", "high"):
        return "high"
    if s in ("warning", "medium", "moderate"):
        return "medium"
    if s == "critical":
        return "critical"
    if s in ("info", "informational"):
        return "info"
    return "low"


class Collector:
    def __init__(self, folder):
        self.folder = folder
        self.found = {}
        # Some tools print absolute paths; show them relative to the project (the folder that holds audit/)
        self.root = os.path.dirname(os.path.dirname(os.path.abspath(folder))).replace("\\", "/").rstrip("/") + "/"

    def read(self, name):
        try:
            with open(os.path.join(self.folder, name), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def json(self, name):
        text = self.read(name)
        if not text or not text.strip():
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def add(self, source, sev, rule, file, line=""):
        file = norm(file)
        if file.lower().startswith(self.root.lower()):
            file = file[len(self.root):]
        rule = str(rule or "finding")
        key = (source, rule, file)
        have = self.found.get(key)
        if have:
            have["count"] += 1
            if SEV_ORDER[sev] < SEV_ORDER[have["severity"]]:
                have["severity"] = sev   # the file shows its worst finding
            return
        fid = "F-" + hashlib.sha1("|".join(key).encode("utf-8")).hexdigest()[:6]  # nosemgrep: only a short stable label for a finding, not a security use
        self.found[key] = {"id": fid, "source": source, "severity": sev, "rule": rule,
                           "file": file, "line": line if line is not None else "", "count": 1}

    # --- JSON tools ---------------------------------------------------------
    def gitleaks(self):
        for name in ("gitleaks.json", "gitleaks-uncommitted.json"):
            data = self.json(name)
            if isinstance(data, list):
                for x in data:   # the value fields are never read
                    self.add(name[:-5], "high", x.get("RuleID"), x.get("File"), x.get("StartLine"))

    def semgrep(self):
        for name in ("semgrep.json", "semgrep-astro.json"):
            data = self.json(name)
            if not isinstance(data, dict):
                continue
            for r in data.get("results") or []:
                path = norm(r.get("path"))
                m = re.search(r"astro-extract/(.*?)(\.script)?\.ts$", path)   # map extracted code back to the .astro file
                if m:
                    path = m.group(1)
                self.add(name[:-5], severity((r.get("extra") or {}).get("severity")),
                         str(r.get("check_id") or "").split(".")[-1], path, (r.get("start") or {}).get("line"))

    def zizmor(self):
        data = self.json("zizmor.json")
        if not isinstance(data, list):
            return
        for x in data:
            locs = x.get("locations") or [{}]
            loc = locs[0]
            key = ((loc.get("symbolic") or {}).get("key") or {})
            key = key.get("Local") or key
            file = key.get("given_path") or key.get("verbatim_path") or ""
            row = (((loc.get("concrete") or {}).get("location") or {}).get("start_point") or {}).get("row")
            self.add("zizmor", severity((x.get("determinations") or {}).get("severity")), x.get("ident"),
                     file, row + 1 if isinstance(row, int) else "")

    def osv(self):
        data = self.json("osv-scanner.json")
        if not isinstance(data, dict):
            return
        for r in data.get("results") or []:
            for p in r.get("packages") or []:
                vulns = p.get("vulnerabilities") or []
                if not vulns:
                    continue
                top = 0.0
                for g in p.get("groups") or []:
                    try:
                        top = max(top, float(g.get("max_severity")))
                    except (TypeError, ValueError):
                        pass
                sev = "critical" if top >= 9 else "high" if top >= 7 else "medium" if top >= 4 else "low" if top > 0 else "medium"
                pkg = p.get("package") or {}
                self.add("osv-scanner", sev, "%s@%s (%d advisories)" % (pkg.get("name"), pkg.get("version"), len(vulns)),
                         (r.get("source") or {}).get("path"))

    def npm_audit(self):
        for name in ("npm-audit.json", "npm-audit-shipped.json"):
            data = self.json(name)
            if isinstance(data, dict) and isinstance(data.get("vulnerabilities"), dict):
                for pkg, v in data["vulnerabilities"].items():
                    self.add(name[:-5], severity((v or {}).get("severity")), pkg, "package-lock.json")

    def eslint(self):
        data = self.json("eslint.json")
        if isinstance(data, list):
            for fl in data:
                for m in fl.get("messages") or []:
                    self.add("eslint", "medium" if m.get("severity") == 2 else "low",
                             m.get("ruleId") or "parse-error", fl.get("filePath"), m.get("line"))

    # --- Text tools ---------------------------------------------------------
    def tsc(self):
        text = self.read("tsc.txt")
        for line in (text or "").splitlines():
            m = re.match(r"^(.+?)\((\d+),\d+\): error (TS\d+)", line)
            if m:
                self.add("tsc", "medium", m.group(3), m.group(1), m.group(2))

    def lizard(self):
        text = self.read("lizard.txt")
        for line in (text or "").splitlines():
            m = re.match(r"^(.+?):(\d+): warning: (\S+) has", line)
            if m:
                self.add("lizard", "low", "complex-or-long-function:" + m.group(3), m.group(1), m.group(2))

    def text_checks(self):
        loc_a = re.compile(r"([A-Za-z0-9_@./\\()\[\]-]+\.[A-Za-z0-9]+|Dockerfile[^\s:]*)(?::(\d+))?\s*$")
        loc_b = re.compile(r"([A-Za-z0-9_@./\\-]+\.[A-Za-z0-9]+):(\d+)")
        for name in TEXT_SOURCES:
            text = self.read(name + ".txt")
            if not text:
                continue
            for line in text.splitlines():
                if not line.strip():
                    continue
                m = loc_a.search(line) or loc_b.search(line)
                head = re.sub(r"^(FAIL|WARN)\s+", "", line)
                rule = re.split(r"[:(]", head)[0].strip()[:40] or name
                if line.startswith("FAIL"):
                    sev = "high"
                elif line.startswith("WARN"):
                    sev = "medium"
                elif line.startswith("NO RLS"):
                    sev = "critical"   # reviews/supabase.md: a table without row-level security is open to anyone with the public key
                elif line.startswith("REVIEW open policy") and re.search(r"for\s+(insert|update|delete|all)\b|with\s+check", line, re.I):
                    sev = "high"       # an open policy that lets anyone write (a read-only open policy stays medium)
                elif re.search(r"COMMITTED TO GIT|CLIENT-VISIBLE|OPEN TO EVERYONE|service.role", line, re.I):
                    sev = "high"
                else:
                    sev = "medium"
                file, ln = (m.group(1), m.group(2) or "") if m else ("", "")
                self.add(name, sev, rule, file, ln)

    def collect(self):
        for step in (self.gitleaks, self.semgrep, self.zizmor, self.osv, self.npm_audit, self.eslint,
                     self.tsc, self.lizard, self.text_checks):
            try:
                step()
            except Exception as exc:   # one broken result file must not lose the others
                sys.stderr.write("digest: %s failed: %s\n" % (step.__name__, exc))
        return sorted(self.found.values(), key=lambda f: (SEV_ORDER[f["severity"]], f["source"], f["file"]))


def read_manifest(folder):
    rows = []
    try:
        with open(os.path.join(folder, "manifest.tsv"), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()[1:]
    except OSError:
        return rows
    for line in lines:
        if line.strip():
            parts = line.split("\t")
            rows.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return rows


def _digest_lines(folder, findings, manifest):
    """The text of digest.txt, as a list of lines."""
    by_sev, counts, per_file = {}, {}, {}
    for x in findings:
        by_sev[x["severity"]] = by_sev.get(x["severity"], 0) + 1
        counts[x["source"]] = counts.get(x["source"], 0) + 1
        if x["file"]:
            per_file.setdefault(x["file"], set()).add(x["source"])
    detail = ", ".join("%d %s" % (by_sev[s], s) for s in ("critical", "high", "medium", "low", "info") if by_sev.get(s))
    out = ["DIGEST of %s" % os.path.basename(os.path.normpath(folder)),
           "%d distinct findings%s" % (len(findings), ": " + detail if findings else ""),
           "(IDs are stable between runs. Open the file and line before calling anything confirmed. No secret values appear here.)",
           "", "NEEDS ATTENTION FIRST (critical and high, up to 30):"]
    top = [x for x in findings if x["severity"] in ("critical", "high")][:30]
    for x in top:
        out.append("  %s  %-8s %-22s %s  %s%s%s" % (x["id"], x["severity"], x["source"], x["rule"], x["file"],
                                                 ":" + str(x["line"]) if x["line"] != "" else "",
                                                 "  (x%d)" % x["count"] if x["count"] > 1 else ""))
    if not top:
        out.append("  none")
    out += ["", "FILES FLAGGED BY MORE THAN ONE TOOL (read these first):"]
    multi = sorted((kv for kv in per_file.items() if len(kv[1]) > 1), key=lambda kv: -len(kv[1]))[:10]
    out += ["  %s  <- %s" % (file, ", ".join(sorted(sources))) for file, sources in multi]
    if not multi:
        out.append("  none")
    out += ["", "BY TOOL (status from manifest.tsv, findings counted here):"]
    for tool, status in manifest:
        n = counts.get(tool)
        out.append("  %-24s %-70s %s" % (tool, status[:70], "%d finding(s)" % n if n is not None else ""))
    out += ["", "NOT FULLY COVERED:"]
    gaps = [(t, s) for t, s in manifest if re.match(r"^(failed-to-run|timeout|skipped|unavailable|partial)", s)]
    out += ["  %s: %s" % (tool, status) for tool, status in gaps]
    if not gaps:
        out.append("  nothing")
    return out


def write_outputs(folder, findings, manifest):
    with open(os.path.join(folder, "findings.tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("id\tsource\tseverity\trule\tfile\tline\tcount\n")
        for x in findings:
            f.write("\t".join(str(x[k]) for k in ("id", "source", "severity", "rule", "file", "line", "count")) + "\n")
    with open(os.path.join(folder, "digest.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(_digest_lines(folder, findings, manifest)) + "\n")


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        sys.stderr.write("usage: audit_digest.py <audit-run-folder>\n")
        return 1
    folder = argv[1]
    findings = Collector(folder).collect()
    write_outputs(folder, findings, read_manifest(folder))
    print("digest: %d findings -> findings.tsv, digest.txt" % len(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
