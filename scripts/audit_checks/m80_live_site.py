"""The deployed site, when a URL is given (url= in .audit.conf, or AUDIT_URL for one run).
Only point this at sites you own or have the owner's permission to test.
  live-site    HTTPS redirect, security headers, files that must never be public (.env, .git),
               public source maps, certificate expiry. Response bodies are never saved.
  lighthouse   accessibility, SEO, performance and best-practice scores (needs Chrome)"""
import os
import re
import subprocess

from audit_core import LIGHTHOUSE_PKG

NAME = "80-live-site"


def applies(ctx):
    return ctx.has_trait("live-url")


def tools(ctx):
    return ["curl", "npx"]


def _curl(args, limit=None, merge_stderr=False):
    """Runs curl and returns its output as bytes (cut to `limit` bytes). Empty on any problem."""
    cmd = ["curl", "-s", "--max-time", "20", "-A", "project-audit"] + args
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return b""
    return p.stdout[:limit] if limit else p.stdout


def _text(raw):
    return raw.decode("utf-8", "replace")


def _http_code(url):
    return _text(_curl(["-o", os.devnull, "-w", "%{http_code}", "-L", url])).strip()


def _public_file(url, path, pattern, report):
    body = _text(_curl(["-L", url + path], limit=4000))
    if _http_code(url + path) == "200" and re.search(pattern, body, re.M) and "<html" not in body.lower():
        report.append("FAIL publicly readable: %s" % path)


def run(ctx):
    ctx.dim = "security"
    if not ctx.has("curl"):
        ctx.skip("live-site", "curl not found")
        ctx.skip("lighthouse", "curl not found")
        return

    url = ctx.audit_url.rstrip("/")
    scheme = url.split("://", 1)[0]
    host = url.split("://", 1)[-1].split("/", 1)[0]
    out = []

    # Reachable at all?
    code = _http_code(url)
    if not code or code == "000":
        ctx.record("live-site", "failed-to-run (could not reach %s)" % url, "-", "-")
        return
    out.append("INFO %s answered HTTP %s" % (url, code))

    # 1. Plain http should redirect to https
    redir = _text(_curl(["-o", os.devnull, "-w", "%{redirect_url}", "http://%s/" % host])).strip()
    if redir.startswith("https://"):
        out.append("OK   http:// redirects to https://")
    else:
        out.append("FAIL http://%s/ does not redirect to https:// (got: %s)" % (host, redir or "no redirect"))
    if scheme != "https":
        out.append("FAIL the audited URL is not https")

    # 2. Security headers on the final response
    headers = _text(_curl(["-o", os.devnull, "-D", "-", "-L", url])).replace("\r", "").lower().splitlines()
    for name in ("strict-transport-security", "content-security-policy", "x-content-type-options", "referrer-policy"):
        if any(h.startswith(name + ":") for h in headers):
            out.append("OK   header %s" % name)
        else:
            out.append("WARN missing header: %s" % name)
    if any(h.startswith("x-frame-options:") for h in headers) or any(re.match(r"^content-security-policy:.*frame-ancestors", h) for h in headers):
        out.append("OK   clickjacking protection (x-frame-options or frame-ancestors)")
    else:
        out.append("WARN no clickjacking protection (x-frame-options or CSP frame-ancestors)")
    for h in headers:
        if re.match(r"^(x-powered-by|server):", h):
            out.append("INFO reveals: %s" % h)

    # 3. Files that must never be public. The body is checked for the file's real content
    #    (many hosts answer 200 with the home page for any path) and never saved.
    found = []
    for path, pattern in (("/.env", r"^[A-Z_][A-Z0-9_]*="), ("/.env.local", r"^[A-Z_][A-Z0-9_]*="), ("/.env.production", r"^[A-Z_][A-Z0-9_]*="),
                          ("/.git/HEAD", r"^ref: "), ("/.git/config", r"\[core\]")):
        _public_file(url, path, pattern, found)
    out += found
    if not found:
        out.append("OK   no .env or .git files served")

    # 4. Public source maps (they hand out the original source code)
    page = _text(_curl(["-L", url], limit=2000000))
    scripts = re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"', page)[:5]
    maps = 0
    for js in scripts:
        if js.startswith("http"):
            pass
        elif js.startswith("//"):
            js = "%s:%s" % (scheme, js)
        elif js.startswith("/"):
            js = "%s://%s%s" % (scheme, host, js)
        else:
            js = "%s/%s" % (url, js)
        js = js.split("?", 1)[0]
        if _http_code(js + ".map") == "200" and '"version"' in _text(_curl([js + ".map"], limit=200)):
            out.append("WARN public source map: %s.map" % js)
            maps = 1
    if not maps:
        out.append("OK   no public source maps found (first 5 scripts checked)")

    # 5. Certificate expiry (best effort; curl's verbose format differs between systems)
    if scheme == "https":
        verbose = _text(_curl(["-v", "-o", os.devnull, url], merge_stderr=True))
        for line in verbose.splitlines():
            m = re.search(r"expire date: *(.*)", line, re.I)
            if m:
                out.append("INFO certificate expires: %s" % m.group(1).strip())
                break

    ctx.write("live-site.txt", "".join(ln + "\n" for ln in out))
    if any(ln.startswith(("FAIL", "WARN")) for ln in out):
        ctx.record("live-site", "findings", "-", "live-site.txt")
    else:
        ctx.record("live-site", "clean", "-", "live-site.txt")

    # Lighthouse
    ctx.dim = "quality"
    if ctx.has("npx"):
        ctx.note_version("lighthouse", LIGHTHOUSE_PKG)
        ctx.run("lighthouse", "lighthouse.json",
                ["npx", "--yes", LIGHTHOUSE_PKG, url, "--output=json", "--output-path=%s" % ctx.path("lighthouse.json"), "--quiet", "--chrome-flags=--headless=new"],
                done=True, json=True, stdout="lighthouse.log")
    else:
        ctx.skip("lighthouse", "npx not found (%s)" % ctx.install_hint("npx"))
