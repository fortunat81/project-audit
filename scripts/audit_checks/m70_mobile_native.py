"""Native Android / iOS code you wrote (not the folders Expo or Flutter generate):
manifest and plist settings, insecure storage, weak crypto, WebView issues (mobsfscan)."""
NAME = "70-mobile-native"


def applies(ctx):
    return ctx.has_trait("native-android") or ctx.has_trait("native-ios")


def tools(ctx):
    return ["mobsfscan"]


def run(ctx):
    ctx.dim = "security"
    if not ctx.has("mobsfscan"):
        ctx.skip("mobsfscan", "not installed (%s)" % ctx.install_hint("mobsfscan"))
        return
    ctx.note_version("mobsfscan", ctx.run_text(["mobsfscan", "--version"]))
    ctx.run("mobsfscan", "mobsfscan.json", ["mobsfscan", "--json", "."], json=True, empty=r'"results": *\{ *\}')
