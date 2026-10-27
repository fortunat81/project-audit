#!/usr/bin/env python3
"""The live progress page (progress.html in the run folder).

It is a small, self-contained page that refreshes itself every few seconds. While the scan runs it lists the checks
done so far; when the scan is over it says Claude is checking the findings and writing the report; once the written
report exists (AUDIT.md) it turns into a redirect to report.html, so one open browser tab goes from progress to the
full report without any server. Standard library only."""
import html
import os
import sys

REFRESH = 3

TEXT = {
    "scanning": ("Scanning your project", "The scanners are running. This page updates by itself."),
    "review": ("Scan finished: Claude is writing the report",
               "Claude is checking the findings and writing the report. This page switches to the full report by itself."),
}


def state_for(folder):
    """scanning, review (scan over, report not written yet) or done (AUDIT.md exists)."""
    if os.path.isfile(os.path.join(folder, "AUDIT.md")):
        return "done"
    if os.path.isfile(os.path.join(folder, "coverage.txt")):
        return "review"
    return "scanning"


def _rows(folder):
    try:
        with open(os.path.join(folder, "manifest.tsv"), encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()[1:]
    except OSError:
        return []
    return [ln.split("\t") for ln in lines if ln]


def _mark(status):
    if status in ("clean", "done"):
        return "ok", "clean"
    if status == "findings":
        return "warn", "findings"
    if status.startswith(("skipped", "unavailable")):
        return "skip", status
    return "bad", status


def page(folder, state):
    if state == "done":
        return ('<!doctype html><html><head><meta charset="utf-8"><title>Audit report</title>'
                '<meta http-equiv="refresh" content="0;url=report.html"></head>'
                '<body><p>Report ready: <a href="report.html">open report.html</a></p></body></html>\n')
    title, note = TEXT[state]
    rows = _rows(folder)
    items = []
    for r in rows:
        cls, label = _mark(r[1] if len(r) > 1 else "")
        items.append('<tr class="%s"><td>%s</td><td>%s</td></tr>' % (cls, html.escape(r[0]), html.escape(label)))
    if not items:
        items.append('<tr><td colspan="2">Starting up...</td></tr>')
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="%d">
<title>Audit in progress</title>
<style>
:root { --bg:#fff; --fg:#1b1f24; --mut:#5b6573; --ok:#1a7f37; --warn:#b35900; --bad:#c62828; --line:#d8dde3; }
@media (prefers-color-scheme: dark) { :root { --bg:#14181d; --fg:#e6e9ed; --mut:#9aa5b1; --ok:#4cc26b; --warn:#f0a050; --bad:#ff6b6b; --line:#2c333b; } }
body { background:var(--bg); color:var(--fg); font:16px/1.5 system-ui,sans-serif; margin:0; padding:24px 16px; }
main { max-width:720px; margin:0 auto; }
h1 { font-size:1.4rem; margin:0 0 4px; } p { color:var(--mut); margin:0 0 16px; }
table { width:100%%; border-collapse:collapse; } td { padding:6px 8px; border-bottom:1px solid var(--line); }
tr.ok td:last-child { color:var(--ok); } tr.warn td:last-child { color:var(--warn); } tr.bad td:last-child { color:var(--bad); } tr.skip td:last-child { color:var(--mut); }
</style></head>
<body><main>
<h1>%s</h1>
<p>%s</p>
<p>%d checks finished so far.</p>
<table>%s</table>
</main></body></html>
""" % (REFRESH, html.escape(title), html.escape(note), len(rows), "\n".join(items))


def write(folder, state=None):
    """Writes progress.html for the run folder. Never raises: a progress page must not stop a scan."""
    try:
        state = state or state_for(folder)
        with open(os.path.join(folder, "progress.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(folder, state))
    except Exception:
        pass


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        sys.stderr.write("usage: audit_progress.py <audit-run-folder>\n")
        return 1
    write(argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
