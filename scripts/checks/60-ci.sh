# GitHub Actions workflows: injection, leaked credentials, over-broad permissions (zizmor).

mod_applies() { has_trait ci-github; }
mod_tools() { echo zizmor; }

mod_run() {
  DIM="security"
  if ! has zizmor; then skip zizmor "not installed ($(install_hint zizmor))"; return; fi
  note_version zizmor "$(zizmor --version 2>/dev/null | head -1)"
  # Exit codes 10-14 mean findings (by highest severity); 0 means none.
  run --json --codes "10 11 12 13 14" zizmor zizmor.json zizmor --format json .
}
