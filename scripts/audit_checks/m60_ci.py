"""GitHub Actions workflows: injection, leaked credentials, over-broad permissions (zizmor)."""
NAME = "60-ci"


def applies(ctx):
    return ctx.has_trait("ci-github")


def tools(ctx):
    return ["zizmor"]


def run(ctx):
    ctx.dim = "security"
    if not ctx.has("zizmor"):
        ctx.skip("zizmor", "not installed (%s)" % ctx.install_hint("zizmor"))
        return
    ctx.note_version("zizmor", ctx.run_text(["zizmor", "--version"]))
    # Exit codes 10-14 mean findings (by highest severity); 0 means none.
    ctx.run("zizmor", "zizmor.json", ["zizmor", "--format", "json", "."], codes=(10, 11, 12, 13, 14), json=True)
