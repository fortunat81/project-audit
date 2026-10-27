#!/usr/bin/env python3
"""Project audit runner. Detects what the project is, then runs only the check modules in audit_checks/
that apply to it. Saves raw output and records what happened. Never aborts: scanners exit non-zero when
they find problems, which is normal.

Usage (run from the project root; scan.sh calls this):
  scan.sh                  run the scan
  scan.sh --untrusted      (before any mode) skip every check that runs the project's own code; use it for code you did not write
  scan.sh --detect         show what was detected and which modules apply (changes nothing)
  scan.sh --all            scan this folder and every project folder in it, each with its own checks
  scan.sh --projects       list project folders (this one and any in subfolders); audit each (changes nothing)
  scan.sh --report-html    rebuild the web page (report.html) for the latest run; --open also opens it in your browser
  scan.sh --translate      add the other language (English or French) of the report and fixes, using Claude Code
  scan.sh --serve          open the audit screen from a local server: tick fixes and click "Fix with Claude" to start Claude Code on them
  scan.sh --verdict        compute the release verdict from scores.json and the checklist in AUDIT.md (changes nothing)
  scan.sh --verify-report  check the finished AUDIT.md and scores.json for mistakes (changes nothing)
  scan.sh --check          list missing tools and how to install them (changes nothing)
  scan.sh --install        install the missing tools this project needs (--install all, or --install tool tool ...)
  scan.sh --install-deps   install this project's own packages (no install scripts) so tsc/eslint/knip can run
  scan.sh --status         compare with the last audit and recommend quick or full (changes nothing)
  scan.sh --version        branch, behind/ahead of GitHub, uncommitted files (runs git fetch only)
  scan.sh --add-gitignore  add "audit/" to this folder's .gitignore (the scan never edits it on its own)

Optional per-project settings in .audit.conf (plain key=value lines, never executed):
  url=https://example.com       also check the live site (or set AUDIT_URL for one run)
  skip=lizard,knip              tools to leave out
  ignore=legacy/**,vendor/**    extra paths to leave out of duplication checks
  untrusted=yes                 always run in untrusted mode

Untrusted mode is for code you did not write. Some checks run the project's OWN code (its ESLint config,
its compiler and plugins, its package scripts), and a hostile project could use that to run commands on
this machine. In untrusted mode those checks are skipped and said so; what still runs only READS files.
Secret-looking environment variables are removed first. The network stays on.
Standard library only (Python 3.8+).
"""
import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import audit_core  # noqa: E402
import audit_detect  # noqa: E402
import audit_modes  # noqa: E402
import audit_progress  # noqa: E402
from audit_checks import load_modules  # noqa: E402
from audit_core import Ctx, posix, read_text  # noqa: E402


def make_ctx(args):
    audit_core.extend_path()
    ctx = Ctx(os.getcwd(), HERE)
    untrusted = os.environ.get("AUDIT_UNTRUSTED") or ctx.conf_get("untrusted")
    if args and args[0] == "--untrusted":
        untrusted = "1"
        args = args[1:]
    ctx.set_untrusted(untrusted in ("1", "yes", "true"))
    return ctx, args


def detect_project(ctx):
    audit_detect.detect(ctx, ctx.audit_url)
    audit_detect.find_subprojects(ctx)


def tool_copy_state(tool_dir):
    """Is this copy of the audit tool current? Returns (state, warning). States: current, behind, no-git (a plain copy
    with no history, so nobody can tell), unknown (no GitHub address or no answer). Only behind and no-git carry a
    warning. Fetches from GitHub unless AUDIT_NO_FETCH=1. An old copy used to run silently and give weaker results."""
    if not os.path.exists(os.path.join(tool_dir, ".git")):
        return "no-git", ("WARNING: this copy of the audit tool has no git history, so it cannot tell whether it is out of date. "
                          "Replace it with a fresh clone (git clone https://github.com/fortunat81/project-audit) so you get the current checks.")

    def git(*args):
        r = subprocess.run(["git", "-C", tool_dir] + list(args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        return r.returncode, r.stdout.decode("utf-8", "replace").strip()
    try:
        if git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")[0] != 0:
            return "unknown", ""
        if os.environ.get("AUDIT_NO_FETCH") != "1":
            git("fetch", "--quiet")
        code, counts = git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    except (OSError, subprocess.TimeoutExpired):
        return "unknown", ""
    behind = int((counts.split() + ["0", "0"])[1]) if code == 0 else 0
    if behind > 0:
        return "behind", ("WARNING: this copy of the audit tool is %d commit(s) behind GitHub, so it may miss newer checks. "
                          "Update it: cd %s && git pull" % (behind, tool_dir.replace("\\", "/")))
    return "current", ""


def _git_meta(ctx):
    """Meta lines about the repository (empty set of facts outside git)."""
    if not ctx.is_git():
        return ["commit=none"]
    ahead = ctx.git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    return ["commit=%s" % (ctx.git("rev-parse", "--verify", "-q", "HEAD")[1].strip() or "none"),
            "branch=%s" % (ctx.git("rev-parse", "--abbrev-ref", "HEAD")[1].strip() or "none"),
            "uncommitted_files=%d" % len([ln for ln in ctx.git("status", "--porcelain", "--untracked-files=no")[1].splitlines() if ln]),
            "untracked_files=%d" % len([ln for ln in ctx.git("ls-files", "--others", "--exclude-standard")[1].splitlines() if ln and not ln.startswith("audit/")]),
            "ahead_behind_upstream=%s" % ("/".join(ahead[1].split()) if ahead[0] == 0 else "unknown"),
            "audit_folder_ignored=%s" % ("yes" if ctx.git("check-ignore", "-q", "audit/")[0] == 0 else "no")]


def _report_tool_copy(ctx):
    """Warn (and record in meta.txt) when this copy of the audit tool is old or cannot tell."""
    state, warning = tool_copy_state(os.path.dirname(HERE))
    ctx.meta("tool_copy=%s" % state)
    if warning:
        print(warning)


def _write_provenance(ctx):
    """What exactly was audited, with which settings, and did it stay the same?"""
    _report_tool_copy(ctx)
    settings = read_text(os.path.join(HERE, "gitleaks-extra.toml")) + read_text(os.path.join(ctx.root, ".audit.conf")) + "semgrep_config=p/default\n"
    describe = subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ctx.meta("fingerprint_start=%s" % ctx.fingerprint())
    ctx.meta("methodology_commit=%s" % (describe.stdout.decode().strip() if describe.returncode == 0 else "unknown"))
    ctx.meta("settings_hash=%s" % audit_core.hash_text(settings))
    ctx.meta("semgrep_rules=p/default, downloaded at scan time (not pinned): results can change when the rules are updated")
    ctx.meta("os=%s" % ctx.os_name())


def write_meta(ctx):
    meta = ["date=%s" % time.strftime("%Y-%m-%d"), "epoch=%d" % int(time.time()),
            "traits=%s" % " ".join(t for t in ctx.traits if t != "live-url"), "languages=%s" % ctx.langs,
            "unhandled_languages=%s" % (ctx.unhandled or "none"), "live_url=%s" % (ctx.audit_url or "none")]
    ctx.write("meta.txt", "".join(m + "\n" for m in meta + _git_meta(ctx)))
    _write_provenance(ctx)


def status_bucket(status):
    """Which column of the coverage line a manifest status counts in."""
    if status in ("clean", "findings", "done", "timeout"):
        return status
    if status.startswith("failed-to-run"):
        return "failed"
    if status.startswith("partial"):
        return "partial"
    return "skipped"


def coverage_lines(rows, unhandled):
    """The coverage text for manifest rows (each a list: tool, status, ...) and the languages with no dedicated checks."""
    n = {k: 0 for k in ("clean", "findings", "done", "timeout", "failed", "partial", "skipped")}
    for r in rows:
        n[status_bucket(r[1])] += 1
    lines = ["COVERAGE: %d checks: %d clean, %d with findings, %d measured, %d partial, %d failed, %d timed out, %d skipped/unavailable" % (
        len(rows), n["clean"], n["findings"], n["done"], n["partial"], n["failed"], n["timeout"], n["skipped"])]
    gaps = [r for r in rows if r[1].startswith(("failed-to-run", "skipped", "unavailable", "partial")) or r[1] == "timeout"]
    if gaps:
        lines.append("INCOMPLETE: some checks did not run fully. A clean result does not cover them:")
        lines += ["  - %s: %s" % (r[0], r[1]) for r in gaps]
    if unhandled:
        lines.append("NO DEDICATED CHECKS for: %s (only the generic security, secret and dependency checks cover these files)" % unhandled)
    return lines


def coverage(ctx):
    """How much of the audit actually ran. Written to coverage.txt and printed."""
    rows = [ln.split("\t") for ln in read_text(ctx.path("manifest.tsv")).splitlines()[1:] if ln]
    lines = coverage_lines(rows, ctx.unhandled)
    ctx.write("coverage.txt", "".join(ln + "\n" for ln in lines))
    print("\n".join(lines))


def _new_run_folder(audit_dir):
    base = os.path.join(audit_dir, audit_core.now_stamp())
    out, n = base, 1
    while os.path.exists(out):
        n += 1
        out = "%s-%d" % (base, n)
    os.makedirs(out)
    return out


def _record_trust_and_subprojects(ctx):
    ctx.meta("time_limit=%ds" % audit_core.TIMEOUT_SECONDS)
    ctx.meta("untrusted=%s" % ("yes" if ctx.untrusted else "no"))
    if ctx.untrusted:
        ctx.dim = "general"
        ctx.record("trust-mode", "done: untrusted mode, checks that run the project's own code were skipped and secret-looking environment variables were removed", "-", "-")
    if ctx.is_git() and ctx.git("check-ignore", "-q", "audit/")[0] != 0:
        print("WARNING: audit/ is not git-ignored. Don't commit it. Run: bash scan.sh --add-gitignore")
    # Project folders this run does not cover must show up as a gap, not vanish silently
    if not ctx.subprojects:
        return
    ctx.dim = "general"
    if os.environ.get("AUDIT_ALL") == "1" and not os.environ.get("AUDIT_SUB"):
        print("==> subprojects (scanned separately by --all)")
        ctx.record("subprojects", "done: each project folder was scanned separately by --all: %s" % ctx.subprojects, "-", "-")
    else:
        print("==> subprojects (partial: not scanned)")
        ctx.record("subprojects", "partial: more project folders found: %s (the checks that need a project folder ran only here; audit each folder separately)" % ctx.subprojects, "-", "-")
    ctx.meta("subprojects=%s" % ctx.subprojects)


def _run_modules(ctx):
    """Runs every applicable check module. A broken or crashing module shows up as a gap, never vanishes."""
    applied, not_applied = [], []
    for name, mod, err in load_modules():
        ctx.dim = "general"
        if mod is None:
            ctx.record("module:%s" % name, "failed-to-run (module file is broken: %s)" % err, "-", "-")
            continue
        if not mod.applies(ctx):
            not_applied.append(name)
            continue
        applied.append(name)
        try:
            mod.run(ctx)
        except Exception as exc:   # one crashing module must not lose the others
            ctx.dim = "general"
            ctx.record("module:%s" % name, "failed-to-run (the check crashed: %s: %s)" % (type(exc).__name__, str(exc)[:120]), "-", "-")
    ctx.meta("modules_run=%s" % " ".join(applied))
    ctx.meta("modules_not_applicable=%s" % " ".join(not_applied))


def _check_consistency(ctx):
    """Did the project change while the scanners were running? Then the results may mix two versions."""
    ctx.refresh_files()
    start = [ln for ln in read_text(ctx.path("meta.txt")).splitlines() if ln.startswith("fingerprint_start=")][0].split("=", 1)[1]
    end = ctx.fingerprint()
    ctx.meta("fingerprint_end=%s" % end)
    ctx.meta("consistent=%s" % ("yes" if start == end else "no"))
    if start != end:
        ctx.dim = "general"
        ctx.record("consistency", "partial: project files changed while the scan was running, so results may mix two versions (run the scan again)", "-", "-")
    if ctx.is_git():
        ctx.meta("commit_end=%s" % (ctx.git("rev-parse", "--verify", "-q", "HEAD")[1].strip() or "none"))


def _write_digest_and_page(out):
    """A compact digest of the findings (findings.tsv, digest.txt) and one web page for the run (report.html)."""
    try:
        import audit_digest
        with contextlib.redirect_stdout(io.StringIO()):
            audit_digest.main(["audit_digest", out])
    except Exception:
        print("NOTE: digest.txt could not be built; read manifest.tsv and the tool outputs")
    try:
        import audit_report_html
        with contextlib.redirect_stdout(io.StringIO()):
            audit_report_html.main(["audit_report_html", out])
        print("Screen: %s/report.html  (open it in a browser, or run: bash scan.sh --open)" % posix(out))
    except Exception:
        pass


def scan(ctx):
    audit_dir = os.path.join(ctx.root, "audit")
    ctx.out = _new_run_folder(audit_dir)
    ctx.write("manifest.tsv", "tool\tstatus\texit\toutput\tdimension\n")
    ctx.write("versions.txt", "")
    audit_progress.write(ctx.out, "scanning")
    if os.environ.get("AUDIT_OPEN") == "1" and not os.environ.get("AUDIT_SUB"):
        open_progress(ctx.out)   # the page follows the scan and becomes the report
    write_meta(ctx)
    _record_trust_and_subprojects(ctx)
    _run_modules(ctx)
    _check_consistency(ctx)
    with open(os.path.join(audit_dir, "latest.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(posix(ctx.out) + "\n")
    _write_digest_and_page(ctx.out)
    coverage(ctx)
    audit_progress.write(ctx.out, "review")
    print()
    print("Profile: %s" % " ".join(ctx.traits))
    print("Done. Results saved in: %s" % posix(ctx.out))
    print(read_text(ctx.path("manifest.tsv")), end="")
    return 0


def run_all(ctx, rest):
    """Scans this folder (secrets, history and every general check cover the whole tree) and then every project
    folder from --projects, each in its own audit/ folder, so each one's stack is detected and gets its own checks."""
    summary_path = os.path.join(ctx.root, "audit", "all-latest.txt")
    os.makedirs(os.path.join(ctx.root, "audit"), exist_ok=True)
    script = os.path.join(HERE, "audit_scan.py")
    folders = ["."] + ctx.subprojects.split()
    for d in folders:
        print(("##### . (whole folder)" if d == "." else "\n##### %s" % d))
        sys.stdout.flush()
        env = dict(os.environ, AUDIT_ALL="1")
        if d != ".":
            env["AUDIT_SUB"] = "1"
        subprocess.call([sys.executable, script] + rest, cwd=os.path.join(ctx.root, d), env=env)
    rows = ["folder\tfindings\tpartial\tfailed\tskipped\ttraits"]
    for d in folders:
        latest = os.path.join(ctx.root, d, "audit", "latest.txt")
        if not os.path.isfile(latest):
            continue
        run_dir = read_text(latest).strip()
        f = p = x = s = 0
        for line in read_text(os.path.join(run_dir, "manifest.tsv")).splitlines()[1:]:
            st = line.split("\t")[1] if "\t" in line else ""
            if st == "findings":
                f += 1
            elif st.startswith("partial"):
                p += 1
            elif st.startswith("failed-to-run") or st == "timeout":
                x += 1
            elif st.startswith(("skipped", "unavailable")):
                s += 1
        traits = [ln.split("=", 1)[1] for ln in read_text(os.path.join(run_dir, "meta.txt")).splitlines() if ln.startswith("traits=")]
        rows.append("%s\t%d\t%d\t%d\t%d\t%s" % (d, f, p, x, s, traits[0] if traits else ""))
    text = "\n".join(rows) + "\n"
    with open(summary_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(text, end="")
    print("Combined summary saved in: %s" % posix(summary_path))
    return 0


BROWSER_NAMES = ["msedge", "chrome", "google-chrome", "chromium", "chromium-browser", "brave"]


def find_browser(names):
    """The first Chrome-family browser found on PATH or in its usual install folder, or None."""
    places = []
    if audit_core.is_windows():
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                places += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                           os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif sys.platform == "darwin":
        places += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                   "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                   "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for p in places:
        if os.path.isfile(p):
            return p
    return None


def app_window_command(page, finder=find_browser):
    """The command that opens the page in its own app-style window (no tabs, no address bar), like an installed web
    app. Chrome, Edge and other Chromium browsers support it. Empty when none is installed."""
    browser = finder(BROWSER_NAMES)
    if not browser:
        return []
    return [browser, "--app=" + pathlib.Path(os.path.abspath(page)).as_uri(), "--window-size=1100,800"]


def open_file(page):
    """Opens a file in its own browser window like a web app (Chrome or Edge), else in the default browser, or says
    where it is when there is no way to open it."""
    try:
        cmd = app_window_command(page)
        if cmd:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if audit_core.is_windows():
            os.startfile(page)  # type: ignore[attr-defined]
            return
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        if shutil.which(opener):
            subprocess.call([opener, page])
            return
    except OSError:
        pass
    print("Open this file in a browser: %s" % page)


PROGRESS_OPENED = "progress-opened.txt"


def open_progress(run_dir, opener=open_file):
    """Opens the live progress page and leaves a note, so the --open that follows does not open a second window."""
    opener(os.path.join(run_dir, "progress.html"))
    try:
        with open(os.path.join(run_dir, PROGRESS_OPENED), "w", encoding="utf-8", newline="\n") as f:
            f.write("progress.html was opened at the start; it turns into the report by itself\n")
    except OSError:
        pass


def open_report(run_dir, opener=open_file):
    """--open: opens report.html, unless the progress page opened at the start of this run is still the window (it
    switches to the report by itself). The note is used once, so a later --open opens the report again."""
    note = os.path.join(run_dir, PROGRESS_OPENED)
    if os.path.isfile(note):
        try:
            os.remove(note)
        except OSError:
            pass
        print("The page is already open in your browser and has switched to the report.")
        return
    opener(os.path.join(run_dir, "report.html"))


def find_run_dir(rest, cwd):
    """The audit run folder for the helper commands: the one given, else the folder we are standing in when it is a
    run folder, else the latest run of the project (looked up from here and then from each parent folder)."""
    if rest:
        return rest[0]
    here = os.path.abspath(cwd)
    if os.path.isfile(os.path.join(here, "manifest.tsv")) and os.path.isfile(os.path.join(here, "meta.txt")):
        return here
    while True:
        latest = os.path.join(here, "audit", "latest.txt")
        if os.path.isfile(latest):
            return read_text(latest).strip()
        parent = os.path.dirname(here)
        if parent == here:
            return ""
        here = parent


def delegate(mode, rest):
    """Modes that live in their own scripts."""
    run_dir = find_run_dir(rest, os.getcwd())
    if mode == "--verify-report":
        import audit_verify
        return audit_verify.main(["audit_verify"] + (rest or ([run_dir] if run_dir else [])))
    if mode == "--verdict":
        import audit_verdict
        return audit_verdict.main(["audit_verdict", run_dir])
    if not run_dir or not os.path.isdir(run_dir):
        print("No audit folder found. Run the scan first.")
        return 1
    if mode == "--translate":
        import audit_report_html
        import audit_translate
        code = audit_translate.main(["audit_translate", run_dir])
        return code or audit_report_html.main(["audit_report_html", run_dir])
    if mode == "--serve":
        import audit_serve
        return audit_serve.main(["audit_serve", run_dir, "--open"])
    import audit_report_html   # --report-html and --open
    if audit_report_html.main(["audit_report_html", run_dir]):
        return 1
    if mode == "--open":
        open_report(run_dir)
    return 0


def main(argv):
    # Plain "\n" line endings and UTF-8 on every system (Windows would otherwise write "\r\n"), so the output reads the same in a script
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(newline="\n", encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ctx, args = make_ctx(argv[1:])
    mode = args[0] if args else ""
    rest = args[1:]
    if mode in ("--verify-report", "--verdict", "--translate", "--serve", "--report-html", "--open"):
        return delegate(mode, rest)
    detect_project(ctx)
    if mode == "--detect":
        return audit_modes.detect(ctx)
    if mode == "--projects":
        return audit_modes.projects(ctx)
    if mode == "--all":
        return run_all(ctx, rest)
    if mode == "--check":
        return audit_modes.check(ctx)
    if mode == "--install":
        return audit_modes.install(ctx, rest)
    if mode == "--install-deps":
        return audit_modes.install_deps(ctx)
    if mode == "--status":
        return audit_modes.status(ctx)
    if mode == "--version":
        return audit_modes.version(ctx)
    if mode == "--add-gitignore":
        return audit_modes.add_gitignore(ctx)
    if mode.startswith("--"):
        print("Unknown option: %s (see the usage at the top of scan.sh)" % mode)
        return 2
    return scan(ctx)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
