#!/usr/bin/env python3
"""Tests for trait detection (scripts/audit_detect.py): what each kind of project is recognised as.
Each case is a few files; the test builds a git repo from them and checks which traits appear.
Prints 'OK: label' or 'BAD: label | detail' per check."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import audit_core    # noqa: E402
import audit_detect  # noqa: E402


def say(ok, label, detail=""):
    print(("OK: " if ok else "BAD: ") + label + ("" if ok else " | " + str(detail)))


def pkg(**deps):
    return json.dumps({"name": "x", "version": "1.0.0", "dependencies": {k.replace("__", "-"): "1.0.0" for k in deps}})


def project(files):
    root = tempfile.mkdtemp(prefix="detect")
    for name, text in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    for cmd in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"], ["add", "-A"], ["commit", "-qm", "x", "--allow-empty"]):
        subprocess.run(["git"] + cmd, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return root


def detect(files, url=""):
    ctx = audit_core.Ctx(project(files), SCRIPTS)
    audit_detect.detect(ctx, url)
    audit_detect.find_subprojects(ctx)
    return ctx


# (label, files, traits that must be present, traits that must be absent)
CASES = [
    ("an Expo app", {"package.json": pkg(expo=1, react__native=1, react=1), "tsconfig.json": "{}"},
     "node expo react-native react mobile typescript", "web next flutter"),
    ("a Next.js site with Supabase, Stripe and an AI SDK", {"package.json": pkg(next=1, react=1, openai=1, stripe=1, **{"@supabase/supabase-js": 1}), "app/api/x/route.ts": "export {}"},
     "node next react web supabase payments ai server-code", "mobile expo"),
    ("a Vite React site is a website", {"package.json": pkg(vite=1, react=1)}, "node vite react web", "mobile server-code"),
    ("an Astro site", {"package.json": pkg(astro=1)}, "node astro web", "react mobile"),
    ("an Express API", {"package.json": pkg(express=1)}, "node server-framework server-code", "web mobile"),
    ("a Flask app with OpenAI", {"requirements.txt": "flask==3.0.0\nopenai==1.0.0\n", "app.py": "print(1)"},
     "python server-framework server-code ai", "node mobile"),
    ("a Django app with Stripe", {"requirements.txt": "Django>=4\nstripe\n"}, "python server-framework payments", "node"),
    ("a package name inside another word is not a match", {"requirements.txt": "flask-cors==4.0.0\nrequests\n"}, "python", "server-framework"),
    ("a Flutter app with Supabase", {"pubspec.yaml": "name: a\ndependencies:\n  flutter:\n    sdk: flutter\n  supabase_flutter: ^2.0.0\nflutter:\n  uses-material-design: true\nenvironment:\n  sdk: flutter\n",
                                    "lib/main.dart": "void main() {}"},
     "dart supabase mobile", "node"),
    ("a plain Dart package", {"pubspec.yaml": "name: a\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n"}, "dart", "flutter mobile"),
    ("WordPress", {"wp-config.php": "<?php", "wp-content/index.php": "<?php", "index.php": "<?php"}, "php wordpress web server-code", "node"),
    ("a static site", {"index.html": "<html></html>", "styles.css": "a{}"}, "static-site web", "node server-code"),
    ("Firebase configured by files, not packages", {"firebase.json": "{}", "firestore.rules": "rules_version = '2';"}, "firebase", "supabase"),
    ("Supabase configured by a folder", {"supabase/migrations/1.sql": "create table a(id int);"}, "supabase", "firebase"),
    ("serverless functions count as server code", {"package.json": pkg(react=1), "netlify/functions/a.js": "exports.handler = 1"}, "server-code web", ""),
    ("a monorepo", {"package.json": json.dumps({"name": "m", "workspaces": ["packages/*"]}), "pnpm-lock.yaml": "lockfileVersion: 9"}, "node monorepo pm-pnpm", "pm-npm"),
    ("each package manager is told apart", {"package.json": pkg(react=1), "package-lock.json": "{}"}, "pm-npm", "pm-pnpm pm-yarn pm-bun"),
    ("GitHub Actions and Docker", {".github/workflows/ci.yml": "name: ci", "Dockerfile": "FROM node:22", "package.json": pkg(react=1)}, "ci-github docker", ""),
    ("AI used through a plain HTTP call", {"package.json": pkg(express=1), "src/llm.js": "fetch('https://openrouter.ai/api/v1/chat/completions')"}, "ai", ""),
    ("an AI host mentioned only in docs is not AI use", {"package.json": pkg(express=1), "README.md": "see https://api.openai.com"}, "", "ai"),
    ("native Android code", {"android/build.gradle": "x", "android/app/build.gradle": "y"}, "native-android mobile", "expo"),
    ("a live URL makes the live-site check apply", {"package.json": pkg(react=1)}, "live-url", ""),
    ("an empty folder has no stack", {"README.md": "# x"}, "git", "node python dart php web mobile"),
]


def main():
    for label, files, present, absent in CASES:
        ctx = detect(files, url="https://example.com" if "live URL" in label else "")
        have = set(ctx.traits)
        missing = [t for t in present.split() if t not in have]
        extra = [t for t in absent.split() if t in have]
        say(not missing and not extra, label, "traits were %s; missing %s; unexpected %s" % (sorted(have), missing, extra))

    # project folders in subfolders
    ctx = detect({"README.md": "x", "backend/requirements.txt": "flask", "web/package.json": pkg(react=1), "docs/package.json": pkg(react=1)})
    say(ctx.subprojects.split() == ["backend", "docs", "web"] and not ctx.root_is_project, "folders with project files are found when the top folder has none", ctx.subprojects)
    ctx = detect({"package.json": pkg(react=1), "frontend/package.json": pkg(react=1), "docs/package.json": pkg(react=1),
                  "examples/a/package.json": pkg(react=1), "tests/x/package.json": pkg(react=1)})
    say(ctx.subprojects.split() == ["frontend"] and ctx.root_is_project, "docs, examples and tests folders are not counted as products", ctx.subprojects)
    ctx = detect({"package.json": json.dumps({"name": "m", "workspaces": ["packages/*"]}), "packages/a/package.json": pkg(react=1), "services/b/package.json": pkg(react=1)})
    say(ctx.subprojects == "" and ctx.has_trait("monorepo"), "monorepo packages are covered from the top, not listed as extra projects", ctx.subprojects)

    # language census
    ctx = detect({"a.ts": "1", "b.ts": "1", "c.py": "1", "d.go": "1", "e.go": "1", "f.go": "1", "g.go": "1", "h.go": "1"})
    say(ctx.langs.startswith("go(5)") and "ts(2)" in ctx.langs, "the language census counts files by extension", ctx.langs)
    say(ctx.unhandled == "go(5)", "a language with five or more files and no dedicated checks is reported", ctx.unhandled)
    ctx = detect({"a.go": "1"})
    say(ctx.unhandled == "", "a language with only a few files is not reported")

    # generated and vendored files do not count as the project's own code
    ctx = detect({"package.json": pkg(expo=1), "android/Generated.java": "x", "dist/a.js": "x", "src/a.ts": "x", "pnpm-lock.yaml": "x"})
    say(ctx.noise("android/Generated.java") and ctx.noise("dist/a.js") and ctx.noise("pnpm-lock.yaml") and not ctx.noise("src/a.ts"),
        "generated, built and lock files count as noise (android/ only for Expo and Flutter)")
    ctx = detect({"package.json": pkg(react=1), "android/Native.java": "x"})
    say(not ctx.noise("android/Native.java"), "android/ is the project's own code when the app is not Expo or Flutter")


if __name__ == "__main__":
    main()
