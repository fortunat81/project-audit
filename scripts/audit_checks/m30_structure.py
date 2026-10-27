"""Structure: circular imports, duplication, function complexity, biggest files, folder sizes, docs facts.
Scans the whole project (not one guessed folder), leaving out generated and vendored code."""
import collections
import os
import re
import shutil

from audit_core import JSCPD_PKG, MADGE_PKG, read_text

NAME = "30-structure"

LIZARD_EXCLUDE_DIRS = "node_modules dist build out coverage audit .git .expo .next .nuxt .svelte-kit .dart_tool Pods vendor".split()
MADGE_EXCLUDE = r"(^|/)(node_modules|dist|build|out|coverage|audit|\.expo|\.next|\.nuxt|\.svelte-kit|android|ios)/"
SOURCE_EXT = re.compile(r"\.(ts|tsx|js|jsx|mjs|vue|svelte|astro|py|dart|swift|kt|java|php|rb|go)$")
TEST_FILE = re.compile(r"(\.test\.|\.spec\.|_test\.|__tests__|(^|/)tests?/)")


def applies(ctx):
    return True


def tools(ctx):
    return ["npx", "lizard"]   # madge and jscpd run through npx; lizard measures function complexity (not Dart)


def _circular_imports(ctx):
    ctx.dim = "architecture,modularity,spaghettiness"
    if not ctx.has_trait("node"):
        return
    if ctx.shadowed("madge"):
        ctx.skip("madge-circular", "untrusted mode: the project ships its own madge program in node_modules")
    elif ctx.has("npx"):
        args = ["npx", "--yes", MADGE_PKG, "--circular", "--json", "--extensions", "ts,tsx,js,jsx,mjs,cjs"]
        if ctx.isfile("tsconfig.json"):
            args += ["--ts-config", "tsconfig.json"]   # follows @/ path aliases
        ctx.note_version("madge", MADGE_PKG)
        ctx.run("madge-circular", "madge-circular.json", args + ["--exclude", MADGE_EXCLUDE, "."], json=True)
    else:
        ctx.skip("madge-circular", "npx not found (%s)" % ctx.install_hint("npx"))


def _duplication(ctx):
    ctx.dim = "spaghettiness"
    if ctx.shadowed("jscpd"):
        ctx.skip("jscpd", "untrusted mode: the project ships its own jscpd program in node_modules")
    elif ctx.has("npx"):
        ctx.note_version("jscpd", JSCPD_PKG)
        os.makedirs(ctx.path("jscpd"), exist_ok=True)
        ctx.run("jscpd", "jscpd/jscpd-report.json",
                ["npx", "--yes", JSCPD_PKG, ".", "--reporters", "json", "--output", ctx.path("jscpd"), "--silent", "--ignore", ctx.jscpd_ignore + ",**/.git/**"],
                done=True, stdout="jscpd.log")
    else:
        ctx.skip("jscpd", "npx not found (%s)" % ctx.install_hint("npx"))


def _complexity(ctx):
    ctx.dim = "spaghettiness,modularity"
    if not ctx.has("lizard"):
        ctx.skip("lizard", "not installed (%s)" % ctx.install_hint("lizard"))
        return
    ctx.note_version("lizard", ctx.run_text(["lizard", "--version"]))
    args = ["-w", "-C", "15", "-L", "100"]   # warn on complexity above 15 or functions over 100 lines of code
    for d in LIZARD_EXCLUDE_DIRS:
        args += ["-x", "*/%s/*" % d]
    if ctx.has_trait("expo") or ctx.has_trait("flutter"):
        args += ["-x", "./android/*", "-x", "./ios/*"]
    status = ctx.run("lizard", "lizard.txt", ["lizard"] + args + ["."], match="warning")
    # lizard's JavaScript parser can crash on one odd file (unbalanced braces in vendored or generated
    # code) and then reports nothing at all. Retry without JavaScript, and say so.
    if status.startswith("failed-to-run") and "Traceback" in read_text(ctx.path("lizard.txt.err")):
        ctx.drop_last_record()
        shutil.copy(ctx.path("lizard.txt.err"), ctx.path("lizard-crash.err"))
        again = ctx.run("lizard", "lizard.txt", ["lizard"] + args + ["-x", "*.js", "-x", "*.jsx", "-x", "*.mjs", "-x", "*.cjs", "."], match="warning")
        if again in ("clean", "findings"):
            ctx.amend_last_status("partial: JavaScript files left out because lizard crashed on one (see lizard-crash.err); ")


def _sizes(ctx):
    ctx.dim = "modularity,spaghettiness"
    if not ctx.is_git():
        ctx.skip("biggest-files", "not a git repo")
        return
    sizes = []
    for f in ctx.source_files():
        try:
            with open(os.path.join(ctx.root, f), "rb") as fh:
                sizes.append((fh.read().count(b"\n"), f))
        except OSError:
            continue
    top = sorted(sizes, reverse=True)[:30]
    ctx.write("biggest-files.txt", "".join("%7d %s\n" % (n, f) for n, f in top))
    ctx.record("biggest-files", "done", 0, "biggest-files.txt")
    ctx.dim = "architecture"
    per_folder = collections.Counter(f.rsplit("/", 1)[0] if "/" in f else "." for f in ctx.source_files())
    ranked = sorted(per_folder.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[:15]
    ctx.write("files-per-folder.txt", "".join("%7d %s\n" % (n, d) for d, n in ranked))
    ctx.record("files-per-folder", "done", 0, "files-per-folder.txt")


def _docs_facts(ctx):
    ctx.dim = "documentation"
    files = ctx.project_files()
    readme = ctx.isfile("README.md")
    lines = [
        "readme_exists=%s" % ("yes" if readme else "no"),
        "readme_lines=%d" % (ctx.read("README.md").count("\n") if readme else 0),
        "claude_md_exists=%s" % ("yes" if ctx.isfile("CLAUDE.md") else "no"),
        "markdown_files=%d" % sum(1 for f in files if f.endswith(".md")),
        "test_files=%d" % sum(1 for f in files if TEST_FILE.search(f)),
        "source_files=%d" % sum(1 for f in ctx.source_files() if SOURCE_EXT.search(f)),
    ]
    ctx.write("docs-facts.txt", "\n".join(lines) + "\n")
    ctx.record("docs-facts", "done", 0, "docs-facts.txt")


def run(ctx):
    _circular_imports(ctx)
    _duplication(ctx)
    _complexity(ctx)
    _sizes(ctx)
    _docs_facts(ctx)
