# Native Android / iOS code you wrote (not the folders Expo or Flutter generate):
# manifest and plist settings, insecure storage, weak crypto, WebView issues (mobsfscan).

mod_applies() { has_trait native-android || has_trait native-ios; }
mod_tools() { echo mobsfscan; }

mod_run() {
  DIM="security"
  if ! has mobsfscan; then skip mobsfscan "not installed ($(install_hint mobsfscan))"; return; fi
  note_version mobsfscan "$(mobsfscan --version 2>/dev/null | head -1)"
  run --json --empty '"results": *\{ *\}' mobsfscan mobsfscan.json mobsfscan --json .
}
