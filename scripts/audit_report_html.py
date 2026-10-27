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
import audit_i18n      # noqa: E402
import audit_translate  # noqa: E402

SEVERITIES = ["critical", "high", "medium", "low", "info"]

# Every label on the page, in both languages. The test suite checks both have the same keys.
I18N = {
    "en": {
        "lang_btn": "Français", "theme_light": "Light", "theme_dark": "Dark",
        "nav_summary": "Summary", "nav_findings": "Findings", "nav_fixes": "Fixes", "nav_checklist": "Checklist",
        "nav_coverage": "Coverage", "nav_report": "Report",
        "verdict_dont-launch": "Don't launch yet", "verdict_launch-with-limits": "Launch with limits",
        "verdict_no-blocking-problems": "No blocking problems found", "verdict_none": "No written verdict yet",
        "verdict_none_hint": "This page shows the scan results only.", "mode_line": "Level {n}, {mode} audit",
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
        "meta_line": "{date}, commit {commit}, branch {branch}",
        "not_translated": "This report is not available in English yet. Showing the original language.",
        "translate_btn": "Translate with Claude", "translating": "Translating...", "translated": "Translated. Reloading...",
        "translate_hint": "To translate it, run: bash scan.sh --translate (or open the page with bash scan.sh --serve and click Translate).",
        "translate_failed": "The translation did not finish",
    },
    "fr": {
        "lang_btn": "English", "theme_light": "Clair", "theme_dark": "Sombre",
        "nav_summary": "Résumé", "nav_findings": "Constats", "nav_fixes": "Correctifs", "nav_checklist": "Liste de lancement",
        "nav_coverage": "Couverture", "nav_report": "Rapport",
        "verdict_dont-launch": "Ne pas lancer tout de suite", "verdict_launch-with-limits": "Lancement avec réserves",
        "verdict_no-blocking-problems": "Aucun problème bloquant trouvé", "verdict_none": "Pas encore de verdict écrit",
        "verdict_none_hint": "Cette page ne montre que les résultats de l'analyse.", "mode_line": "Niveau {n}, audit {mode}",
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
        "meta_line": "{date}, commit {commit}, branche {branch}",
        "not_translated": "Ce rapport n'est pas encore disponible en français. Affichage dans la langue d'origine.",
        "translate_btn": "Traduire avec Claude", "translating": "Traduction en cours...", "translated": "Traduit. Rechargement...",
        "translate_hint": "Pour le traduire, exécutez : bash scan.sh --translate (ou ouvrez la page avec bash scan.sh --serve et cliquez sur Traduire).",
        "translate_failed": "La traduction ne s'est pas terminée",
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
        if not isinstance(x, dict) or not (isinstance(x.get("id"), str) and x.get("id") and isinstance(x.get("who"), str) and x.get("who")):
            continue
        if not (isinstance(x.get("title"), (str, dict)) and x.get("title")):
            continue
        row = {k: str(x.get(k, "")) for k in ("id", "finding", "who", "file", "severity", "risk")}
        for k in ("title", "why", "change", "verify"):
            row[k] = x.get(k) or ""
        out.append(row)
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


def _e(x):
    return html.escape(str(x), quote=True)


def lang_map(value, primary):
    """A text that is a plain string (written in the report's language) or {"en": ..., "fr": ...} -> {lang: text}."""
    if isinstance(value, dict):
        return {k: str(v) for k, v in value.items() if k in audit_translate.LANGS and v}
    if value:
        return {primary: str(value)}
    return {}


def pick(mapping, lang="en"):
    """The text in `lang`, else any language that exists."""
    if not isinstance(mapping, dict):
        return str(mapping or "")
    return mapping.get(lang) or mapping.get("en") or mapping.get("fr") or ""


def _static_cards(data, en):
    counts = {s: sum(1 for x in data["findings"] if x["severity"] == s) for s in SEVERITIES}
    ran = sum(1 for m in data["manifest"] if m["cls"] in ("ok", "find"))
    cards = "".join('<div class="card s-%s"><b>%d</b><span>%s</span></div>' % (s, counts[s], _e(en["sev_" + s])) for s in SEVERITIES)
    return cards + '<div class="card"><b>%d / %d</b><span>%s</span></div>' % (ran, len(data["manifest"]), _e(en["checks_ran"]))


def _static_scores(data, en):
    bars = []
    for k, v in data["scores"].items():
        label = _e(en.get("dim_" + k, k))
        if v is None:
            bars.append('<div class="bar"><b>%s</b><span></span><i>%s</i></div>' % (label, _e(en["not_assessed"])))
            continue
        conf = data["confidence"].get(k)
        bars.append('<div class="bar"><b>%s</b><div class="track"><div class="fill" style="width:%d%%"></div></div><i>%d%s</i></div>'
                    % (label, max(0, min(100, int(v))), int(v), (" (%s)" % _e(conf)) if conf else ""))
    if not bars:
        return ""
    return '<section><h2>%s</h2><div class="bars">%s</div></section>' % (_e(en["scores"]), "".join(bars))


def _static_findings(data, en):
    rows = []
    for x in data["findings"][:400]:   # the script shows them all; without it the first 400 are enough to read
        where = x["file"] + (":%s" % x["line"] if x["line"] not in ("", None) else "")
        what = _e(x["rule"] + ("  (x%d)" % x["count"] if x["count"] > 1 else ""))
        if x.get("desc"):
            what += '<br><small class="muted">%s</small>' % _e(x["desc"]["en"])
        rows.append('<tr><td><span class="pill p-%s">%s</span></td><td>%s</td><td>%s</td><td>%s</td><td class="file">%s</td></tr>' % (
            _e(x["severity"]), _e(en["sev_" + x["severity"]]), _e(x["id"]), _e(x["source"]), what, _e(where)))
    return "".join(rows)


def _static_fixes(data, en):
    cards = []
    for x in data["fixes"]:
        meta = ['<span class="badge">%s</span>' % _e(en["who_you"] if x["who"] == "you" else en["who_claude"])]
        if x.get("finding"):
            meta.append('<span class="badge">%s</span>' % _e(x["finding"]))
        if x.get("file"):
            meta.append('<span class="file">%s</span>' % _e(x["file"]))
        body = "".join("<p><b>%s:</b> %s</p>" % (_e(en[k]), _e(pick(x[k]))) for k in ("why", "change", "verify") if x.get(k))
        cards.append('<div class="fix"><h3>%s  %s</h3><div class="meta">%s</div>%s</div>' % (_e(x["id"]), _e(pick(x["title"])), "".join(meta), body))
    return "".join(cards) or '<div class="empty">%s</div>' % _e(data["fixes_error"] or en["fixes_none"])


def static_fragments(data):
    """The page content as plain HTML (English), so it shows even where scripts do not run.
    The page script replaces all of this with the interactive, translated version."""
    en = I18N["en"]
    vk = data["verdict"] or "none"
    tail = en["mode_line"].format(n=data["level"], mode=en.get(data["mode"] or "full", "")) if data["verdict"] else en["verdict_none_hint"]
    rep = data["reports"].get("en") or data["reports"].get(data["primary"]) or {}
    return {
        "S_PROJECT": _e(data["project"]),
        "S_META": _e(en["meta_line"].format(**data["meta"])),
        "S_VERDICT": '<div class="verdict v-%s"><span>%s</span>%s</div>' % (vk, _e(en["verdict_" + vk]), _e(tail)),
        "S_NOTICES": "".join('<div class="notice">%s%s</div>' % (("%d " % n["n"]) if n.get("n") is not None else "", _e(en[n["key"]])) for n in data["notices"]),
        "S_CARDS": _static_cards(data, en),
        "S_SCORES": _static_scores(data, en),
        "S_FINDINGS": _static_findings(data, en),
        "S_FIXES": _static_fixes(data, en),
        "S_CHECK_HIDDEN": "" if data["checklist"] else " hidden",
        "S_CHECKLIST": "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % _e(c) for c in (r["n"], pick(r["item"]), r["mark"], r["by"], pick(r["evidence"]))) for r in data["checklist"]),
        "S_COVERAGE": "".join('<tr class="c-%s"><td>%s</td><td>%s</td><td>%s</td></tr>' % (m["cls"], _e(m["tool"]), _e(pick(m["status_i18n"])), _e(pick(m["dim_i18n"]))) for m in data["manifest"]),
        "S_REPORT": rep.get("html", ""),   # already built and escaped by render_markdown
        "S_NOREPORT_HIDDEN": " hidden" if data["reports"] else "",
    }


def fill_labels(page):
    """Put the English text into every element the page script would translate."""
    en = I18N["en"]
    pattern = r'(<(\w+)[^>]*\sdata-i18n="(\w+)"[^>]*>)(</\2>)'
    return re.sub(pattern, lambda m: m.group(1) + _e(en.get(m.group(3), "")) + m.group(4), page)


def read_manifest(folder):
    rows = []
    for line in (read(folder, "manifest.tsv") or "").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 2 and p[0]:
            dimension = p[4] if len(p) > 4 else ""
            rows.append({"tool": p[0], "status": p[1], "cls": status_class(p[1]), "dimension": dimension,
                         "status_i18n": audit_i18n.translate_status(p[1]), "dim_i18n": audit_i18n.translate_dimensions(dimension)})
    return rows


def read_scores(folder):
    try:
        scores = json.loads(read(folder, "scores.json") or "")
    except ValueError:
        return None
    return scores if isinstance(scores, dict) else None


def load_reports(folder, primary):
    """The written report in each language that exists, and the launch checklist merged from them."""
    reports, by_lang = {}, {}
    for lang in audit_translate.LANGS:
        text = read(folder, os.path.basename(audit_translate.report_path(folder, lang, primary)))
        if text:
            reports[lang] = {"html": render_markdown(text), "source": text}
            by_lang[lang] = {r["n"]: r for r in read_checklist(text)}
    checklist = []
    for n in sorted(set().union(*[set(c) for c in by_lang.values()])) if by_lang else []:
        rows = {lg: c[n] for lg, c in by_lang.items() if n in c}
        first = rows.get(primary) or next(iter(rows.values()))
        builtin = audit_i18n.CHECKLIST.get(n)
        item = {"en": builtin[0], "fr": builtin[1]} if builtin else {lg: r["item"] for lg, r in rows.items()}
        checklist.append({"n": n, "group": first["group"], "mark": first["mark"], "by": first["by"], "item": item,
                          "evidence": {lg: r["evidence"] for lg, r in rows.items() if r["evidence"]}})
    return reports, checklist


def build_notices(meta, manifest):
    notices = []
    if meta.get("consistent") == "no":
        notices.append({"key": "n_inconsistent"})
    if meta.get("untrusted") == "yes":
        notices.append({"key": "n_untrusted"})
    gaps = [m for m in manifest if m["cls"] in ("bad", "skip", "warn")]
    if gaps:
        notices.append({"key": "n_gaps", "n": len(gaps)})
    return notices


def build_data(folder):
    """Everything the page shows, as one dictionary (also embedded in the page for its script)."""
    meta = read_meta(folder)
    manifest = read_manifest(folder)
    scores = read_scores(folder) or {}
    primary = audit_translate.primary_language(folder)
    reports, checklist = load_reports(folder, primary)
    findings = read_findings(folder)
    for finding in findings:
        d = audit_i18n.describe_rule(finding["rule"])
        finding["desc"] = {"en": d[0], "fr": d[1]} if d else None
    fixes, fixes_error = read_fixes(folder)
    for fx in fixes:
        for key in ("title", "why", "change", "verify"):
            fx[key] = lang_map(fx[key], primary)
    verdict = scores.get("verdict") if scores.get("verdict") in audit_verdict.VERDICT_TEXT else None
    return {
        "project": os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(folder)))) or "project",
        "run": os.path.basename(os.path.normpath(folder)),
        "meta": {"date": meta.get("date", ""), "commit": meta.get("commit", "none")[:8], "branch": meta.get("branch", "none")},
        "primary": primary, "verdict": verdict, "level": scores.get("level"), "mode": scores.get("mode"),
        "scores": scores.get("scores") or {}, "confidence": scores.get("confidence") or {},
        "findings": findings, "manifest": manifest, "checklist": checklist, "fixes": fixes, "fixes_error": fixes_error,
        "notices": build_notices(meta, manifest), "i18n": I18N, "reports": reports,
        "missing_languages": [lg for lg, _ in audit_translate.missing(folder)[1]],
    }


def build(folder):
    data = build_data(folder)
    # "<" ">" "&" are escaped so nothing in the data can end the script block or open a tag
    data_json = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = fill_labels(PAGE)
    for key, value in static_fragments(data).items():
        page = page.replace("{{%s}}" % key, value)
    return page.replace("{{TITLE}}", html.escape("Audit: " + data["project"])).replace("{{DATA}}", data_json)


def _load_page():
    """The page is three files in scripts/web/: page.html (the skeleton), page.css and page.js."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

    def part(name):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            return f.read()
    return part("page.html").replace("{{CSS}}", part("page.css")).replace("{{JS}}", part("page.js"))


PAGE = _load_page()


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
