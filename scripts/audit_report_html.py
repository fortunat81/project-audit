#!/usr/bin/env python3
"""Builds one self-contained web page (report.html) for an audit run, to open in any browser.

    python audit_report_html.py <audit-run-folder>

Shows the verdict, the findings (filter by severity, tool or text), what was and was not covered,
the scores, the launch checklist, the proposed fixes (tick the ones you approve and copy them to
Claude) and the written report in a formatted view. English and French, light and dark.
One file, no internet, no installs. It uses only files already in the run folder and never reads
project source, so it cannot show a secret value. Everything shown is escaped.
Standard library only (Python 3.8+).
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

# Every label on the page, in both languages. The test suite checks both have the same keys.
I18N = {
    "en": {
        "lang_btn": "Français", "theme_light": "Light", "theme_dark": "Dark",
        "nav_summary": "Summary", "nav_findings": "Findings", "nav_fixes": "Fixes", "nav_checklist": "Checklist",
        "nav_coverage": "Coverage", "nav_report": "Report",
        "verdict_dont-launch": "Don't launch yet", "verdict_launch-with-limits": "Launch with limits",
        "verdict_no-blocking-problems": "No blocking problems found", "verdict_none": "No written verdict yet",
        "verdict_none_hint": "This page shows the scan results only.", "level": "Level", "audit": "audit",
        "quick": "quick", "full": "full",
        "sev_critical": "Critical", "sev_high": "High", "sev_medium": "Medium", "sev_low": "Low", "sev_info": "Info",
        "checks_ran": "checks ran fully", "findings": "Findings", "all_tools": "All tools", "search": "Search file, rule or ID",
        "shown": "shown", "of": "of", "no_match": "No findings match.",
        "th_severity": "Severity", "th_id": "ID", "th_tool": "Tool", "th_what": "What", "th_where": "Where",
        "findings_note": "Open the file and line before treating anything as confirmed. IDs stay the same between runs. No secret values are ever shown here.",
        "coverage": "What was checked", "th_check": "Check", "th_result": "Result", "th_feeds": "Feeds",
        "scores": "Scores", "not_assessed": "not assessed",
        "dim_architecture": "Architecture", "dim_modularity": "Modularity", "dim_spaghettiness": "Spaghettiness",
        "dim_security": "Security", "dim_quality": "Bugs and quality", "dim_scalability": "Scalability", "dim_documentation": "Documentation",
        "checklist": "Launch checklist", "th_n": "#", "th_item": "Item", "th_mark": "Mark", "th_by": "Checked by", "th_evidence": "Evidence",
        "fixes": "Proposed fixes", "fixes_intro": "Tick the fixes you approve, add a note if you want, then copy them to Claude. Nothing is changed until you send them.",
        "fixes_none": "No structured fixes were saved for this run (fixes.json).",
        "who_claude": "Claude can do this", "who_you": "You do this", "approve": "Approve", "myself": "I'll do this myself",
        "note": "Note for Claude (optional)", "why": "Why", "change": "The change", "verify": "How to check it worked", "risk": "Risk",
        "send_title": "Send to Claude", "selected": "selected", "copy": "Copy message", "copied": "Copied. Paste it into Claude.",
        "download": "Download approved-fixes.json", "select_all": "Select all", "clear": "Clear",
        "msg_head": "Please apply these approved fixes from the audit in", "msg_mine": "I will do these myself (no action for you, just note them)",
        "msg_rules": "Work one fix at a time on a new git branch, run the project's tests if it has any, then run the scan again and tell me the score change. Don't change anything I did not approve. If a fix turns out wrong, revert it and say so.",
        "msg_note": "Note", "msg_none": "Nothing is selected yet.",
        "report": "Written report", "formatted": "Formatted", "source": "Source", "no_report": "No written report yet. Ask Claude to write the audit report.",
        "n_gaps": "check(s) did not run fully, so a clean result does not cover them.",
        "n_inconsistent": "The project changed while the scan was running, so the results may mix two versions. Scan again.",
        "n_untrusted": "Untrusted mode: checks that run the project's own code were skipped (see Coverage).",
        "st_ok": "ran", "st_find": "findings", "st_warn": "partial", "st_bad": "failed", "st_skip": "skipped",
        "fix_btn": "Fix selected with Claude", "confirm_fix": "Claude Code will create a new git branch in your project and apply {n} fix(es), one commit each. It will not push or merge anything. Start?",
        "progress": "Claude's progress", "state_idle": "Not started", "state_running": "Claude is working...", "state_done": "Finished", "state_failed": "Stopped with an error",
        "server_hint": "To start Claude from this page, run: bash scan.sh --serve (in a terminal). Without it you can still copy the message or download the file.",
        "started": "Started. Progress appears below.", "report_ready": "The fix report was written: audit/{run}/fix-report.md", "log_empty": "Waiting for the first output...",
        "start_failed": "Could not start",
    },
    "fr": {
        "lang_btn": "English", "theme_light": "Clair", "theme_dark": "Sombre",
        "nav_summary": "Résumé", "nav_findings": "Constats", "nav_fixes": "Correctifs", "nav_checklist": "Liste de lancement",
        "nav_coverage": "Couverture", "nav_report": "Rapport",
        "verdict_dont-launch": "Ne pas lancer tout de suite", "verdict_launch-with-limits": "Lancement avec réserves",
        "verdict_no-blocking-problems": "Aucun problème bloquant trouvé", "verdict_none": "Pas encore de verdict écrit",
        "verdict_none_hint": "Cette page ne montre que les résultats de l'analyse.", "level": "Niveau", "audit": "audit",
        "quick": "rapide", "full": "complet",
        "sev_critical": "Critique", "sev_high": "Élevé", "sev_medium": "Moyen", "sev_low": "Faible", "sev_info": "Info",
        "checks_ran": "vérifications complètes", "findings": "Constats", "all_tools": "Tous les outils", "search": "Chercher un fichier, une règle ou un ID",
        "shown": "affichés", "of": "sur", "no_match": "Aucun constat ne correspond.",
        "th_severity": "Gravité", "th_id": "ID", "th_tool": "Outil", "th_what": "Quoi", "th_where": "Où",
        "findings_note": "Ouvrez le fichier et la ligne avant de considérer un constat comme confirmé. Les ID restent les mêmes d'une analyse à l'autre. Aucune valeur secrète n'est affichée ici.",
        "coverage": "Ce qui a été vérifié", "th_check": "Vérification", "th_result": "Résultat", "th_feeds": "Alimente",
        "scores": "Notes", "not_assessed": "non évalué",
        "dim_architecture": "Architecture", "dim_modularity": "Modularité", "dim_spaghettiness": "Code spaghetti", "dim_security": "Sécurité",
        "dim_quality": "Bogues et qualité", "dim_scalability": "Mise à l'échelle", "dim_documentation": "Documentation",
        "checklist": "Liste de contrôle avant lancement", "th_n": "#", "th_item": "Élément", "th_mark": "Résultat", "th_by": "Vérifié par", "th_evidence": "Preuve",
        "fixes": "Correctifs proposés", "fixes_intro": "Cochez les correctifs que vous approuvez, ajoutez une note si vous voulez, puis copiez-les vers Claude. Rien n'est modifié avant l'envoi.",
        "fixes_none": "Aucun correctif structuré n'a été enregistré pour cette analyse (fixes.json).",
        "who_claude": "Claude peut le faire", "who_you": "À faire par vous", "approve": "Approuver", "myself": "Je m'en occupe",
        "note": "Note pour Claude (facultatif)", "why": "Pourquoi", "change": "La modification", "verify": "Comment vérifier que ça marche", "risk": "Risque",
        "send_title": "Envoyer à Claude", "selected": "sélectionné(s)", "copy": "Copier le message", "copied": "Copié. Collez-le dans Claude.",
        "download": "Télécharger approved-fixes.json", "select_all": "Tout sélectionner", "clear": "Effacer",
        "msg_head": "Merci d'appliquer ces correctifs approuvés de l'audit dans", "msg_mine": "Je m'en occupe moi-même (rien à faire pour toi, juste les noter)",
        "msg_rules": "Travaille un correctif à la fois sur une nouvelle branche git, lance les tests du projet s'il y en a, relance l'analyse et dis-moi le changement de notes. Ne modifie rien que je n'ai pas approuvé. Si un correctif se révèle mauvais, annule-le et dis-le.",
        "msg_note": "Note", "msg_none": "Rien n'est sélectionné pour l'instant.",
        "report": "Rapport écrit", "formatted": "Mis en forme", "source": "Source", "no_report": "Pas encore de rapport écrit. Demandez à Claude de rédiger le rapport d'audit.",
        "n_gaps": "vérification(s) incomplète(s) : un résultat propre ne les couvre pas.",
        "n_inconsistent": "Le projet a changé pendant l'analyse : les résultats peuvent mélanger deux versions. Relancez l'analyse.",
        "n_untrusted": "Mode non fiable : les vérifications qui exécutent le code du projet ont été sautées (voir Couverture).",
        "st_ok": "exécuté", "st_find": "constats", "st_warn": "partiel", "st_bad": "échec", "st_skip": "ignoré",
        "fix_btn": "Corriger la sélection avec Claude", "confirm_fix": "Claude Code va créer une nouvelle branche git dans votre projet et appliquer {n} correctif(s), un commit chacun. Il ne publiera ni ne fusionnera rien. Démarrer ?",
        "progress": "Progression de Claude", "state_idle": "Pas démarré", "state_running": "Claude travaille...", "state_done": "Terminé", "state_failed": "Arrêté sur une erreur",
        "server_hint": "Pour lancer Claude depuis cette page, exécutez : bash scan.sh --serve (dans un terminal). Sans cela, vous pouvez quand même copier le message ou télécharger le fichier.",
        "started": "Démarré. La progression s'affiche ci-dessous.", "report_ready": "Le rapport de correction a été écrit : audit/{run}/fix-report.md", "log_empty": "En attente de la première sortie...",
        "start_failed": "Démarrage impossible",
    },
}

FIX_FIELDS = ("id", "title", "who")


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


def read_fixes(folder):
    """fixes.json: a list of proposed fixes written with the report. Returns (list, error)."""
    text = read(folder, "fixes.json")
    if text is None:
        return [], None
    try:
        data = json.loads(text)
    except ValueError:
        return [], "fixes.json is not valid JSON"
    if isinstance(data, dict):
        data = data.get("fixes")
    if not isinstance(data, list):
        return [], "fixes.json must be a list of fixes"
    out = []
    for x in data:
        if not isinstance(x, dict) or not all(isinstance(x.get(k), str) and x.get(k) for k in FIX_FIELDS):
            continue
        out.append({k: str(x.get(k, "")) for k in ("id", "finding", "title", "who", "file", "severity", "why", "change", "verify", "risk")})
    return out, None


def status_class(status):
    s = status.split(":")[0].strip()
    return {"clean": "ok", "done": "ok", "findings": "find", "partial": "warn", "skipped": "skip", "unavailable": "skip",
            "failed-to-run": "bad", "timeout": "bad"}.get(s, "skip")


# --- A small, safe Markdown renderer (the report is Markdown) ------------------------------------
def _inline(text):
    text = html.escape(text, quote=True)
    text = re.sub(r"`([^`]+)`", lambda m: "<code>%s</code>" % m.group(1), text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\s][^*]*)\*(?![*\w])", r"<em>\1</em>", text)

    def link(m):
        url = html.unescape(m.group(2)).strip()
        if not re.match(r"^(https?://|#|[A-Za-z0-9_./-]+$)", url):   # no javascript: or other schemes
            return m.group(0)
        return '<a href="%s" target="_blank" rel="noopener">%s</a>' % (html.escape(url, quote=True), m.group(1))
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def render_markdown(text):
    lines = text.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(lines)
    para = []

    def flush():
        if para:
            out.append("<p>%s</p>" % _inline(" ".join(para)))
            para.clear()

    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    while i < n:
        line = lines[i]
        if line.strip().startswith("```"):
            flush()
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>%s</code></pre>" % html.escape("\n".join(code)))
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush()
            level = len(m.group(1)) + 1
            out.append("<h%d>%s</h%d>" % (level, _inline(m.group(2)), level))
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]) and "-" in lines[i + 1]:
            flush()
            head = cells(line)
            i += 2
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append('<div class="tablewrap"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
                "".join("<th>%s</th>" % _inline(c) for c in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _inline(c) for c in r) for r in rows)))
            continue
        m = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", line)
        if m:
            flush()
            ordered = m.group(2)[0].isdigit()
            base = len(m.group(1))
            items = []
            while i < n:
                mm = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
                if mm and len(mm.group(1)) <= base + 1:
                    items.append(mm.group(3))
                    i += 1
                elif lines[i].startswith(" " * (base + 2)) and lines[i].strip() and not re.match(r"^\s*([-*]|\d+[.)])\s", lines[i]):
                    items[-1] += " " + lines[i].strip()   # a wrapped line of the same item
                    i += 1
                elif mm:   # a nested item: keep it as part of the parent line
                    items[-1] += " &middot; " + mm.group(3)
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % _inline(t) for t in items), tag))
            continue
        if line.lstrip().startswith(">"):
            flush()
            quote = []
            while i < n and lines[i].lstrip().startswith(">"):
                quote.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % _inline(" ".join(quote)))
            continue
        para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


def build(folder):
    meta = read_meta(folder)
    findings = read_findings(folder)
    manifest = []
    for line in (read(folder, "manifest.tsv") or "").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 2 and p[0]:
            manifest.append({"tool": p[0], "status": p[1], "cls": status_class(p[1]), "dimension": p[4] if len(p) > 4 else ""})
    scores = None
    try:
        scores = json.loads(read(folder, "scores.json") or "")
    except ValueError:
        pass
    if not isinstance(scores, dict):
        scores = None
    report_text = read(folder, "AUDIT.md")
    fixes, fixes_error = read_fixes(folder)
    project = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(folder)))) or "project"

    notices = []
    if meta.get("consistent") == "no":
        notices.append({"key": "n_inconsistent"})
    if meta.get("untrusted") == "yes":
        notices.append({"key": "n_untrusted"})
    gaps = [m for m in manifest if m["cls"] in ("bad", "skip", "warn")]
    if gaps:
        notices.append({"key": "n_gaps", "n": len(gaps)})

    verdict = scores.get("verdict") if scores and scores.get("verdict") in audit_verdict.VERDICT_TEXT else None
    data = {
        "project": project, "run": os.path.basename(os.path.normpath(folder)),
        "meta": "%s, commit %s, branch %s" % (meta.get("date", ""), meta.get("commit", "none")[:8], meta.get("branch", "none")),
        "verdict": verdict, "level": scores.get("level") if scores else None, "mode": scores.get("mode") if scores else None,
        "scores": (scores or {}).get("scores") or {}, "confidence": (scores or {}).get("confidence") or {},
        "findings": findings, "manifest": manifest, "checklist": read_checklist(report_text), "fixes": fixes,
        "fixes_error": fixes_error, "notices": notices, "i18n": I18N,
        "report_html": render_markdown(report_text) if report_text else "", "report_source": report_text or "",
    }
    # "<" ">" "&" are escaped so nothing in the data can end the script block or open a tag
    data_json = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return PAGE.replace("{{TITLE}}", html.escape("Audit: " + project)).replace("{{DATA}}", data_json)


PAGE = r"""<!doctype html>
<html lang="en" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--bg:#f6f7f9;--panel:#ffffff;--text:#1c2330;--muted:#5d6878;--line:#e1e5eb;--accent:#2f5bd8;--accent-text:#ffffff;
--critical:#b3122b;--high:#c2410c;--medium:#a16207;--low:#2f5fa8;--info:#5d6878;
--ok:#1f7a45;--warn:#a16207;--bad:#b3122b;--skip:#5d6878;--find:#c2410c;--code:#eef1f6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#12151b;--panel:#1b2029;--text:#e6e9ef;--muted:#9aa5b5;--line:#2c3441;--accent:#7ea2ff;--accent-text:#0e1320;
--critical:#ff6b81;--high:#ff8a5c;--medium:#e6b450;--low:#7ea2ff;--info:#9aa5b5;--ok:#4cc38a;--warn:#e6b450;--bad:#ff6b81;--skip:#9aa5b5;--find:#ff8a5c;--code:#232a36}}
:root[data-theme="dark"]{--bg:#12151b;--panel:#1b2029;--text:#e6e9ef;--muted:#9aa5b5;--line:#2c3441;--accent:#7ea2ff;--accent-text:#0e1320;
--critical:#ff6b81;--high:#ff8a5c;--medium:#e6b450;--low:#7ea2ff;--info:#9aa5b5;--ok:#4cc38a;--warn:#e6b450;--bad:#ff6b81;--skip:#9aa5b5;--find:#ff8a5c;--code:#232a36}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header.top{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line)}
.topin{max-width:1100px;margin:0 auto;padding:8px 16px;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;justify-content:space-between}
nav{display:flex;flex-wrap:wrap;gap:4px 14px} nav a{color:var(--muted);text-decoration:none;font-weight:600;font-size:.9rem;padding:2px 0}
nav a:hover{color:var(--accent)}
.tools{display:flex;gap:8px}
button,.btn{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--bg);color:var(--text);border-radius:8px;padding:5px 12px}
button:hover{border-color:var(--accent)}
button.primary{background:var(--accent);color:var(--accent-text);border-color:var(--accent);font-weight:600}
button:disabled{opacity:.5;cursor:not-allowed}
main{max-width:1100px;margin:0 auto;padding:20px 16px 120px}
h1{margin:4px 0 0;font-size:1.5rem} h2{font-size:1.15rem;margin:0 0 12px}
.sub{color:var(--muted);margin:2px 0 14px}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0;scroll-margin-top:64px}
.verdict{border-radius:10px;padding:14px 16px;margin:12px 0;border:1px solid var(--line);background:var(--panel);border-left-width:6px}
.verdict span{font-weight:700;font-size:1.15rem;margin-right:8px}
.v-dont-launch{border-left-color:var(--critical)} .v-launch-with-limits{border-left-color:var(--medium)}
.v-no-blocking-problems{border-left-color:var(--ok)} .v-none{border-left-color:var(--info)}
.notice{border:1px solid var(--medium);border-radius:8px;padding:8px 12px;margin:8px 0;background:var(--panel)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin:12px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.card b{display:block;font-size:1.5rem} .card span{color:var(--muted);font-size:.85rem}
.s-critical b{color:var(--critical)} .s-high b{color:var(--high)} .s-medium b{color:var(--medium)} .s-low b{color:var(--low)} .s-info b{color:var(--info)}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px}
.filters label{display:inline-flex;gap:4px;align-items:center;cursor:pointer}
input[type=search],select,textarea{background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font:inherit}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:.85rem;white-space:nowrap} #findings th{cursor:pointer}
td.file{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85rem;word-break:break-all}
.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.78rem;font-weight:600;color:#fff;background:var(--info)}
.p-critical{background:var(--critical)} .p-high{background:var(--high)} .p-medium{background:var(--medium)} .p-low{background:var(--low)} .p-info{background:var(--info)}
.c-ok td:nth-child(2){color:var(--ok)} .c-find td:nth-child(2){color:var(--find)} .c-warn td:nth-child(2){color:var(--warn)}
.c-bad td:nth-child(2){color:var(--bad);font-weight:600} .c-skip td:nth-child(2){color:var(--skip)}
.bars{display:grid;gap:8px} .bar{display:grid;grid-template-columns:170px 1fr 130px;gap:10px;align-items:center}
.track{background:var(--line);border-radius:6px;height:10px} .fill{background:var(--accent);height:10px;border-radius:6px}
.bar i{color:var(--muted);font-style:normal}
.fix{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.fix.on{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.fix h3{margin:0 0 4px;font-size:1rem} .fix .meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:var(--muted);font-size:.85rem;margin-bottom:6px}
.fix label.ok{display:inline-flex;gap:6px;align-items:center;font-weight:600;cursor:pointer}
.fix details{margin-top:6px} .fix summary{cursor:pointer;color:var(--muted)} .fix textarea{width:100%;min-height:52px;margin-top:8px}
.badge{border:1px solid var(--line);border-radius:999px;padding:0 8px;font-size:.78rem}
.sendbar{position:fixed;left:0;right:0;bottom:0;background:var(--panel);border-top:1px solid var(--line);padding:10px 16px;z-index:6}
.sendin{max-width:1100px;margin:0 auto;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
.report h2,.report h3,.report h4,.report h5{margin:18px 0 8px} .report h2{font-size:1.25rem;border-bottom:1px solid var(--line);padding-bottom:4px}
.report p,.report li{max-width:80ch} .report ul,.report ol{padding-left:22px}
.report code{background:var(--code);border-radius:4px;padding:1px 5px;font:.88em ui-monospace,Menlo,Consolas,monospace}
.report pre{background:var(--code);border-radius:8px;padding:10px 12px;overflow-x:auto} .report pre code{background:none;padding:0}
.report blockquote{border-left:4px solid var(--line);margin:8px 0;padding:2px 12px;color:var(--muted)}
.report a{color:var(--accent)} .report hr{border:0;border-top:1px solid var(--line)}
pre.source{white-space:pre-wrap;word-break:break-word;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:8px}
.seg button{border:0;border-radius:0} .seg button.on{background:var(--accent);color:var(--accent-text)}
.muted{color:var(--muted)} .empty{padding:12px;color:var(--muted)}
@media (max-width:640px){.bar{grid-template-columns:1fr}}
@media print{header.top,.sendbar{display:none}}
</style>
</head>
<body>
<header class="top"><div class="topin">
 <nav>
  <a href="#summary" data-i18n="nav_summary"></a><a href="#findings-sec" data-i18n="nav_findings"></a><a href="#fixes-sec" data-i18n="nav_fixes"></a>
  <a href="#checklist-sec" data-i18n="nav_checklist"></a><a href="#coverage-sec" data-i18n="nav_coverage"></a><a href="#report-sec" data-i18n="nav_report"></a>
 </nav>
 <div class="tools"><button id="lang" type="button"></button><button id="theme" type="button"></button></div>
</div></header>
<main>
<div id="summary">
 <h1 id="project"></h1><p class="sub" id="meta"></p>
 <div id="verdict"></div><div id="notices"></div><div class="cards" id="cards"></div>
 <div id="scores"></div>
</div>

<section id="findings-sec">
<h2 data-i18n="findings"></h2>
<div class="filters" id="filters">
 <label><input type="checkbox" data-sev="critical" checked> <span data-i18n="sev_critical"></span></label>
 <label><input type="checkbox" data-sev="high" checked> <span data-i18n="sev_high"></span></label>
 <label><input type="checkbox" data-sev="medium" checked> <span data-i18n="sev_medium"></span></label>
 <label><input type="checkbox" data-sev="low" checked> <span data-i18n="sev_low"></span></label>
 <label><input type="checkbox" data-sev="info" checked> <span data-i18n="sev_info"></span></label>
 <select id="source"></select>
 <input type="search" id="q" data-i18n-ph="search" size="26">
 <span class="muted" id="count"></span>
</div>
<div class="tablewrap"><table id="findings"><thead><tr>
 <th data-k="severity" data-i18n="th_severity"></th><th data-k="id" data-i18n="th_id"></th><th data-k="source" data-i18n="th_tool"></th>
 <th data-k="rule" data-i18n="th_what"></th><th data-k="file" data-i18n="th_where"></th></tr></thead><tbody></tbody></table></div>
<div class="empty" id="none" hidden data-i18n="no_match"></div>
<p class="muted" data-i18n="findings_note"></p>
</section>

<section id="fixes-sec">
<h2 data-i18n="fixes"></h2>
<p class="muted" data-i18n="fixes_intro"></p>
<div id="fixlist"></div>
<p class="muted" id="serverhint" hidden></p>
</section>

<section id="progress-sec" hidden>
<h2 data-i18n="progress"></h2>
<p><span class="badge" id="state"></span> <span class="muted" id="reportready"></span></p>
<pre class="source" id="log"></pre>
</section>

<section id="checklist-sec" hidden>
<h2 data-i18n="checklist"></h2>
<div class="tablewrap"><table id="checklist"><thead><tr><th data-i18n="th_n"></th><th data-i18n="th_item"></th><th data-i18n="th_mark"></th><th data-i18n="th_by"></th><th data-i18n="th_evidence"></th></tr></thead><tbody></tbody></table></div>
</section>

<section id="coverage-sec">
<h2 data-i18n="coverage"></h2>
<div class="tablewrap"><table id="coverage"><thead><tr><th data-i18n="th_check"></th><th data-i18n="th_result"></th><th data-i18n="th_feeds"></th></tr></thead><tbody></tbody></table></div>
</section>

<section id="report-sec">
<h2 data-i18n="report"></h2>
<div class="seg" id="seg"><button type="button" data-view="formatted" class="on" data-i18n="formatted"></button><button type="button" data-view="source" data-i18n="source"></button></div>
<div class="report" id="report-formatted"></div>
<pre class="source" id="report-source" hidden></pre>
<div class="empty" id="no-report" hidden data-i18n="no_report"></div>
</section>
</main>

<div class="sendbar" id="sendbar" hidden><div class="sendin">
 <strong><span id="selcount">0</span> <span data-i18n="selected"></span></strong>
 <span style="display:flex;gap:8px;flex-wrap:wrap">
  <button type="button" id="selall" data-i18n="select_all"></button><button type="button" id="clearsel" data-i18n="clear"></button>
  <button type="button" id="dl" data-i18n="download"></button><button type="button" id="copy" data-i18n="copy"></button><button type="button" id="fixbtn" class="primary" data-i18n="fix_btn" hidden></button>
 </span><span class="muted" id="copied" aria-live="polite"></span>
</div></div>

<!--AUDIT_SERVER-->
<script type="application/json" id="data">{{DATA}}</script>
<script>
(function(){
 var D=JSON.parse(document.getElementById('data').textContent), root=document.documentElement;
 var KEY='audit-ui:'+D.project+':'+D.run;
 function load(k,d){try{var v=localStorage.getItem(k);return v===null?d:v}catch(e){return d}}
 function save(k,v){try{localStorage.setItem(k,v)}catch(e){}}
 var lang=load('audit-ui:lang',(navigator.language||'en').slice(0,2)==='fr'?'fr':'en'); if(!D.i18n[lang])lang='en';
 var theme=load('audit-ui:theme','auto');
 function t(k,v){var s=(D.i18n[lang]&&D.i18n[lang][k])||D.i18n.en[k]||k;if(v)Object.keys(v).forEach(function(x){s=s.replace('{'+x+'}',v[x])});return s}
 function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
 function dark(){return theme==='dark'||(theme==='auto'&&window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches)}
 function applyTheme(){root.setAttribute('data-theme',theme==='auto'?'auto':theme);
  document.getElementById('theme').textContent=dark()?t('theme_light'):t('theme_dark')}

 // ---- fixes state
 var picked={},notes={};
 try{var st=JSON.parse(load(KEY+':fixes','{}'));picked=st.picked||{};notes=st.notes||{}}catch(e){}
 function saveFixes(){save(KEY+':fixes',JSON.stringify({picked:picked,notes:notes}))}

 var order={critical:0,high:1,medium:2,low:3,info:4}, sortKey='severity', sortDir=1;

 function renderStatic(){
  root.lang=lang;
  document.querySelectorAll('[data-i18n]').forEach(function(n){n.textContent=t(n.dataset.i18n)});
  document.querySelectorAll('[data-i18n-ph]').forEach(function(n){n.placeholder=t(n.dataset.i18nPh)});
  document.getElementById('lang').textContent=t('lang_btn');
  applyTheme();
  document.getElementById('project').textContent=D.project;
  document.getElementById('meta').textContent=D.meta;
  var v=document.getElementById('verdict');v.textContent='';
  var vk=D.verdict||'none', box=el('div','verdict v-'+vk), b=el('span',null,t('verdict_'+vk));box.appendChild(b);
  box.appendChild(document.createTextNode(D.verdict?(t('level')+' '+D.level+', '+t(D.mode||'full')+' '+t('audit')):t('verdict_none_hint')));v.appendChild(box);
  var nb=document.getElementById('notices');nb.textContent='';
  D.notices.forEach(function(n){nb.appendChild(el('div','notice',(n.n!=null?n.n+' ':'')+t(n.key)))});
  var counts={};D.findings.forEach(function(f){counts[f.severity]=(counts[f.severity]||0)+1});
  var cards=document.getElementById('cards');cards.textContent='';
  ['critical','high','medium','low','info'].forEach(function(s){var c=el('div','card s-'+s);c.appendChild(el('b',null,String(counts[s]||0)));c.appendChild(el('span',null,t('sev_'+s)));cards.appendChild(c)});
  var ran=D.manifest.filter(function(m){return m.cls==='ok'||m.cls==='find'}).length, c2=el('div','card');
  c2.appendChild(el('b',null,ran+' / '+D.manifest.length));c2.appendChild(el('span',null,t('checks_ran')));cards.appendChild(c2);
  var sc=document.getElementById('scores');sc.textContent='';
  var names=Object.keys(D.scores);
  if(names.length){var sec=el('section');sec.appendChild(el('h2',null,t('scores')));var bars=el('div','bars');
   names.forEach(function(k){var val=D.scores[k],row=el('div','bar');row.appendChild(el('b',null,t('dim_'+k)));
    if(val==null){row.appendChild(el('span'));row.appendChild(el('i',null,t('not_assessed')))}
    else{var tr=el('div','track'),f=el('div','fill');f.style.width=Math.max(0,Math.min(100,val))+'%';tr.appendChild(f);row.appendChild(tr);
     row.appendChild(el('i',null,val+(D.confidence[k]?' ('+D.confidence[k]+')':'')))}
    bars.appendChild(row)});sec.appendChild(bars);sc.appendChild(sec)}
  // filters
  var sel=document.getElementById('source'),cur=sel.value;sel.textContent='';
  var o=el('option',null,t('all_tools'));o.value='';sel.appendChild(o);
  Array.from(new Set(D.findings.map(function(f){return f.source}))).sort().forEach(function(s){var op=el('option',null,s);op.value=s;sel.appendChild(op)});sel.value=cur;
  // coverage
  var cb=document.querySelector('#coverage tbody');cb.textContent='';
  D.manifest.forEach(function(m){var tr=el('tr','c-'+m.cls);tr.appendChild(el('td',null,m.tool));tr.appendChild(el('td',null,m.status));tr.appendChild(el('td',null,m.dimension));cb.appendChild(tr)});
  // checklist
  var ck=document.getElementById('checklist-sec');ck.hidden=!D.checklist.length;
  var kb=document.querySelector('#checklist tbody');kb.textContent='';
  D.checklist.forEach(function(r){var tr=el('tr');[String(r.n),r.item,r.mark,r.by,r.evidence].forEach(function(x){tr.appendChild(el('td',null,x))});kb.appendChild(tr)});
  // report
  var rf=document.getElementById('report-formatted'),rs=document.getElementById('report-source'),nr=document.getElementById('no-report');
  var has=!!D.report_source;nr.hidden=has;document.getElementById('seg').hidden=!has;
  rf.innerHTML=D.report_html;   // built and escaped by the generator (no raw HTML from the report passes through)
  rs.textContent=D.report_source;
  renderFindings();renderFixes();
 }

 function renderFindings(){
  var body=document.querySelector('#findings tbody'),none=document.getElementById('none'),count=document.getElementById('count');
  var on={};document.querySelectorAll('#filters input[data-sev]').forEach(function(c){on[c.dataset.sev]=c.checked});
  var term=document.getElementById('q').value.toLowerCase(),s=document.getElementById('source').value;
  var rows=D.findings.filter(function(f){return on[f.severity]&&(!s||f.source===s)&&(!term||(f.file+' '+f.rule+' '+f.id+' '+f.source).toLowerCase().indexOf(term)>=0)});
  rows.sort(function(a,b){var x=sortKey==='severity'?order[a.severity]:String(a[sortKey]),y=sortKey==='severity'?order[b.severity]:String(b[sortKey]);return(x<y?-1:x>y?1:0)*sortDir});
  body.textContent='';
  rows.forEach(function(f){var tr=el('tr'),td=el('td'),p=el('span','pill p-'+f.severity,t('sev_'+f.severity));td.appendChild(p);tr.appendChild(td);
   tr.appendChild(el('td',null,f.id));tr.appendChild(el('td',null,f.source));tr.appendChild(el('td',null,f.rule+(f.count>1?'  (x'+f.count+')':'')));
   tr.appendChild(el('td','file',f.file+(f.line!==''&&f.line!=null?':'+f.line:'')));body.appendChild(tr)});
  count.textContent=rows.length+' '+t('of')+' '+D.findings.length+' '+t('shown');none.hidden=rows.length>0;
 }

 function renderFixes(){
  var box=document.getElementById('fixlist');box.textContent='';
  if(!D.fixes.length){box.appendChild(el('div','empty',D.fixes_error||t('fixes_none')))}
  D.fixes.forEach(function(f){
   var card=el('div','fix'+(picked[f.id]?' on':'')),h=el('h3',null,f.id+'  '+f.title);card.appendChild(h);
   var meta=el('div','meta');
   if(f.severity){meta.appendChild(el('span','pill p-'+f.severity,t('sev_'+f.severity)||f.severity))}
   if(f.finding)meta.appendChild(el('span','badge',f.finding));
   if(f.file)meta.appendChild(el('span','file',f.file));
   meta.appendChild(el('span','badge',f.who==='you'?t('who_you'):t('who_claude')));
   if(f.risk)meta.appendChild(el('span',null,t('risk')+': '+f.risk));
   card.appendChild(meta);
   [['why',f.why],['change',f.change],['verify',f.verify]].forEach(function(p){
    if(!p[1])return;var d=el('details'),s=el('summary',null,t(p[0]));d.appendChild(s);
    var body=p[0]==='change'?el('pre','source',p[1]):el('div',null,p[1]);d.appendChild(body);if(p[0]!=='verify')d.open=true;card.appendChild(d)});
   var lab=el('label','ok'),cb=el('input');cb.type='checkbox';cb.checked=!!picked[f.id];
   cb.addEventListener('change',function(){picked[f.id]=cb.checked;saveFixes();card.className='fix'+(cb.checked?' on':'');updateBar()});
   lab.appendChild(cb);lab.appendChild(el('span',null,f.who==='you'?t('myself'):t('approve')));card.appendChild(lab);
   var ta=el('textarea');ta.placeholder=t('note');ta.value=notes[f.id]||'';
   ta.addEventListener('input',function(){notes[f.id]=ta.value;saveFixes()});card.appendChild(ta);
   box.appendChild(card)});
  updateBar();
 }
 function chosen(){return D.fixes.filter(function(f){return picked[f.id]})}
 function updateBar(){var n=chosen().length;document.getElementById('selcount').textContent=n;document.getElementById('sendbar').hidden=!D.fixes.length;
  document.getElementById('copy').disabled=!n;document.getElementById('dl').disabled=!n}
 function message(){
  var c=chosen();if(!c.length)return t('msg_none');
  var mine=c.filter(function(f){return f.who==='you'}),todo=c.filter(function(f){return f.who!=='you'});
  var L=[t('msg_head')+' audit/'+D.run+' ('+D.project+'):',''];
  function line(f,i){var s=(i+1)+'. '+f.id+(f.finding?' ('+f.finding+')':'')+' - '+f.title+(f.file?' ['+f.file+']':'');
   if(notes[f.id]&&notes[f.id].trim())s+='\n   '+t('msg_note')+': '+notes[f.id].trim();return s}
  todo.forEach(function(f,i){L.push(line(f,i))});
  if(mine.length){L.push('','** '+t('msg_mine')+':');mine.forEach(function(f,i){L.push(line(f,i))})}
  L.push('',t('msg_rules'),'',JSON.stringify({run:D.run,approved:todo.map(function(f){return{id:f.id,finding:f.finding||null,note:(notes[f.id]||'').trim()}}),
   mine:mine.map(function(f){return f.id})}));
  return L.join('\n');
 }
 function flash(msg){var c=document.getElementById('copied');c.textContent=msg;setTimeout(function(){c.textContent=''},3000)}
 document.getElementById('copy').addEventListener('click',function(){
  var m=message();
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(m).then(function(){flash(t('copied'))},function(){fallback(m)})}else{fallback(m)}});
 function fallback(m){var ta=el('textarea');ta.value=m;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');flash(t('copied'))}catch(e){}document.body.removeChild(ta)}
 document.getElementById('dl').addEventListener('click',function(){
  var c=chosen(),data={run:D.run,project:D.project,approved:c.filter(function(f){return f.who!=='you'}).map(function(f){return{id:f.id,finding:f.finding||null,title:f.title,note:(notes[f.id]||'').trim()}}),
   mine:c.filter(function(f){return f.who==='you'}).map(function(f){return f.id})};
  var a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download='approved-fixes.json';document.body.appendChild(a);a.click();document.body.removeChild(a)});
 document.getElementById('selall').addEventListener('click',function(){D.fixes.forEach(function(f){picked[f.id]=true});saveFixes();renderFixes()});
 document.getElementById('clearsel').addEventListener('click',function(){picked={};saveFixes();renderFixes()});

 document.getElementById('lang').addEventListener('click',function(){lang=lang==='en'?'fr':'en';save('audit-ui:lang',lang);renderStatic()});
 document.getElementById('theme').addEventListener('click',function(){theme=dark()?'light':'dark';save('audit-ui:theme',theme);applyTheme()});
 if(window.matchMedia)matchMedia('(prefers-color-scheme: dark)').addEventListener&&matchMedia('(prefers-color-scheme: dark)').addEventListener('change',applyTheme);
 document.querySelectorAll('#filters input[data-sev]').forEach(function(c){c.addEventListener('change',renderFindings)});
 document.getElementById('q').addEventListener('input',renderFindings);document.getElementById('source').addEventListener('change',renderFindings);
 document.querySelectorAll('#findings th').forEach(function(th){th.addEventListener('click',function(){var k=th.dataset.k;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1}renderFindings()})});
 document.querySelectorAll('#seg button').forEach(function(b){b.addEventListener('click',function(){
  document.querySelectorAll('#seg button').forEach(function(x){x.classList.toggle('on',x===b)});
  document.getElementById('report-formatted').hidden=b.dataset.view!=='formatted';document.getElementById('report-source').hidden=b.dataset.view!=='source'})});
 // ---- start Claude from this page (only when served by scan.sh --serve)
 var S=window.AUDIT_SERVER||null, timer=null;
 function api(path,opts){opts=opts||{};opts.headers={'X-Audit-Token':S.token,'Content-Type':'application/json'};
  return fetch(path,opts).then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}})})}
 function claudeFixes(){return chosen().filter(function(f){return f.who!=='you'})}
 function showState(st){var b=document.getElementById('state');b.textContent=t('state_'+st.state);
  document.getElementById('progress-sec').hidden=(st.state==='idle');
  document.getElementById('log').textContent=st.log&&st.log.length?st.log.join('\n\n'):t('log_empty');
  document.getElementById('reportready').textContent=st.report?t('report_ready',{run:D.run}):'';
  document.getElementById('fixbtn').disabled=(st.state==='running')||!claudeFixes().length}
 function poll(){api('/api/status').then(function(r){if(r.ok){showState(r.j);if(r.j.state==='running'){clearTimeout(timer);timer=setTimeout(poll,2000)}}})}
 function initServer(){
  var hint=document.getElementById('serverhint');
  if(!S){hint.hidden=!D.fixes.length;hint.textContent=t('server_hint');return}
  if(!S.fixable){hint.hidden=false;hint.textContent=S.reason;return}
  hint.hidden=true;document.getElementById('fixbtn').hidden=false;poll()}
 document.getElementById('fixbtn').addEventListener('click',function(){
  var c=claudeFixes();if(!c.length||!S)return;
  if(!confirm(t('confirm_fix',{n:c.length})))return;
  api('/api/start',{method:'POST',body:JSON.stringify({ids:c.map(function(f){return f.id}),notes:notes})}).then(function(r){
   if(r.ok){flash(t('started'));poll()}else{flash(t('start_failed')+': '+(r.j&&r.j.error||''))}})});
 var _upd=updateBar;updateBar=function(){_upd();if(S&&S.fixable){document.getElementById('fixbtn').disabled=!claudeFixes().length}};
 renderStatic();initServer();
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
