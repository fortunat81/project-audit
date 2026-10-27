#!/usr/bin/env python3
"""Tests for small pure helpers: the live-site header and address rules, the Markdown renderer behind the
report page, and the digest text. Prints 'OK: label' or 'BAD: label | detail' per check."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(SCRIPTS, "audit_checks"))
import audit_digest       # noqa: E402
import audit_report_html  # noqa: E402
import audit_scan         # noqa: E402
import m80_live_site      # noqa: E402


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def live_site():
    full = ["strict-transport-security: max-age=1", "content-security-policy: default-src 'self'; frame-ancestors 'none'",
            "x-content-type-options: nosniff", "referrer-policy: no-referrer", "server: nginx"]
    out = m80_live_site.header_lines(full)
    say(sum(1 for ln in out if ln.startswith("OK")) == 5 and not any(ln.startswith("WARN") for ln in out), "a site with all the headers gets no warnings", out)
    say("INFO reveals: server: nginx" in out, "a server banner is reported as information")
    out = m80_live_site.header_lines([])
    say(sum(1 for ln in out if ln.startswith("WARN")) == 5, "a site with no headers gets five warnings (four headers and clickjacking)", out)
    out = m80_live_site.header_lines(["x-frame-options: deny"])
    say("OK   clickjacking protection (x-frame-options or frame-ancestors)" in out, "x-frame-options alone counts as clickjacking protection")

    u = m80_live_site.script_url
    base = ("https", "example.com", "https://example.com")
    say(u("https://cdn.x.com/a.js?v=2", *base) == "https://cdn.x.com/a.js", "a full address keeps its host and loses its query string")
    say(u("//cdn.x.com/a.js", *base) == "https://cdn.x.com/a.js", "a protocol-relative address takes the site's scheme")
    say(u("/static/a.js", *base) == "https://example.com/static/a.js", "a root-relative address takes the site's host")
    say(u("a.js", *base) == "https://example.com/a.js", "a relative address is added to the site address")


def markdown():
    r = audit_report_html.render_markdown
    say(r("# Title") == "<h2>Title</h2>", "a heading starts one level lower (the page has its own h1)", r("# Title"))
    say(r("one\ntwo\n\nthree") == "<p>one two</p>\n<p>three</p>", "lines join into paragraphs, a blank line starts the next", r("one\ntwo\n\nthree"))
    say("<script>" not in r("<script>alert(1)</script>"), "HTML in the text is escaped")
    say("href" not in r("[x](javascript:alert(1))"), "a javascript: link is not turned into a link", r("[x](javascript:alert(1))"))
    say('href="https://a.com"' in r("[x](https://a.com)"), "a normal link becomes a link")
    say(r("- a\n- b") == "<ul><li>a</li><li>b</li></ul>", "dashes make a list", r("- a\n- b"))
    say(r("1. a\n2. b").startswith("<ol>"), "numbers make an ordered list")
    say("<li>a wrapped &middot; nested</li>" in r("- a\n  wrapped\n  - nested") or "a wrapped" in r("- a\n  wrapped\n  - nested"), "a wrapped line stays in its item", r("- a\n  wrapped\n  - nested"))
    table = r("| a | b |\n|---|---|\n| 1 | 2 |")
    say("<th>a</th><th>b</th>" in table and "<td>1</td><td>2</td>" in table, "a table has a header row and body rows", table)
    say(r("```\n<b>\n```") == "<pre><code>&lt;b&gt;</code></pre>", "code blocks are shown as text", r("```\n<b>\n```"))
    say(r("> a\n> b") == "<blockquote>a b</blockquote>", "quote lines join into one quote")
    say(r("text\n---\nmore") == "<p>text</p>\n<hr>\n<p>more</p>", "three dashes make a rule and end the paragraph", r("text\n---\nmore"))
    say(r("a\r\nb") == "<p>a b</p>", "Windows line endings read the same")


def digest():
    findings = [
        {"id": "F-1", "source": "semgrep", "severity": "high", "rule": "r1", "file": "a.js", "line": 3, "count": 2},
        {"id": "F-2", "source": "eslint", "severity": "low", "rule": "r2", "file": "a.js", "line": "", "count": 1},
    ]
    manifest = [("semgrep", "findings"), ("eslint", "findings"), ("knip", "skipped: not installed"), ("gitleaks", "clean")]
    lines = audit_digest._digest_lines(os.path.join("x", "2026-01-01_000000"), findings, manifest)
    text = "\n".join(lines)
    say(lines[0] == "DIGEST of 2026-01-01_000000" and "2 distinct findings: 1 high, 1 low" in text, "the digest names the run and counts findings by severity", lines[:3])
    say("F-1  high     semgrep" in text and "a.js:3  (x2)" in text, "a high finding is listed first with its line and repeat count", text)
    say("a.js  <- eslint, semgrep" in text, "a file flagged by two tools is listed")
    say("knip: skipped: not installed" in text and "gitleaks:" not in text.split("NOT FULLY COVERED:")[1], "only the tools that did not fully run are listed as gaps")
    lines = audit_digest._digest_lines("run", [], [("gitleaks", "clean")])
    text = "\n".join(lines)
    say("0 distinct findings" in text and text.count("  none") == 2 and "  nothing" in text, "an empty result says none and nothing", text)
    folder = tempfile.mkdtemp(prefix="digest")
    audit_digest.write_outputs(folder, findings, manifest)
    say(os.path.isfile(os.path.join(folder, "findings.tsv")) and os.path.isfile(os.path.join(folder, "digest.txt")), "both output files are written")


def coverage():
    b = audit_scan.status_bucket
    say([b(x) for x in ("clean", "findings", "done", "timeout")] == ["clean", "findings", "done", "timeout"], "plain statuses count in their own column")
    say(b("failed-to-run (could not reach)") == "failed" and b("partial: left out") == "partial", "failed and partial statuses count by their start")
    say(b("skipped: not installed") == "skipped" and b("unavailable") == "skipped" and b("anything else") == "skipped", "skipped, unavailable and unknown statuses count as skipped")
    rows = [["a", "clean"], ["b", "findings"], ["c", "failed-to-run (x)"], ["d", "skipped: y"], ["e", "timeout"], ["f", "partial: z"], ["g", "done"]]
    lines = audit_scan.coverage_lines(rows, "go(5)")
    say(lines[0] == "COVERAGE: 7 checks: 1 clean, 1 with findings, 1 measured, 1 partial, 1 failed, 1 timed out, 1 skipped/unavailable", "the coverage line counts every column", lines[0])
    say(sum(1 for ln in lines if ln.startswith("  - ")) == 4 and "INCOMPLETE" in lines[1], "the checks that did not fully run are listed", lines)
    say(lines[-1].startswith("NO DEDICATED CHECKS for: go(5)"), "languages with no dedicated checks are named last", lines[-1])
    lines = audit_scan.coverage_lines([["a", "clean"]], "")
    say(len(lines) == 1, "a fully clean run has just the one line", lines)


def severity_matches_checklists():
    """The scan's own severity must agree with the Supabase checklist (reviews/supabase.md):
    a table with no row-level security is critical, an open write policy is high."""
    run = tempfile.mkdtemp(prefix="sev")
    text = "\n".join([
        "NO RLS: table 'bookings' is created in a migration but never gets 'enable row level security'",
        'REVIEW open policy: supabase/migrations/001.sql:12:create policy "anyone can insert" on bookings for insert with check (true);',
        'REVIEW open policy: supabase/migrations/002.sql:5:create policy "public read" on posts for select using (true);',
        'REVIEW open policy: supabase/migrations/003.sql:3:create policy "public read" on tags for select using (true);',
        'REVIEW open policy: supabase/migrations/003.sql:9:create policy "anyone can update" on tags for update using (true);',
    ]) + "\n"
    with open(os.path.join(run, "supabase-rls.txt"), "w", newline="\n") as f:
        f.write(text)
    found = audit_digest.Collector(run).collect()
    sev = {(x["rule"], x["file"]): x["severity"] for x in found}
    say(sev.get(("NO RLS", "")) == "critical", "a table with no row-level security is critical", sev)
    say(sev.get(("REVIEW open policy", "supabase/migrations/001.sql")) == "high", "an open insert policy is high", sev)
    say(sev.get(("REVIEW open policy", "supabase/migrations/002.sql")) == "medium", "an open read-only policy stays medium", sev)
    say(sev.get(("REVIEW open policy", "supabase/migrations/003.sql")) == "high", "when one file has a read policy and a write policy, the file is high", sev)


if __name__ == "__main__":
    live_site()
    markdown()
    digest()
    coverage()
    severity_matches_checklists()
