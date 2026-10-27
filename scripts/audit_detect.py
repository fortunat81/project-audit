#!/usr/bin/env python3
"""Works out what the project is: its traits (expo, next, supabase, ai, ...), its main languages, the
languages with no dedicated checks, and project folders that sit in subfolders.
Standard library only (Python 3.8+)."""
import collections
import glob
import os
import re

from audit_core import read_text

AI_HOSTS = re.compile(r"api\.openai\.com|api\.anthropic\.com|openrouter\.ai|generativelanguage\.googleapis\.com|api\.groq\.com|api\.mistral\.ai"
                      r"|api\.cohere\.(ai|com)|api\.together\.(xyz|ai)|api\.replicate\.com|api\.deepseek\.com|api\.x\.ai|api\.perplexity\.ai")
PROJECT_FILE_RE = re.compile(r"(^|/)(package\.json|pyproject\.toml|requirements[^/]*\.txt|Pipfile|setup\.py|pubspec\.yaml|composer\.json)$")
NOT_PRODUCT_RE = re.compile(r"(^|/)(node_modules|test|tests|__tests__|e2e|example|examples|sample|samples|doc|docs|fixtures|fixture|demo|demos|vendor|android|ios)(/|$)")
UNHANDLED_EXTS = "go rb php cs rs c cpp scala ex lua java kt swift".split()


def _pkg_has(text, name):
    return re.search(r'"%s"\s*:' % re.escape(name), text) is not None


def _pkg_has_prefix(text, prefix):
    return re.search(r'"%s[^"]*"\s*:' % re.escape(prefix), text) is not None


def _py_has(ctx, name):
    text = ""
    for fn in ("pyproject.toml", "Pipfile", "setup.py"):
        text += ctx.read(fn) + "\n"
    for path in sorted(glob.glob(os.path.join(ctx.root, "requirements*.txt"))):
        text += read_text(path) + "\n"
    return re.search(r"(^|[^a-z0-9_-])%s([^a-z0-9_-]|$)" % re.escape(name), text, re.I | re.M) is not None


def _pub_has(text, name):
    return re.search(r"^\s+%s\s*:" % re.escape(name), text, re.M) is not None


def _javascript(ctx):
    if not ctx.isfile("package.json"):
        return
    pkg = ctx.read("package.json")
    ctx.add_trait("node")
    if ctx.isfile("package-lock.json") or ctx.isfile("npm-shrinkwrap.json"):
        ctx.add_trait("pm-npm")
    if ctx.isfile("pnpm-lock.yaml"):
        ctx.add_trait("pm-pnpm")
    if ctx.isfile("yarn.lock"):
        ctx.add_trait("pm-yarn")
    if ctx.isfile("bun.lockb") or ctx.isfile("bun.lock"):
        ctx.add_trait("pm-bun")
    if ctx.isfile("tsconfig.json"):
        ctx.add_trait("typescript")
    if any(ctx.isfile(f) for f in ("pnpm-workspace.yaml", "turbo.json", "nx.json", "lerna.json")) or '"workspaces"' in pkg:
        ctx.add_trait("monorepo")
    for name, trait in (("expo", "expo"), ("react-native", "react-native"), ("next", "next"), ("astro", "astro"), ("vite", "vite"),
                        ("nuxt", "nuxt"), ("vue", "vue")):
        if _pkg_has(pkg, name):
            ctx.add_trait(trait)
    if _pkg_has(pkg, "svelte") or _pkg_has(pkg, "@sveltejs/kit"):
        ctx.add_trait("svelte")
    if _pkg_has_prefix(pkg, "@remix-run/"):
        ctx.add_trait("remix")
    if _pkg_has(pkg, "react"):
        ctx.add_trait("react")
    if any(_pkg_has(pkg, s) for s in ("express", "fastify", "hono", "koa", "@nestjs/core")):
        ctx.add_trait("server-framework")
    ai = ("openai", "@anthropic-ai/sdk", "ai", "@google/generative-ai", "@google/genai", "groq-sdk", "cohere-ai", "replicate", "ollama",
          "@mistralai/mistralai", "langchain")
    if any(_pkg_has(pkg, s) for s in ai) or _pkg_has_prefix(pkg, "@ai-sdk/") or _pkg_has_prefix(pkg, "@langchain/"):
        ctx.add_trait("ai")
    if any(_pkg_has(pkg, s) for s in ("stripe", "@stripe/stripe-js", "@stripe/stripe-react-native", "@paypal/react-paypal-js", "square")):
        ctx.add_trait("payments")
    if _pkg_has(pkg, "@supabase/supabase-js"):
        ctx.add_trait("supabase")
    if any(_pkg_has(pkg, s) for s in ("firebase", "firebase-admin", "@react-native-firebase/app")):
        ctx.add_trait("firebase")


def _python(ctx):
    if not (ctx.isfile("pyproject.toml") or ctx.any_file("requirements*.txt") or ctx.isfile("Pipfile") or ctx.isfile("setup.py")):
        return
    ctx.add_trait("python")
    if any(_py_has(ctx, s) for s in ("django", "flask", "fastapi")):
        ctx.add_trait("server-framework")
    if any(_py_has(ctx, s) for s in ("openai", "anthropic", "langchain", "google-generativeai", "google-genai")):
        ctx.add_trait("ai")
    if _py_has(ctx, "stripe"):
        ctx.add_trait("payments")
    if _py_has(ctx, "supabase"):
        ctx.add_trait("supabase")
    if _py_has(ctx, "firebase-admin"):
        ctx.add_trait("firebase")


def _dart(ctx):
    if not ctx.isfile("pubspec.yaml"):
        return
    spec = ctx.read("pubspec.yaml")
    ctx.add_trait("dart")
    if re.search(r"sdk:\s*flutter", spec):
        ctx.add_trait("flutter")
    if any(_pub_has(spec, s) for s in ("google_generative_ai", "dart_openai", "firebase_vertexai", "firebase_ai", "anthropic_sdk_dart")):
        ctx.add_trait("ai")
    if _pub_has(spec, "supabase_flutter"):
        ctx.add_trait("supabase")
    if _pub_has(spec, "firebase_core"):
        ctx.add_trait("firebase")
    if _pub_has(spec, "flutter_stripe"):
        ctx.add_trait("payments")


def _ai_through_http(ctx):
    """AI used through a plain HTTP call: no SDK in the dependencies, but the code talks to an AI provider."""
    if ctx.has_trait("ai"):
        return
    ext = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs|py|dart|php)$")
    for f in ctx.project_files():
        if ctx.noise(f) or not ext.search(f):
            continue
        if AI_HOSTS.search(read_text(os.path.join(ctx.root, f), 2000000)):
            ctx.add_trait("ai")
            return


def detect(ctx, audit_url):
    if ctx.is_git():
        ctx.add_trait("git")
    _javascript(ctx)
    _python(ctx)
    _dart(ctx)

    # PHP / WordPress
    if ctx.isfile("composer.json") or any(f.endswith(".php") for f in ctx.project_files()):
        ctx.add_trait("php")
        if ctx.isfile("wp-config.php") or ctx.exists("wp-content"):
            ctx.add_trait("wordpress")

    # Backends configured by files rather than packages
    if ctx.exists("supabase") and os.path.isdir(os.path.join(ctx.root, "supabase")):
        ctx.add_trait("supabase")
    if any(ctx.isfile(f) for f in ("firebase.json", "firestore.rules", "database.rules.json", "storage.rules")):
        ctx.add_trait("firebase")

    _ai_through_http(ctx)

    # Native mobile code that is really yours (Expo and Flutter generate android/ and ios/)
    if not ctx.has_trait("expo") and not ctx.has_trait("flutter"):
        if os.path.isdir(os.path.join(ctx.root, "android")) and ctx.any_file("android/build.gradle*", "android/app/build.gradle*"):
            ctx.add_trait("native-android")
        if ctx.any_file("*.xcodeproj", "ios/*.xcodeproj", "Podfile", "ios/Podfile"):
            ctx.add_trait("native-ios")
    if any(ctx.has_trait(t) for t in ("expo", "react-native", "flutter", "native-android", "native-ios")):
        ctx.add_trait("mobile")

    # Websites
    if not ctx.has_trait("node") and (ctx.isfile("index.html") or ctx.isfile("public", "index.html")):
        ctx.add_trait("static-site")
    if any(ctx.has_trait(t) for t in ("next", "astro", "vite", "nuxt", "vue", "svelte", "remix", "static-site", "wordpress")):
        ctx.add_trait("web")
    if ctx.has_trait("react") and not ctx.has_trait("react-native") and not ctx.has_trait("expo"):
        ctx.add_trait("web")

    # Code that runs on a server (API routes, serverless functions, backend frameworks)
    if ctx.has_trait("server-framework"):
        ctx.add_trait("server-code")
    if ctx.has_trait("next") and any(os.path.isdir(os.path.join(ctx.root, d)) for d in ("app/api", "src/app/api", "pages/api", "src/pages/api")):
        ctx.add_trait("server-code")
    if (os.path.isdir(os.path.join(ctx.root, "supabase", "functions")) or ctx.isfile("functions", "package.json")
            or os.path.isdir(os.path.join(ctx.root, "netlify", "functions")) or os.path.isdir(os.path.join(ctx.root, "api"))):
        ctx.add_trait("server-code")
    if ctx.has_trait("php"):
        ctx.add_trait("server-code")

    # Other
    if ctx.any_file(".github/workflows/*.yml", ".github/workflows/*.yaml"):
        ctx.add_trait("ci-github")
    if ctx.any_file("Dockerfile", "*/Dockerfile", "docker-compose*.yml", "compose*.yml"):
        ctx.add_trait("docker")
    if audit_url:
        ctx.add_trait("live-url")

    _languages(ctx)
    _finish(ctx)


def _languages(ctx):
    """Language census by file extension, and the languages with many files but no dedicated module."""
    counts = collections.Counter()
    for f in ctx.project_files():
        m = re.search(r"\.([A-Za-z0-9]+)$", f)
        if m:
            counts[m.group(1).lower()] += 1
    top = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[:8]
    ctx.langs = " ".join("%s(%d)" % (ext, n) for ext, n in top)
    unhandled = []
    for ext in UNHANDLED_EXTS:
        if ext == "php" and ctx.has_trait("wordpress"):
            continue
        if ext in ("java", "kt") and ctx.has_trait("native-android"):
            continue
        if ext == "swift" and ctx.has_trait("native-ios"):
            continue
        n = sum(1 for f in ctx.project_files() if f.endswith("." + ext))
        if n >= 5:
            unhandled.append("%s(%d)" % (ext, n))
    ctx.unhandled = " ".join(unhandled)


def _finish(ctx):
    # Expo and Flutter generate android/ and ios/; that code isn't the user's.
    if ctx.has_trait("expo") or ctx.has_trait("flutter"):
        ctx.noise_re += "|^(android|ios)/"
        ctx.jscpd_ignore += ",**/android/**,**/ios/**"
    if ctx.conf_ignore:
        ctx.jscpd_ignore += "," + ctx.conf_ignore


def find_subprojects(ctx):
    """Project folders up to 3 levels down that hold project files (empty if none). When this folder is itself
    a project, test/example/docs folders and monorepo packages are left out: they are covered from here or
    aren't the product."""
    ctx.root_is_project = bool(ctx.isfile("package.json") or ctx.isfile("pyproject.toml") or ctx.isfile("Pipfile") or ctx.isfile("setup.py")
                               or ctx.isfile("pubspec.yaml") or ctx.isfile("composer.json") or ctx.any_file("requirements*.txt"))
    if ctx.is_git():
        files = ctx.project_files()
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(ctx.root):
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", "audit")]
            depth = os.path.relpath(dirpath, ctx.root).count(os.sep)
            if depth > 3:
                dirnames[:] = []
                continue
            for fn in filenames:
                files.append(os.path.relpath(os.path.join(dirpath, fn), ctx.root).replace("\\", "/"))
    dirs = set()
    for f in files:
        if PROJECT_FILE_RE.search(f) and "/" in f:
            d = f.rsplit("/", 1)[0]
            if d.count("/") + 1 <= 3:
                dirs.add(d)
    found = sorted(dirs)
    if ctx.root_is_project:
        found = [d for d in found if not NOT_PRODUCT_RE.search(d)]
        if ctx.has_trait("monorepo"):
            found = [d for d in found if not re.match(r"^(packages|apps|libs|services)/", d)]
    ctx.subprojects = " ".join(found[:20])
