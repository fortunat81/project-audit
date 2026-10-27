#!/usr/bin/env node
// Builds a compact digest of one scan run, so the report can be written without reading every raw
// tool output. Usage: node digest.js <audit-run-folder>
//   findings.tsv  one line per finding: id, source, severity, rule, file, line, count
//   digest.txt    counts, the findings that need attention first, files several tools flagged,
//                 and what was NOT covered
// Reads only the tools' own result files. It never reads or prints a secret value: secret findings
// carry the rule name and the location, nothing else. Full raw outputs stay in the folder.
// Finding IDs are stable between runs: they come from source + rule + file, not from line numbers.

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const dir = process.argv[2];
if (!dir || !fs.existsSync(dir)) { console.error("usage: node digest.js <audit-run-folder>"); process.exit(1); }

const read = (f) => { try { return fs.readFileSync(path.join(dir, f), "utf8"); } catch { return null; } };
const json = (f) => { const t = read(f); if (!t || !t.trim()) return null; try { return JSON.parse(t); } catch { return null; } };
const norm = (p) => String(p || "").replace(/\\/g, "/").replace(/^\.\//, "");

const found = new Map();   // key -> finding
function add(source, severity, rule, file, line) {
  file = norm(file); rule = String(rule || "finding");
  const key = [source, rule, file].join("|");
  const id = "F-" + crypto.createHash("sha1").update(key).digest("hex").slice(0, 6);
  const have = found.get(key);
  if (have) { have.count++; return; }
  found.set(key, { id, source, severity, rule, file, line: line || "", count: 1 });
}
const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const sev = (s) => {
  s = String(s || "").toLowerCase();
  if (s === "error" || s === "high") return "high";
  if (s === "warning" || s === "medium" || s === "moderate") return "medium";
  if (s === "critical") return "critical";
  if (s === "info" || s === "informational") return "info";
  return "low";
};

// --- JSON tools -------------------------------------------------------------
for (const f of ["gitleaks.json", "gitleaks-uncommitted.json"]) {
  const d = json(f); if (!Array.isArray(d)) continue;
  for (const x of d) add(f.replace(".json", ""), "high", x.RuleID, x.File, x.StartLine);   // value fields are never read
}
for (const f of ["semgrep.json", "semgrep-astro.json"]) {
  const d = json(f); if (!d || !Array.isArray(d.results)) continue;
  for (const r of d.results) {
    let file = norm(r.path);
    const m = file.match(/astro-extract\/(.*?)(\.script)?\.ts$/);   // map extracted code back to the .astro file
    if (m) file = m[1];
    add(f.replace(".json", ""), sev(r.extra && r.extra.severity), String(r.check_id || "").split(".").pop(), file, r.start && r.start.line);
  }
}
{
  const d = json("zizmor.json");
  if (Array.isArray(d)) for (const x of d) {
    const l = (x.locations || [])[0] || {};
    const key = l.symbolic && l.symbolic.key && (l.symbolic.key.Local || l.symbolic.key);
    const file = (key && (key.given_path || key.verbatim_path)) || "";
    const row = l.concrete && l.concrete.location && l.concrete.location.start_point && l.concrete.location.start_point.row;
    add("zizmor", sev(x.determinations && x.determinations.severity), x.ident, file, row != null ? row + 1 : "");
  }
}
{
  const d = json("osv-scanner.json");
  if (d && Array.isArray(d.results)) for (const r of d.results) for (const p of r.packages || []) {
    const v = p.vulnerabilities || []; if (!v.length) continue;
    let top = 0;
    for (const g of p.groups || []) { const n = parseFloat(g.max_severity); if (n > top) top = n; }
    const s = top >= 9 ? "critical" : top >= 7 ? "high" : top >= 4 ? "medium" : top > 0 ? "low" : "medium";
    add("osv-scanner", s, `${p.package.name}@${p.package.version} (${v.length} advisories)`, r.source && r.source.path, "");
  }
}
for (const f of ["npm-audit.json", "npm-audit-shipped.json"]) {
  const d = json(f);
  if (d && d.vulnerabilities) for (const [name, v] of Object.entries(d.vulnerabilities)) add(f.replace(".json", ""), sev(v.severity), name, "package-lock.json", "");
}
{
  const d = json("eslint.json");
  if (Array.isArray(d)) for (const fl of d) for (const m of fl.messages || []) add("eslint", m.severity === 2 ? "medium" : "low", m.ruleId || "parse-error", fl.filePath, m.line);
}
// --- Text tools -------------------------------------------------------------
{
  const t = read("tsc.txt");
  if (t) for (const l of t.split(/\r?\n/)) { const m = l.match(/^(.+?)\((\d+),\d+\): error (TS\d+)/); if (m) add("tsc", "medium", m[3], m[1], m[2]); }
}
{
  const t = read("lizard.txt");
  if (t) for (const l of t.split(/\r?\n/)) { const m = l.match(/^(.+?):(\d+): warning: (\S+) has/); if (m) add("lizard", "low", "complex-or-long-function:" + m[3], m[1], m[2]); }
}
const TEXT = ["release-checks", "astro-set-html", "exposed-keys", "env-files", "supabase-rls", "firebase-rules", "supabase-service-role", "live-site"];
for (const name of TEXT) {
  const t = read(name + ".txt"); if (!t) continue;
  for (const l of t.split(/\r?\n/)) {
    if (!l.trim()) continue;
    const loc = l.match(/([A-Za-z0-9_@./\\()\[\]-]+\.[A-Za-z0-9]+|Dockerfile[^\s:]*)(?::(\d+))?\s*$/) || l.match(/([A-Za-z0-9_@./\\-]+\.[A-Za-z0-9]+):(\d+)/);
    const head = l.replace(/^(FAIL|WARN)\s+/, "");
    const rule = head.split(/[:(]/)[0].trim().slice(0, 40) || name;
    let s = /^FAIL/.test(l) ? "high" : /^WARN/.test(l) ? "medium" : (/COMMITTED TO GIT|CLIENT-VISIBLE|OPEN TO EVERYONE|service.role/i.test(l) ? "high" : "medium");
    add(name, s, rule, loc ? loc[1] : "", loc && loc[2] ? loc[2] : "");
  }
}

// --- Output -----------------------------------------------------------------
const all = [...found.values()].sort((a, b) => (SEV_ORDER[a.severity] - SEV_ORDER[b.severity]) || a.source.localeCompare(b.source) || a.file.localeCompare(b.file));
fs.writeFileSync(path.join(dir, "findings.tsv"),
  "id\tsource\tseverity\trule\tfile\tline\tcount\n" + all.map((f) => [f.id, f.source, f.severity, f.rule, f.file, f.line, f.count].join("\t")).join("\n") + (all.length ? "\n" : ""));

const manifest = (read("manifest.tsv") || "").split(/\r?\n/).slice(1).filter(Boolean).map((l) => l.split("\t"));
const bySev = {}; for (const f of all) bySev[f.severity] = (bySev[f.severity] || 0) + 1;
const out = [];
out.push(`DIGEST of ${path.basename(dir)}`);
out.push(`${all.length} distinct findings` + (all.length ? ": " + ["critical", "high", "medium", "low", "info"].filter((s) => bySev[s]).map((s) => `${bySev[s]} ${s}`).join(", ") : ""));
out.push("(IDs are stable between runs. Open the file and line before calling anything confirmed. No secret values appear here.)");
out.push("");
out.push("NEEDS ATTENTION FIRST (critical and high, up to 30):");
const top = all.filter((f) => f.severity === "critical" || f.severity === "high").slice(0, 30);
for (const f of top) out.push(`  ${f.id}  ${f.severity.padEnd(8)} ${f.source.padEnd(22)} ${f.rule}  ${f.file}${f.line ? ":" + f.line : ""}${f.count > 1 ? `  (x${f.count})` : ""}`);
if (!top.length) out.push("  none");
out.push("");
const perFile = new Map();
for (const f of all) if (f.file) { const s = perFile.get(f.file) || new Set(); s.add(f.source); perFile.set(f.file, s); }
const multi = [...perFile.entries()].filter(([, s]) => s.size > 1).sort((a, b) => b[1].size - a[1].size).slice(0, 10);
out.push("FILES FLAGGED BY MORE THAN ONE TOOL (read these first):");
for (const [file, s] of multi) out.push(`  ${file}  <- ${[...s].join(", ")}`);
if (!multi.length) out.push("  none");
out.push("");
out.push("BY TOOL (status from manifest.tsv, findings counted here):");
const counts = {}; for (const f of all) counts[f.source] = (counts[f.source] || 0) + 1;
for (const [tool, status] of manifest) out.push(`  ${tool.padEnd(24)} ${String(status).slice(0, 70).padEnd(70)} ${counts[tool] != null ? counts[tool] + " finding(s)" : ""}`);
out.push("");
out.push("NOT FULLY COVERED:");
const gaps = manifest.filter(([, st]) => /^(failed-to-run|timeout|skipped|unavailable|partial)/.test(st));
for (const [tool, status] of gaps) out.push(`  ${tool}: ${status}`);
if (!gaps.length) out.push("  nothing");
fs.writeFileSync(path.join(dir, "digest.txt"), out.join("\n") + "\n");
console.log(`digest: ${all.length} findings -> findings.tsv, digest.txt`);
