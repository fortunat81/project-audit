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


SECURITY_HEADERS = ("strict-transport-security", "content-security-policy", "x-content-type-options", "referrer-policy")
SECRET_FILE = r"^[A-Z_][A-Z0-9_]*="
# Files that must never be public, with what their real content looks like
PRIVATE_FILES = (("/.env", SECRET_FILE), ("/.env.local", SECRET_FILE), ("/.env.production", SECRET_FILE),
                 ("/.git/HEAD", r"^ref: "), ("/.git/config", r"\[core\]"))


def header_lines(headers):
    """Report lines for the security headers in a response (headers = lowercase 'name: value' lines)."""
    out = []
    for name in SECURITY_HEADERS:
        if any(h.startswith(name + ":") for h in headers):
            out.append("OK   header %s" % name)
        else:
            out.append("WARN missing header: %s" % name)
    if any(h.startswith("x-frame-options:") for h in headers) or any(re.match(r"^content-security-policy:.*frame-ancestors", h) for h in headers):
        out.append("OK   clickjacking protection (x-frame-options or frame-ancestors)")
    else:
        out.append("WARN no clickjacking protection (x-frame-options or CSP frame-ancestors)")
    out += ["INFO reveals: %s" % h for h in headers if re.match(r"^(x-powered-by|server):", h)]
    return out


def script_url(src, scheme, host, url):
    """The full address of a script found in the page, without its query string."""
    if src.startswith("//"):
        src = "%s:%s" % (scheme, src)
    elif src.startswith("/"):
        src = "%s://%s%s" % (scheme, host, src)
    elif not src.startswith("http"):
        src = "%s/%s" % (url, src)
    return src.split("?", 1)[0]


def _redirect_lines(host, scheme):
    redir = _text(_curl(["-o", os.devnull, "-w", "%{redirect_url}", "http://%s/" % host])).strip()
    if redir.startswith("https://"):
        out = ["OK   http:// redirects to https://"]
    else:
        out = ["FAIL http://%s/ does not redirect to https:// (got: %s)" % (host, redir or "no redirect")]
    if scheme != "https":
        out.append("FAIL the audited URL is not https")
    return out


def _private_file_lines(url):
    """The body is checked for the file's real content (many hosts answer 200 with the home page for any path) and never saved."""
    found = []
    for path, pattern in PRIVATE_FILES:
        _public_file(url, path, pattern, found)
    return found or ["OK   no .env or .git files served"]


def _source_map_lines(url, scheme, host):
    page = _text(_curl(["-L", url], limit=2000000))
    out = []
    for src in re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"', page)[:5]:
        js = script_url(src, scheme, host, url)
        if _http_code(js + ".map") == "200" and '"version"' in _text(_curl([js + ".map"], limit=200)):
            out.append("WARN public source map: %s.map" % js)
    return out or ["OK   no public source maps found (first 5 scripts checked)"]


def _certificate_lines(url):
    """Certificate expiry (best effort; curl's verbose format differs between systems)."""
    verbose = _text(_curl(["-v", "-o", os.devnull, url], merge_stderr=True))
    for line in verbose.splitlines():
        m = re.search(r"expire date: *(.*)", line, re.I)
        if m:
            return ["INFO certificate expires: %s" % m.group(1).strip()]
    return []


def _lighthouse(ctx, url):
    ctx.dim = "quality"
    if not ctx.has("npx"):
        ctx.skip("lighthouse", "npx not found (%s)" % ctx.install_hint("npx"))
        return
    ctx.note_version("lighthouse", LIGHTHOUSE_PKG)
    ctx.run("lighthouse", "lighthouse.json",
            ["npx", "--yes", LIGHTHOUSE_PKG, url, "--output=json", "--output-path=%s" % ctx.path("lighthouse.json"), "--quiet", "--chrome-flags=--headless=new"],
            done=True, json=True, stdout="lighthouse.log")


def run(ctx):
    ctx.dim = "security"
    if not ctx.has("curl"):
        ctx.skip("live-site", "curl not found")
        ctx.skip("lighthouse", "curl not found")
        return
    url = ctx.audit_url.rstrip("/")
    scheme = url.split("://", 1)[0]
    host = url.split("://", 1)[-1].split("/", 1)[0]
    code = _http_code(url)
    if not code or code == "000":
        ctx.record("live-site", "failed-to-run (could not reach %s)" % url, "-", "-")
        return
    headers = _text(_curl(["-o", os.devnull, "-D", "-", "-L", url])).replace("\r", "").lower().splitlines()
    out = ["INFO %s answered HTTP %s" % (url, code)]
    out += _redirect_lines(host, scheme)
    out += header_lines(headers)
    out += _private_file_lines(url)
    out += _source_map_lines(url, scheme, host)
    if scheme == "https":
        out += _certificate_lines(url)
    ctx.write("live-site.txt", "".join(ln + "\n" for ln in out))
    ctx.record("live-site", "findings" if any(ln.startswith(("FAIL", "WARN")) for ln in out) else "clean", "-", "live-site.txt")
    _lighthouse(ctx, url)
