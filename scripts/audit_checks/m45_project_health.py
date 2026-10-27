"""Project health for JavaScript/TypeScript: dead code and unused dependencies (knip),
and for Expo apps, SDK/library mismatches and deprecated packages (expo-doctor)."""
from audit_core import KNIP_PKG

NAME = "45-project-health"


def applies(ctx):
    return ctx.has_trait("node")


def tools(ctx):
    return ["npx"]


def run(ctx):
    ctx.dim = "quality,spaghettiness"
    if not ctx.has("npx"):
        ctx.skip("knip", "npx not found (%s)" % ctx.install_hint("npx"))
        if ctx.has_trait("expo"):
            ctx.skip("expo-doctor", "npx not found")
        return

    # Unused files, exports and dependencies. Needs installed dependencies to read the project's config.
    if ctx.untrusted:
        ctx.skip("knip", "untrusted mode: knip loads the project's config files as code")
    elif not ctx.exists("node_modules"):
        ctx.skip("knip", "dependencies not installed (offer: scan.sh --install-deps)")
    else:
        ctx.note_version("knip", KNIP_PKG)
        ctx.run("knip", "knip.json", ["npx", "--yes", KNIP_PKG, "--reporter", "json", "--no-progress"], json=True)

    # Expo: checks the project against its SDK version (needs network)
    if ctx.has_trait("expo"):
        ctx.dim = "quality"
        if ctx.untrusted:
            ctx.skip("expo-doctor", "untrusted mode: expo-doctor runs the app's own config as code")
        elif not ctx.exists("node_modules"):
            ctx.skip("expo-doctor", "dependencies not installed (offer: scan.sh --install-deps)")
        else:
            ctx.note_version("expo-doctor", "latest via npx (follows the Expo SDK)")
            ctx.run("expo-doctor", "expo-doctor.txt", ["npx", "--yes", "expo-doctor"], match=r"checks? (passed|failed)|[0-9]+/[0-9]+ checks")
