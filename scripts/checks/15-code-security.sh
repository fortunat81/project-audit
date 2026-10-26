# Risky code patterns in any language Semgrep supports (Semgrep Community Edition, free rules).
# Note: the free edition analyses one file at a time; data passed between files isn't traced.

mod_applies() { return 0; }
mod_tools() { echo semgrep; }

mod_run() {
  DIM="security"
  if ! has semgrep; then skip semgrep "not installed ($(install_hint semgrep))"; return; fi
  note_version semgrep "$(semgrep --version 2>/dev/null | head -1)"
  # Semgrep exits 0 even when it finds things, so decide by the results list.
  run --json --empty '"results": *\[ *\]' semgrep semgrep.json \
    semgrep scan --config p/default --json --quiet --metrics=off .

  # Files Semgrep couldn't parse or scan are silently missing from "results".
  if json_looking "$OUT/semgrep.json"; then
    local errs scanned
    errs="$(json_eval "$OUT/semgrep.json" '(d.errors||[]).length' 'len(d.get("errors",[]))')"
    scanned="$(json_eval "$OUT/semgrep.json" '((d.paths||{}).scanned||[]).length' 'len(d.get("paths",{}).get("scanned",[]))')"
    [ -n "$scanned" ] && echo "semgrep_files_scanned=$scanned" >> "$OUT/meta.txt"
    if [ -z "$errs" ]; then
      record semgrep-coverage "skipped: no node or python available to read semgrep.json" "-" "-"
    elif [ "$errs" -gt 0 ]; then
      record semgrep-coverage "partial: $errs error(s), some files not fully scanned (see errors in semgrep.json)" "-" semgrep.json
    else
      record semgrep-coverage "clean" "-" semgrep.json
    fi
  fi
}
