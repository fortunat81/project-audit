#!/usr/bin/env python3
"""Builds one self-contained web page (report.html) for an audit run, to open in any browser.

    python audit_report_html.py <audit-run-folder>

Shows the verdict, the findings (filter by severity, tool or text), what was and was not covered,
the scores, the launch checklist and the written report. One file, no internet, no installs. It uses
only files already in the run folder and never reads project source, so it cannot show a secret
value. Everything shown is escaped. Standard library only (Python 3.8+).
"""
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_digest    # noqa: E402
import audit_verdict   # noqa: E402

SEVERITIES = ["critical", "high", "medium", "low", "info"]


def read(folder, name):
    try:
        with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def read_meta(folder):
    meta = {}
    for line in (read(folder, "meta.txt") or "").splitlines():
        k, _, v = line.partition("=")
        if k:
            meta[k] = v
    return meta


def read_findings(folder):
    text = read(folder, "findings.tsv")
    if text is None:   # the digest was not built; build the list now
        return audit_digest.Collector(folder).collect()
    rows = []
    for line in text.splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 7:
            rows.append({"id": p[0], "source": p[1], "severity": p[2], "rule": p[3], "file": p[4], "line": p[5],
                         "count": int(p[6]) if p[6].isdigit() else 1})
    return rows


def read_checklist(report_text):
    rows = []
    for line in (report_text or "").splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|(.*)$", line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        mark = audit_verdict.mark_from_cell(cells[1]) if len(cells) > 1 else None
        if mark:
            rows.append({"n": int(m.group(1)), "group": audit_verdict.group_of(int(m.group(1))), "item": cells[0],
                         "mark": cells[1], "by": cells[2] if len(cells) > 2 else "", "evidence": cells[3] if len(cells) > 3 else ""})
    return rows


def status_class(status):
    s = status.split(":")[0].strip()
    return {"clean": "ok", "done": "ok", "findings": "find", "partial": "warn", "skipped": "skip", "unavailable": "skip",
            "failed-to-run": "bad", "timeout": "bad"}.get(s, "skip")


def build(folder):
    meta = read_meta(folder)
    findings = read_findings(folder)
    manifest = []
    for line in (read(folder, "manifest.tsv") or "").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 2 and p[0]:
            manifest.append({"tool": p[0], "status": p[1], "dimension": p[4] if len(p) > 4 else ""})
    scores = None
    try:
        scores = json.loads(read(folder, "scores.json") or "")
    except ValueError:
        pass
    report_text = read(folder, "AUDIT.md")
    checklist = read_checklist(report_text)

    verdict = None
    if isinstance(scores, dict) and scores.get("verdict") in audit_verdict.VERDICT_TEXT:
        verdict = scores["verdict"]
    project = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(folder)))) or "project"

    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    cover = {"ok": 0, "find": 0, "warn": 0, "bad": 0, "skip": 0}
    for m in manifest:
        cover[status_class(m["status"])] += 1

    data = {"findings": findings, "manifest": manifest, "checklist": checklist}
    data_json = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    esc = html.escape

    notices = []
    if meta.get("consistent") == "no":
        notices.append("The project changed while the scan was running, so the results may mix two versions. Scan again.")
    if meta.get("untrusted") == "yes":
        notices.append("Untrusted mode: checks that run the project's own code were skipped (see Coverage).")
    gaps = [m for m in manifest if status_class(m["status"]) in ("bad", "skip", "warn")]
    if gaps:
        notices.append("%d check(s) did not run fully, so a clean result does not cover them." % len(gaps))

    verdict_html = ""
    if verdict:
        verdict_html = '<div class="verdict v-%s"><span>%s</span> Level %s, %s audit</div>' % (
            verdict, esc(audit_verdict.VERDICT_TEXT[verdict]), esc(str(scores.get("level", "?"))), esc(str(scores.get("mode", "?"))))
    else:
        verdict_html = '<div class="verdict v-none"><span>No written verdict yet</span> This page shows the scan results only.</div>'

    score_html = ""
    if isinstance(scores, dict) and isinstance(scores.get("scores"), dict):
        bars = []
        for name, value in scores["scores"].items():
            conf = (scores.get("confidence") or {}).get(name, "")
            if value is None:
                bars.append('<div class="bar"><b>%s</b><i>not assessed</i></div>' % esc(name.title()))
            else:
                bars.append('<div class="bar"><b>%s</b><div class="track"><div class="fill" style="width:%d%%"></div></div><i>%d%s</i></div>'
                            % (esc(name.title()), max(0, min(100, int(value))), int(value), (" (%s)" % esc(str(conf))) if conf else ""))
        score_html = '<section><h2>Scores</h2><div class="bars">%s</div></section>' % "".join(bars)

    cover_rows = "".join('<tr class="c-%s"><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        status_class(m["status"]), esc(m["tool"]), esc(m["status"]), esc(m["dimension"])) for m in manifest)

    report_block = ""
    if report_text:
        report_block = '<section><h2>Written report</h2><details open><summary>AUDIT.md</summary><pre class="report">%s</pre></details></section>' % esc(report_text)

    page = PAGE.replace("{{TITLE}}", esc("Audit: " + project)) \
        .replace("{{PROJECT}}", esc(project)) \
        .replace("{{META}}", esc("%s, commit %s, branch %s" % (meta.get("date", ""), meta.get("commit", "none")[:8], meta.get("branch", "none")))) \
        .replace("{{VERDICT}}", verdict_html) \
        .replace("{{NOTICES}}", "".join('<div class="notice">%s</div>' % esc(n) for n in notices)) \
        .replace("{{CARDS}}", "".join('<div class="card s-%s"><b>%d</b><span>%s</span></div>' % (s, counts[s], s) for s in SEVERITIES)
                 + '<div class="card s-cover"><b>%d / %d</b><span>checks ran fully</span></div>' % (cover["ok"] + cover["find"], len(manifest))) \
        .replace("{{SCORES}}", score_html) \
        .replace("{{COVERAGE}}", cover_rows) \
        .replace("{{REPORT}}", report_block) \
        .replace("{{DATA}}", data_json)
    return page


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f6f7f9;--panel:#fff;--text:#1c2330;--muted:#5d6878;--line:#e1e5eb;--accent:#2f5bd8;
--critical:#b3122b;--high:#d4380d;--medium:#b7791f;--low:#3b6fb6;--info:#6b7788;
--ok:#1f8a4c;--warn:#b7791f;--bad:#b3122b;--skip:#6b7788;--find:#d4380d}
@media (prefers-color-scheme: dark){:root{--bg:#12151b;--panel:#1b2029;--text:#e6e9ef;--muted:#9aa5b5;--line:#2c3441;--accent:#7ea2ff;
--critical:#ff6b81;--high:#ff8a5c;--medium:#e6b450;--low:#7ea2ff;--info:#9aa5b5;--ok:#4cc38a;--warn:#e6b450;--bad:#ff6b81;--skip:#9aa5b5;--find:#ff8a5c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{margin:0;font-size:1.5rem} h2{font-size:1.1rem;margin:0 0 12px}
.sub{color:var(--muted);margin:2px 0 16px}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0;overflow-x:auto}
.verdict{border-radius:10px;padding:14px 16px;margin:12px 0;border:1px solid var(--line);background:var(--panel)}
.verdict span{font-weight:700;font-size:1.15rem;margin-right:8px}
.v-dont-launch{border-left:6px solid var(--critical)} .v-launch-with-limits{border-left:6px solid var(--medium)}
.v-no-blocking-problems{border-left:6px solid var(--ok)} .v-none{border-left:6px solid var(--info)}
.notice{border:1px solid var(--medium);border-radius:8px;padding:8px 12px;margin:8px 0;background:var(--panel)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin:12px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.card b{display:block;font-size:1.5rem} .card span{color:var(--muted);text-transform:capitalize;font-size:.85rem}
.s-critical b{color:var(--critical)} .s-high b{color:var(--high)} .s-medium b{color:var(--medium)} .s-low b{color:var(--low)} .s-info b{color:var(--info)}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px}
.filters label{display:inline-flex;gap:4px;align-items:center;cursor:pointer}
input[type=search],select{background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit}
table{border-collapse:collapse;width:100%} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.85rem;cursor:pointer;white-space:nowrap}
td.file{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem;word-break:break-all}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.78rem;font-weight:600;color:#fff}
.p-critical{background:var(--critical)} .p-high{background:var(--high)} .p-medium{background:var(--medium)} .p-low{background:var(--low)} .p-info{background:var(--info)}
.c-ok td:nth-child(2){color:var(--ok)} .c-find td:nth-child(2){color:var(--find)} .c-warn td:nth-child(2){color:var(--warn)}
.c-bad td:nth-child(2){color:var(--bad);font-weight:600} .c-skip td:nth-child(2){color:var(--skip)}
.bars{display:grid;gap:8px} .bar{display:grid;grid-template-columns:150px 1fr 120px;gap:10px;align-items:center}
.track{background:var(--line);border-radius:6px;height:10px} .fill{background:var(--accent);height:10px;border-radius:6px}
.bar i{color:var(--muted);font-style:normal}
pre.report{white-space:pre-wrap;word-break:break-word;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace;margin:8px 0 0}
.muted{color:var(--muted)} .empty{padding:12px;color:var(--muted)}
@media (max-width:600px){.bar{grid-template-columns:1fr}}
</style>
</head>
<body>
<main>
<h1>{{PROJECT}}</h1>
<p class="sub">{{META}}</p>
{{VERDICT}}
{{NOTICES}}
<div class="cards">{{CARDS}}</div>

<section>
<h2>Findings</h2>
<div class="filters" id="filters">
 <label><input type="checkbox" data-sev="critical" checked> Critical</label>
 <label><input type="checkbox" data-sev="high" checked> High</label>
 <label><input type="checkbox" data-sev="medium" checked> Medium</label>
 <label><input type="checkbox" data-sev="low" checked> Low</label>
 <label><input type="checkbox" data-sev="info" checked> Info</label>
 <select id="source"><option value="">All tools</option></select>
 <input type="search" id="q" placeholder="Search file, rule or ID" size="28">
 <span class="muted" id="count"></span>
</div>
<table id="findings"><thead><tr><th data-k="severity">Severity</th><th data-k="id">ID</th><th data-k="source">Tool</th><th data-k="rule">What</th><th data-k="file">Where</th></tr></thead><tbody></tbody></table>
<div class="empty" id="none" hidden>No findings match.</div>
<p class="muted">Open the file and line before treating anything as confirmed. IDs stay the same between runs. No secret values are ever shown here.</p>
</section>

<section>
<h2>What was checked</h2>
<table><thead><tr><th>Check</th><th>Result</th><th>Feeds</th></tr></thead><tbody>{{COVERAGE}}</tbody></table>
</section>

{{SCORES}}

<section id="checklist-section" hidden>
<h2>Launch checklist</h2>
<table id="checklist"><thead><tr><th>#</th><th>Item</th><th>Mark</th><th>Checked by</th><th>Evidence</th></tr></thead><tbody></tbody></table>
</section>

{{REPORT}}
</main>
<script type="application/json" id="data">{{DATA}}</script>
<script>
(function(){
 var data=JSON.parse(document.getElementById('data').textContent);
 var order={critical:0,high:1,medium:2,low:3,info:4}, sortKey='severity', sortDir=1;
 var body=document.querySelector('#findings tbody'), none=document.getElementById('none'), count=document.getElementById('count');
 var q=document.getElementById('q'), src=document.getElementById('source');
 var sources=Array.from(new Set(data.findings.map(function(f){return f.source}))).sort();
 sources.forEach(function(s){var o=document.createElement('option');o.value=s;o.textContent=s;src.appendChild(o)});
 function cell(tr,text,cls){var td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;tr.appendChild(td);return td}
 function render(){
  var on={};document.querySelectorAll('#filters input[data-sev]').forEach(function(c){on[c.dataset.sev]=c.checked});
  var term=q.value.toLowerCase(), s=src.value;
  var rows=data.findings.filter(function(f){
   return on[f.severity]&&(!s||f.source===s)&&(!term||(f.file+' '+f.rule+' '+f.id+' '+f.source).toLowerCase().indexOf(term)>=0)});
  rows.sort(function(a,b){
   var x=sortKey==='severity'?order[a.severity]:String(a[sortKey]), y=sortKey==='severity'?order[b.severity]:String(b[sortKey]);
   return (x<y?-1:x>y?1:0)*sortDir});
  body.textContent='';
  rows.forEach(function(f){
   var tr=document.createElement('tr'), td=document.createElement('td'), p=document.createElement('span');
   p.className='pill p-'+f.severity;p.textContent=f.severity;td.appendChild(p);tr.appendChild(td);
   cell(tr,f.id);cell(tr,f.source);cell(tr,f.rule+(f.count>1?'  (x'+f.count+')':''));
   cell(tr,f.file+(f.line!==''&&f.line!=null?':'+f.line:''),'file');
   body.appendChild(tr)});
  count.textContent=rows.length+' of '+data.findings.length+' shown';
  none.hidden=rows.length>0;
 }
 document.querySelectorAll('#filters input[data-sev]').forEach(function(c){c.addEventListener('change',render)});
 q.addEventListener('input',render);src.addEventListener('change',render);
 document.querySelectorAll('#findings th').forEach(function(th){th.addEventListener('click',function(){
  var k=th.dataset.k; if(sortKey===k){sortDir=-sortDir}else{sortKey=k;sortDir=1} render()})});
 render();
 if(data.checklist.length){
  document.getElementById('checklist-section').hidden=false;
  var cb=document.querySelector('#checklist tbody');
  data.checklist.forEach(function(r){var tr=document.createElement('tr');
   cell(tr,String(r.n));cell(tr,r.item);cell(tr,r.mark);cell(tr,r.by);cell(tr,r.evidence);cb.appendChild(tr)});
 }
})();
</script>
</body>
</html>
"""


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        sys.stderr.write("usage: audit_report_html.py <audit-run-folder>\n")
        return 1
    page = build(argv[1])
    with open(os.path.join(argv[1], "report.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("report: %s" % os.path.join(argv[1], "report.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
