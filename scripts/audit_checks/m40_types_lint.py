"""Bugs and quality: type errors and lint, with each stack's own tools.
  TypeScript -> tsc     JavaScript/TypeScript -> ESLint (only if the project has a config)
  Python -> ruff        Flutter -> flutter analyze      Dart -> dart analyze"""
NAME = "40-types-lint"

NODE_BIN = "node_modules/.bin/"


def applies(ctx):
    return ctx.has_trait("node") or ctx.has_trait("python") or ctx.has_trait("dart")


def tools(ctx):
    out = []
    if ctx.has_trait("python"):
        out.append("ruff")
    if ctx.has_trait("flutter"):
        out.append("flutter")
    elif ctx.has_trait("dart"):
        out.append("dart")
    return out


def eslint_config_found(ctx):
    """Flat config, classic .eslintrc, or "eslintConfig" in package.json."""
    return ctx.any_file("eslint.config.*", ".eslintrc", ".eslintrc.*") or '"eslintConfig"' in ctx.read("package.json")


def _tsc(ctx):
    if not ctx.has_trait("typescript"):
        return
    if ctx.untrusted:
        ctx.skip("tsc", "untrusted mode: tsc would run the project's own compiler and plugins")
    elif ctx.has_trait("node") and not ctx.exists("node_modules"):
        ctx.skip("tsc", "dependencies not installed (offer: scan.sh --install-deps)")
    elif ctx.has_trait("astro") and not ctx.isfile(".astro", "types.d.ts"):
        # Astro writes its type files to .astro/ (npx astro sync, also done by dev and build). Without them
        # tsc reports errors that are not real (for example "Property 'env' does not exist on ImportMeta").
        ctx.skip("tsc", "Astro's generated types are missing, so tsc would report false errors (run: npx astro sync, then scan again)")
    elif ctx.isfile("node_modules", ".bin", "tsc"):
        ctx.note_version("tsc", ctx.run_text([NODE_BIN + "tsc", "--version"]))
        ctx.run("tsc", "tsc.txt", [NODE_BIN + "tsc", "--noEmit"], codes=(1, 2), match="error TS")
    elif ctx.has("npx"):
        ctx.run("tsc", "tsc.txt", ["npx", "--yes", "-p", "typescript", "tsc", "--noEmit"], codes=(1, 2), match="error TS")
    else:
        ctx.skip("tsc", "npx not found")


def _eslint(ctx):
    if not ctx.has_trait("node"):
        return
    ignore = ["--ignore-pattern", "audit/**"]
    if ctx.untrusted:
        ctx.skip("eslint", "untrusted mode: ESLint would run the project's config file and plugins as code")
    elif not eslint_config_found(ctx):
        ctx.skip("eslint", "no ESLint config in the project (looked for eslint.config.*, .eslintrc*, package.json)")
    elif not ctx.exists("node_modules"):
        ctx.skip("eslint", "dependencies not installed (offer: scan.sh --install-deps)")
    elif ctx.isfile("node_modules", ".bin", "eslint"):
        ctx.note_version("eslint", ctx.run_text([NODE_BIN + "eslint", "--version"]))
        ctx.run("eslint", "eslint.json", [NODE_BIN + "eslint", ".", "-f", "json"] + ignore, json=True)
    elif ctx.has("npx"):
        ctx.run("eslint", "eslint.json", ["npx", "--yes", "eslint", ".", "-f", "json"] + ignore, json=True)
    else:
        ctx.skip("eslint", "npx not found")


def _python(ctx):
    if not ctx.has_trait("python"):
        return
    if ctx.has("ruff"):
        ctx.note_version("ruff", ctx.run_text(["ruff", "--version"]))
        ctx.run("ruff", "ruff.json", ["ruff", "check", ".", "--output-format", "json"], json=True)
    else:
        ctx.skip("ruff", "not installed (%s)" % ctx.install_hint("ruff"))


def _dart(ctx):
    if ctx.has_trait("flutter"):
        if ctx.untrusted:
            ctx.skip("flutter-analyze", "untrusted mode: the analyzer can run package build hooks from the project")
        elif ctx.has("flutter"):
            ctx.note_version("flutter", ctx.run_text(["flutter", "--version"]))
            ctx.run("flutter-analyze", "flutter-analyze.txt", ["flutter", "analyze", "--no-pub"], codes=(1,), match=" • ")
        else:
            ctx.skip("flutter-analyze", "Flutter SDK not found (%s)" % ctx.install_hint("flutter"))
    elif ctx.has_trait("dart"):
        if ctx.untrusted:
            ctx.skip("dart-analyze", "untrusted mode: the analyzer can run package build hooks from the project")
        elif ctx.has("dart"):
            ctx.note_version("dart", ctx.run_text(["dart", "--version"]))
            ctx.run("dart-analyze", "dart-analyze.txt", ["dart", "analyze"], codes=(1, 2, 3), match=" - ")
        else:
            ctx.skip("dart-analyze", "Dart SDK not found")


def run(ctx):
    ctx.dim = "quality"
    _tsc(ctx)
    _eslint(ctx)
    _python(ctx)
    _dart(ctx)
