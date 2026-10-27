"""Secrets that get bundled into the app or website, and .env hygiene.
Variables with these prefixes are copied into the code users download (EXPO_PUBLIC_, NEXT_PUBLIC_,
VITE_, REACT_APP_, ...). A secret there is readable by anyone. Only NAMES are reported, never values."""
import glob
import os
import re

from audit_core import read_text

NAME = "55-exposed-keys"

CLIENT_PREFIX = r"(EXPO_PUBLIC_|NEXT_PUBLIC_|VITE_|REACT_APP_|NUXT_PUBLIC_|PUBLIC_|GATSBY_|STORYBOOK_)"
SECRETISH = (r"(SECRET|PRIVATE|SERVICE_ROLE|PASSWORD|PASSWD|OPENAI|ANTHROPIC|CLAUDE|GEMINI|GROQ|MISTRAL|COHERE|REPLICATE|"
             r"STRIPE_SECRET|SK_LIVE|TOKEN|API_KEY|APIKEY|ADMIN|WEBHOOK)")
CLIENT_VISIBLE = re.compile(CLIENT_PREFIX + r"[A-Z0-9_]*" + SECRETISH + r"[A-Z0-9_]*")
APP_CONFIG = re.compile(r'"?[A-Za-z0-9_]*(secret|api_?key|token|password|private)[A-Za-z0-9_]*"?\s*:', re.I)
ENV_COMMITTED = re.compile(r"(^|/)\.env(\.[A-Za-z0-9_-]+)?$")
ENV_TEMPLATE = re.compile(r"\.(example|sample|template|dist|defaults)$")


def applies(ctx):
    return True


def _env_files(ctx):
    """.env and .env.* in the project folder (ignored .env files are still bundled)."""
    names = []
    for pattern in (".env", ".env.*"):
        names += [os.path.basename(p) for p in glob.glob(os.path.join(ctx.root, pattern)) if os.path.isfile(p)]
    return names


def _client_visible(ctx):
    files = [f for f in ctx.source_files() if not re.search(r"\.(md|lock)$", f)]
    files = sorted(set(files) | set(_env_files(ctx)))
    hits = set()
    for f in files:
        for n, line in enumerate(read_text(os.path.join(ctx.root, f), 2000000).splitlines(), 1):
            for m in CLIENT_VISIBLE.finditer(line):
                hits.add("CLIENT-VISIBLE: %s:%d:%s" % (f, n, m.group(0)))   # the variable NAME only
    lines = sorted(hits)
    # Expo config "extra" is bundled into the app too
    for f in ("app.json", "app.config.js", "app.config.ts"):
        if not ctx.isfile(f):
            continue
        for n, line in enumerate(ctx.read(f).splitlines(), 1):
            for m in APP_CONFIG.finditer(line):
                lines.append("IN APP CONFIG (bundled): %s:%d:%s" % (f, n, m.group(0)))
    ctx.write("exposed-keys.txt", "".join(ln + "\n" for ln in lines))
    ctx.result("exposed-keys", "exposed-keys.txt")


def _env_hygiene(ctx):
    """Committed .env files, and .env files git would pick up."""
    lines = []
    if ctx.is_git():
        tracked = ctx.git("ls-files")[1].splitlines()
        for f in tracked:
            if ENV_COMMITTED.search(f) and not ENV_TEMPLATE.search(f):
                lines.append("COMMITTED TO GIT (rotate what it held): %s" % f)
        for f in (".env", ".env.local", ".env.production", ".env.development"):
            if not ctx.isfile(f) or f in tracked:
                continue   # a committed one is already reported above
            if ctx.git("check-ignore", "-q", f)[0] != 0:
                lines.append("NOT GIT-IGNORED (one 'git add .' from being committed): %s" % f)
    ctx.write("env-files.txt", "".join(ln + "\n" for ln in lines))
    ctx.result("env-files", "env-files.txt")


def run(ctx):
    ctx.dim = "security"
    _client_visible(ctx)
    _env_hygiene(ctx)
