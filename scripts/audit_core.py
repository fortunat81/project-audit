#!/usr/bin/env python3
"""Core of the scanner: the run context, how tools are started and how their results are recorded.

A scan writes everything into audit/<run>/. Each tool ends as one row in manifest.tsv:
    tool, status, exit code, output file, score dimension(s)
Statuses: clean, findings, done (a measurement), partial, failed-to-run, timeout, skipped, unavailable.
A crash must never look like "findings", and "findings" must never look like "clean": run() decides the
status from the tool's real exit code and the shape of its output.
Standard library only (Python 3.8+).
"""
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import site
import subprocess
import sys
import time

TIMEOUT_SECONDS = 300

# Tools fetched with npx are pinned so results don't change between audits just because a new version
# came out. Bump these on purpose; every run records the versions in versions.txt.
MADGE_PKG = "madge@8.0.0"
JSCPD_PKG = "jscpd@5.4.1"
KNIP_PKG = "knip@6.9.0"
LIGHTHOUSE_PKG = "lighthouse@13.4.1"

# Lines in lockfiles, minified, binary or generated files are noise when measuring size or change.
# Whole-name matches, so Clock.tsx or blocks/list.ts are NOT mistaken for lockfiles.
NOISE_RE_BASE = (r"(^|/)(package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|Cargo\.lock|Gemfile\.lock|poetry\.lock|composer\.lock|Podfile\.lock|pubspec\.lock)$"
                 r"|\.min\.(js|css)$|\.(svg|png|jpe?g|gif|ico|webp|ttf|otf|woff2?|pdf|mp4|mov|mp3|wav|zip)$|\.(g|freezed|gen|mocks)\.dart$"
                 r"|(^|/)(\.expo|\.next|\.nuxt|\.svelte-kit|\.astro|\.dart_tool|dist|build|out|coverage|Pods|vendor)/")
JSCPD_IGNORE_BASE = ("**/node_modules/**,**/dist/**,**/build/**,**/out/**,**/coverage/**,**/.expo/**,**/.next/**,**/.nuxt/**,**/.svelte-kit/**,**/.astro/**,"
                     "**/.dart_tool/**,**/Pods/**,**/vendor/**,**/audit/**,**/*.min.js,**/*.g.dart,**/*.freezed.dart,**/*.gen.dart,**/*.lock,"
                     "**/package-lock.json,**/pnpm-lock.yaml")

SECRET_ENV_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|^AWS_|^GH_|^GITHUB_|^NPM_|^AZURE_|^SSH_AUTH_SOCK$", re.I)


def is_windows():
    return os.name == "nt"


def posix(path):
    """A path with forward slashes: works in Git Bash and in Windows programs alike."""
    return str(path).replace("\\", "/")


def extend_path():
    """A tool just installed with winget or "pip --user" may not be on PATH until the terminal restarts
    (or ever). Look in the places those installers use. Added at the END of PATH, so nothing already
    installed gets replaced."""
    extra = []
    home = os.path.expanduser("~")
    if is_windows():
        local = os.environ.get("LOCALAPPDATA")
        if local:
            winget = os.path.join(local, "Microsoft", "WinGet")
            extra.append(os.path.join(winget, "Links"))
            for pattern in ("Gitleaks.Gitleaks_*", "Google.OSVScanner_*"):
                extra += glob.glob(os.path.join(winget, "Packages", pattern))
        appdata = os.environ.get("APPDATA")
        if appdata:
            extra += glob.glob(os.path.join(appdata, "Python", "Python*", "Scripts"))
        if local:   # the Microsoft Store Python keeps its "pip --user" packages inside its own folder
            extra += glob.glob(os.path.join(local, "Packages", "PythonSoftwareFoundation.Python.*", "LocalCache", "local-packages", "Python*", "Scripts"))
        extra.append(os.path.join(site.getuserbase(), "Scripts"))   # wherever this Python puts "pip --user" tools
    extra.append(os.path.join(home, ".local", "bin"))
    extra += glob.glob(os.path.join(home, "Library", "Python", "*", "bin"))
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for d in extra:
        if os.path.isdir(d) and d not in parts:
            parts.append(d)
    os.environ["PATH"] = os.pathsep.join(parts)


def _is_script(path):
    """A file that starts with #! (bash can run it; Windows cannot start it directly)."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def find_executable(name, path=None):
    """Like shutil.which, but on Windows it also finds extensionless shell scripts (a '#!' file on PATH, the way
    bash would), in PATH order. Returns (path, needs_bash) or (None, False)."""
    path = os.environ.get("PATH", "") if path is None else path
    if not is_windows():
        found = shutil.which(name, path=path)
        return (found, False) if found else (None, False)
    exts = [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e]
    for d in path.split(os.pathsep):
        if not d:
            continue
        exact = os.path.join(d, name)
        if os.path.isfile(exact) and _is_script(exact):
            return exact, True
        for e in exts:
            cand = exact + e.lower()
            if os.path.isfile(cand):
                return cand, False
            if os.path.isfile(exact + e):
                return exact + e, False
    return None, False


def hash_text(text):
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]  # nosemgrep: a short label to compare two moments, not a security use


def json_looking(path):
    """Does the file start like JSON?"""
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return False
    return head.lstrip(b" \t\r\n")[:1] in (b"{", b"[")


def read_text(path, limit=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read() if limit is None else f.read(limit)
    except OSError:
        return ""


class Ctx:
    """Everything a check module needs: where the project is, what it is, where results go."""

    def __init__(self, root, script_dir):
        self.root = root
        self.script_dir = script_dir
        self.traits = []
        self.langs = ""
        self.unhandled = ""
        self.noise_re = NOISE_RE_BASE
        self.jscpd_ignore = JSCPD_IGNORE_BASE
        self.subprojects = ""
        self.root_is_project = False
        self.out = None
        self.dim = "general"
        self._git = None
        self._files = None
        self.read_conf()
        self.untrusted = False
        self.npx_env = {}

    # --- settings (.audit.conf is read as text, never executed)
    def conf_get(self, key):
        found = ""
        for line in read_text(os.path.join(self.root, ".audit.conf")).splitlines():
            m = re.match(r"^\s*%s\s*=(.*)$" % re.escape(key), line)
            if m:
                found = m.group(1).strip()
        return found

    def read_conf(self):
        self.audit_url = os.environ.get("AUDIT_URL") or self.conf_get("url")
        self.conf_skip = {s for s in self.conf_get("skip").replace(" ", "").split(",") if s}
        self.conf_ignore = self.conf_get("ignore").replace(" ", "")

    def skip_file_tools(self):
        """Tools the user asked never to be offered again (audit/.skip-tools)."""
        return {ln.strip() for ln in read_text(os.path.join(self.root, "audit", ".skip-tools")).splitlines() if ln.strip()}

    # --- untrusted mode: for code you did not write
    def set_untrusted(self, on):
        self.untrusted = bool(on)
        self.npx_env = {}
        if self.untrusted:
            os.environ["AUDIT_UNTRUSTED"] = "1"
            # Keys, tokens and passwords in the environment are not needed by any read-only check
            for name in list(os.environ):
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name) and SECRET_ENV_RE.search(name) and not name.startswith("AUDIT_"):
                    del os.environ[name]
            # npx tools: ignore a project .npmrc's registry and never run install scripts
            self.npx_env = {"npm_config_ignore_scripts": "true", "npm_config_registry": "https://registry.npmjs.org/"}

    def shadowed(self, tool):
        """A program of this name shipped inside the project would win over the pinned npx download."""
        return self.untrusted and os.path.exists(os.path.join(self.root, "node_modules", ".bin", tool))

    # --- the project
    def has(self, tool):
        return find_executable(tool)[0] is not None

    def has_trait(self, trait):
        return trait in self.traits

    def add_trait(self, trait):
        if trait not in self.traits:
            self.traits.append(trait)

    def exists(self, *parts):
        return os.path.exists(os.path.join(self.root, *parts))

    def isfile(self, *parts):
        return os.path.isfile(os.path.join(self.root, *parts))

    def read(self, *parts):
        return read_text(os.path.join(self.root, *parts))

    def any_file(self, *patterns):
        return any(glob.glob(os.path.join(self.root, p)) for p in patterns)

    def git(self, *args):
        """Runs git in the project; returns (exit code, stdout text)."""
        try:
            p = subprocess.run(["git", "-c", "core.quotepath=false"] + list(args), cwd=self.root, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except OSError:
            return 127, ""
        return p.returncode, p.stdout.decode("utf-8", "replace")

    def is_git(self):
        if self._git is None:
            self._git = self.git("rev-parse", "--git-dir")[0] == 0
        return self._git

    def project_files(self):
        """Every file that counts as part of the project: tracked plus new files git doesn't ignore.
        The audit's own output folder is never part of the project. Empty when this is not a git repo."""
        if self._files is None:
            self._files = []
            if self.is_git():
                code, text = self.git("ls-files", "--cached", "--others", "--exclude-standard")
                self._files = [ln for ln in text.splitlines() if ln and not ln.startswith("audit/")]
        return self._files

    def refresh_files(self):
        self._files = None

    def noise(self, path):
        return re.search(self.noise_re, path) is not None

    def source_files(self):
        return [f for f in self.project_files() if not self.noise(f)]

    # --- results
    def path(self, name):
        return os.path.join(self.out, name)

    def write(self, name, text):
        os.makedirs(os.path.dirname(self.path(name)), exist_ok=True)
        with open(self.path(name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def append(self, name, text):
        with open(self.path(name), "a", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def meta(self, line):
        self.append("meta.txt", line + "\n")

    def note_version(self, tool, text):
        text = (text or "").strip().splitlines()
        if text and text[0].strip():
            self.append("versions.txt", "%s\t%s\n" % (tool, text[0].strip()))

    def record(self, name, status, code, output):
        self.append("manifest.tsv", "%s\t%s\t%s\t%s\t%s\n" % (name, status, code, output, self.dim))

    def drop_last_record(self):
        """Removes the last manifest row (used when a tool is run again after a crash)."""
        lines = read_text(self.path("manifest.tsv")).splitlines()
        self.write("manifest.tsv", "\n".join(lines[:-1]) + "\n")

    def last_record(self):
        lines = read_text(self.path("manifest.tsv")).splitlines()
        return lines[-1].split("\t") if len(lines) > 1 else []

    def amend_last_status(self, prefix):
        """Puts `prefix` in front of the last manifest row's status."""
        lines = read_text(self.path("manifest.tsv")).splitlines()
        cols = lines[-1].split("\t")
        cols[1] = prefix + cols[1]
        lines[-1] = "\t".join(cols)
        self.write("manifest.tsv", "\n".join(lines) + "\n")

    def skip(self, name, reason):
        print("==> %s (skipped: %s)" % (name, reason))
        self.record(name, "skipped: %s" % reason, "-", "-")

    def result(self, name, outfile):
        """Record the result of a check done by the script itself (no external tool): findings if the file has content."""
        text = read_text(self.path(outfile))
        self.record(name, "findings" if text else "clean", "-", outfile)

    def grep_count(self, outfile):
        return sum(1 for ln in read_text(self.path(outfile)).splitlines() if ln.strip())

    # --- starting tools
    def command(self, argv, env):
        """argv ready to start. Handles what Windows cannot start directly: npx/npm (cmd shims, where a '|' in an
        argument would reach cmd.exe) and shell-script shims (a '#!' file such as node_modules/.bin/tsc)."""
        argv = list(argv)
        exe = argv[0]
        if is_windows():
            if os.path.basename(exe).lower() in ("npx", "npm"):
                node = find_executable("node", env.get("PATH"))[0]
                if node:
                    cli = os.path.join(os.path.dirname(node), "node_modules", "npm", "bin", "%s-cli.js" % os.path.basename(exe).lower())
                    if os.path.exists(cli):
                        return [node, cli] + argv[1:]
            local = exe if os.path.isabs(exe) else os.path.join(self.root, exe)
            has_dir = "/" in exe or "\\" in exe
            found, needs_bash = (local, _is_script(local)) if has_dir and os.path.isfile(local) else find_executable(exe, env.get("PATH"))
            if found and needs_bash:
                bash = find_executable("bash", env.get("PATH"))[0]
                if bash:
                    env["MSYS"] = "noglob"   # Git Bash would otherwise expand wildcards such as audit/** in the arguments
                    return [bash, found] + argv[1:]
            if found:
                argv[0] = found
            return argv
        resolved = find_executable(exe, env.get("PATH"))[0]
        if resolved is None and os.path.isfile(os.path.join(self.root, exe)):
            resolved = os.path.join(self.root, exe)
        argv[0] = resolved or exe
        return argv

    def exec_to_files(self, argv, out_path, err_path, env=None, cwd=None):
        """Starts a tool with its output in files. Returns its exit code (124 on timeout, 127 if it cannot start)."""
        full_env = dict(os.environ)
        full_env.update(self.npx_env)
        full_env.update(env or {})
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            try:
                cmd = self.command(argv, full_env)
                proc = subprocess.Popen(cmd, cwd=cwd or self.root, stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=full_env)
            except OSError as exc:
                err.write(("could not start %s: %s\n" % (argv[0], exc)).encode("utf-8", "replace"))
                return 127
            try:
                return proc.wait(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                return 124

    def run(self, name, file, argv, codes=(1,), ok=(), json=False, match=None, empty=None, stdout=None, done=False, env=None, cwd=None):
        """Runs a tool and records how it ended.
        codes   exit codes that mean "ran and found problems" (default: 1)
        ok      extra exit codes that mean "ran, nothing to report" (recorded as clean)
        json    the output must look like JSON, or the run counts as failed
        match   on a findings exit code, the output must match this regex (for example 'error TS')
        empty   decide by content instead of exit code: output matching this regex means clean
        stdout  send console text to this file (for tools that write their own report to <file>)
        done    the tool measures rather than judges: success is recorded as "done"
        stderr always goes to <file>.err. Respects skip= in .audit.conf. Returns the status."""
        if name in self.conf_skip:
            self.skip(name, "turned off in .audit.conf")
            return "skipped"
        if done:
            codes = ()
        print("==> %s" % name)
        out_path = self.path(stdout or file)
        err_path = self.path(file + ".err")
        code = self.exec_to_files(argv, out_path, err_path, env=env, cwd=cwd)
        target = self.path(file)
        looks_json = json_looking(target) if json else True
        if code == 124:
            status = "timeout"
        elif code in ok:
            status = "clean"
        elif empty is not None and (code == 0 or code in codes):
            if not looks_json:
                status = "failed"
            else:
                status = "clean" if re.search(empty, read_text(target)) else "findings"
        elif code == 0:
            status = "failed" if not looks_json else ("done" if done else "clean")
        elif code in codes:
            if not looks_json:
                status = "failed"
            elif match is not None and not re.search(match, read_text(target)):
                status = "failed"
            else:
                status = "findings"
        else:
            status = "failed"
        if status == "failed":
            status = "failed-to-run (see %s.err)" % file
        self.record(name, status, code, file)
        return status

    def run_text(self, argv, env=None, cwd=None, timeout=60):
        """Runs a small command and returns its text output ('' if it cannot run). For version strings and similar."""
        full_env = dict(os.environ)
        full_env.update(env or {})
        try:
            p = subprocess.run(self.command(argv, full_env), cwd=cwd or self.root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=full_env, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return p.stdout.decode("utf-8", "replace")

    # --- hints for installing tools
    def py_install_cmd(self, pkg):
        if self.has("pipx"):
            return "pipx install %s" % pkg
        if self.has("pip3"):
            return "pip3 install --user %s" % pkg
        if self.has("pip"):
            return "pip install --user %s" % pkg
        if self.has("py"):
            return "py -m pip install --user %s" % pkg
        return "install Python 3 first (https://www.python.org/downloads/), then: pipx install %s" % pkg

    def install_hint(self, tool):
        if tool == "semgrep":
            if self.has("pipx"):
                return "pipx install semgrep"
            if self.has("brew"):
                return "brew install semgrep"
            return self.py_install_cmd("semgrep")
        if tool == "gitleaks":
            if is_windows() and self.has("winget"):
                return "winget install -e --id Gitleaks.Gitleaks"
            if self.has("brew"):
                return "brew install gitleaks"
            if self.has("go"):
                return "go install github.com/gitleaks/gitleaks/v8@latest"
            return "download the release for your system from https://github.com/gitleaks/gitleaks/releases and put the gitleaks file in a folder on your PATH"
        if tool == "osv-scanner":
            if is_windows() and self.has("winget"):
                return "winget install -e --id Google.OSVScanner"
            if self.has("brew"):
                return "brew install osv-scanner"
            if self.has("go"):
                return "go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest"
            return "download the release for your system from https://github.com/google/osv-scanner/releases and put it on your PATH"
        if tool in ("ruff", "zizmor"):
            if self.has("pipx"):
                return "pipx install %s" % tool
            if self.has("brew"):
                return "brew install %s" % tool
            return self.py_install_cmd(tool)
        if tool in ("pip-audit", "lizard", "mobsfscan"):
            return self.py_install_cmd(tool)
        if tool == "git":
            if is_windows() and self.has("winget"):
                return "winget install -e --id Git.Git"
            if self.has("brew"):
                return "brew install git"
            return "install Git from https://git-scm.com/downloads (on Linux, with your package manager, for example: apt install git)"
        return {
            "npx": "install Node.js from https://nodejs.org (it provides npm and npx)",
            "flutter": "install the Flutter SDK from https://docs.flutter.dev/get-started/install",
            "dart": "install the Dart SDK from https://dart.dev/get-dart",
            "curl": "install curl (it ships with Git for Windows and macOS)",
        }.get(tool, "")

    # --- provenance
    def fingerprint(self):
        """A fingerprint of the project files as they are right now (commit, edits, new files and their sizes).
        The audit's own folder is left out."""
        parts = []
        if self.is_git():
            parts.append(self.git("rev-parse", "HEAD")[1])
            parts.append(self.git("diff", "HEAD", "--", ".", ":!audit")[1])
            code, text = self.git("ls-files", "--others", "--exclude-standard")
            for f in sorted(ln for ln in text.splitlines() if ln and not ln.startswith("audit/")):
                try:
                    parts.append("%s %d\n" % (f, os.path.getsize(os.path.join(self.root, f))))
                except OSError:
                    pass
        else:
            seen = 0
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", "audit")]
                for fn in sorted(filenames):
                    rel = posix(os.path.relpath(os.path.join(dirpath, fn), self.root))
                    parts.append("%s %d\n" % (rel, os.path.getsize(os.path.join(dirpath, fn))))
                    seen += 1
                if seen > 5000:
                    break
        return hash_text("".join(parts))

    def os_name(self):
        return "%s %s" % (platform.system() or "unknown", platform.machine() or "")


def kill_tree(proc):
    """Stops a process and the programs it started (npx starts node, which starts the real tool)."""
    try:
        if is_windows():
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc.kill()
    except OSError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def json_load(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def log(*args):
    print(*args)
    sys.stdout.flush()


def now_stamp():
    return time.strftime("%Y-%m-%d_%H%M%S")
