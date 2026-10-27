"""Risky code patterns in any language Semgrep supports (Semgrep Community Edition, free rules).
Note: the free edition analyses one file at a time; data passed between files isn't traced.

Semgrep has no rules for .astro files, so it opens them and finds nothing. The TypeScript at the top of
each .astro file (between the two --- lines) and its <script> blocks are copied into temporary .ts files,
with every other line blanked so line numbers stay the same, and scanned instead. The project is never
touched. Also flags set:html, Astro's way of writing raw HTML into a page (the same risk as React's
dangerouslySetInnerHTML)."""
import os
import re
import shutil
import tempfile

from audit_core import json_load, json_looking, posix, read_text

NAME = "15-code-security"

SET_HTML = re.compile(r"set:html=\{\s*[^\"'`\s}]")
SCRIPT_SKIP = re.compile(r'type="?(application/ld\+json|application/json|text/template)')


def applies(ctx):
    return True


def tools(ctx):
    return ["semgrep"]


def run(ctx):
    ctx.dim = "security"
    if not ctx.has("semgrep"):
        ctx.skip("semgrep", "not installed (%s)" % ctx.install_hint("semgrep"))
        ctx.skip("semgrep-coverage", "semgrep not installed")
        astro_security(ctx)
        return
    ctx.note_version("semgrep", ctx.run_text(["semgrep", "--version"]))
    # Semgrep exits 0 even when it finds things, so decide by the results list. "audit" is our own results folder.
    ctx.run("semgrep", "semgrep.json", ["semgrep", "scan", "--config", "p/default", "--json", "--quiet", "--metrics=off", "--exclude", "audit", "."],
            json=True, empty=r'"results": *\[ *\]')

    # Files Semgrep couldn't parse or scan are silently missing from "results".
    path = ctx.path("semgrep.json")
    if json_looking(path):
        data = json_load(path) or {}
        errors = len(data.get("errors") or [])
        scanned = len((data.get("paths") or {}).get("scanned") or [])
        ctx.meta("semgrep_files_scanned=%d" % scanned)
        if errors > 0:
            ctx.record("semgrep-coverage", "partial: %d error(s), some files not fully scanned (see errors in semgrep.json)" % errors, "-", "semgrep.json")
        else:
            ctx.record("semgrep-coverage", "clean", "-", "semgrep.json")
    astro_security(ctx)


def extract_top(lines):
    """The TypeScript between the two --- lines at the top of an .astro file; every other line blank."""
    out, inside = [], False
    for i, line in enumerate(lines):
        if i == 0 and re.match(r"^---\s*$", line):
            inside = True
            out.append("")
        elif inside and re.match(r"^---\s*$", line):
            inside = False
            out.append("")
        else:
            out.append(line if inside else "")
    return out


def extract_scripts(lines):
    """The contents of <script> blocks (not JSON ones); every other line blank."""
    out, inside, skip = [], False, False
    for line in lines:
        res = ""
        if not inside:
            m = re.search(r"<script[^>]*>", line)
            if m:
                tag, rest = m.group(0), line[m.end():]
                skip = bool(SCRIPT_SKIP.search(tag) or "set:html" in tag)
                end = rest.find("</script>")
                if end >= 0:
                    res = "" if skip else rest[:end]
                else:
                    inside = True
                    res = "" if skip else rest
        else:
            end = line.find("</script>")
            if end >= 0:
                res = "" if skip else line[:end]
                inside = False
            elif not skip:
                res = line
        out.append(res)
    return out


def astro_security(ctx):
    files = [f for f in ctx.project_files() if f.endswith(".astro")]
    if not files:
        return

    # 1. set:html with anything other than a plain string
    hits = set()
    for f in files:
        for n, line in enumerate(read_text(os.path.join(ctx.root, f)).splitlines(), 1):
            if SET_HTML.search(line) and "JSON.stringify" not in line:
                hits.add("%s:%d" % (f, n))
    ctx.write("astro-set-html.txt", "".join(
        "WARN  ASTRO-SET-HTML: raw HTML written into the page; make sure the value can never contain visitor input: %s\n" % h
        for h in sorted(hits)[:20]))
    ctx.result("astro-set-html", "astro-set-html.txt")

    # 2. Semgrep on the extracted code
    if not ctx.has("semgrep"):
        ctx.skip("semgrep-astro", "not installed (%s)" % ctx.install_hint("semgrep"))
        return
    # The copies go in a temporary folder, not in audit/: tsc and ESLint would otherwise pick them up on the next run
    tmp = tempfile.mkdtemp(prefix="astroextract")
    extract = os.path.join(tmp, "astro-extract")
    made, count = 0, 0
    try:
        for f in files:
            src = os.path.join(ctx.root, f)
            if not os.path.isfile(src):
                continue
            lines = read_text(src).split("\n")
            dest = os.path.join(extract, f)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            for suffix, part in ((".ts", extract_top(lines)), (".script.ts", extract_scripts(lines))):
                if any(ln.strip() for ln in part):
                    with open(dest + suffix, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write("\n".join(part))
                    made += 1
            count += 1
        if not made:
            return
        ctx.run("semgrep-astro", "semgrep-astro.json",
                ["semgrep", "scan", "--config", "p/default", "--json", "--quiet", "--metrics=off", "--no-git-ignore", extract],
                json=True, empty=r'"results": *\[ *\]')
        # Findings in the original file names, for the report
        data = json_load(ctx.path("semgrep-astro.json")) if json_looking(ctx.path("semgrep-astro.json")) else None
        if data is not None:
            lines = []
            for r in data.get("results") or []:
                rel = posix(r.get("path", ""))
                rel = rel.split("astro-extract/", 1)[-1]
                rule = str(r.get("check_id", "")).split(".")[-1]
                line = (r.get("start") or {}).get("line")
                if ".astro.script.ts" in rel:
                    lines.append("%s:%s %s (in a <script> block)" % (rel.replace(".astro.script.ts", ".astro"), line, rule))
                else:
                    lines.append("%s:%s %s" % (rel.replace(".astro.ts", ".astro"), line, rule))
            ctx.write("astro-findings.txt", "".join(ln + "\n" for ln in lines))
        ctx.meta("astro_files_extracted=%d" % count)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
