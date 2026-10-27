# Risky code patterns in any language Semgrep supports (Semgrep Community Edition, free rules).
# Note: the free edition analyses one file at a time; data passed between files isn't traced.

mod_applies() { return 0; }
mod_tools() { echo semgrep; }

mod_run() {
  DIM="security"
  if ! has semgrep; then skip semgrep "not installed ($(install_hint semgrep))"; astro_security; return; fi
  note_version semgrep "$(semgrep --version 2>/dev/null | head -1)"
  # Semgrep exits 0 even when it finds things, so decide by the results list.
  run --json --empty '"results": *\[ *\]' semgrep semgrep.json \
    semgrep scan --config p/default --json --quiet --metrics=off --exclude audit .   # not our own results

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
  astro_security
}

# ---------------------------------------------------------------- Astro ----
# Semgrep has no rules for .astro files, so it opens them and finds nothing. Copy the TypeScript at
# the top of each file (between the two --- lines) and the <script> blocks into temporary .ts files,
# blanking every other line so line numbers stay the same, and scan those. The temporary copies live
# in the audit folder; the project is never touched. Also flags set:html, Astro's way of writing raw
# HTML into a page (the same risk as React's dangerouslySetInnerHTML).

# astro_extract <mode: top|script> <file>   prints the code lines, everything else as empty lines
astro_extract() {
  if [ "$1" = top ]; then
    awk 'NR==1 && /^---[[:space:]]*$/ {t=1; print ""; next}
         t && /^---[[:space:]]*$/ {t=0; print ""; next}
         t {print; next}
         {print ""}' "$2"
  else
    awk '{
      out=""
      if (!ins) {
        if (match($0, /<script[^>]*>/)) {
          tag=substr($0, RSTART, RLENGTH); rest=substr($0, RSTART+RLENGTH)
          skip = (tag ~ /type="?(application\/ld\+json|application\/json|text\/template)/ || tag ~ /set:html/)
          if (index(rest, "</script>") > 0) { if (!skip) out=substr(rest, 1, index(rest, "</script>")-1) }
          else { ins=1; if (!skip) out=rest }
        }
      } else if (index($0, "</script>") > 0) { if (!skip) out=substr($0, 1, index($0, "</script>")-1); ins=0 }
      else if (!skip) out=$0
      print out
    }' "$2"
  fi
}

astro_security() {
  local files f dest n=0 rel
  files="$(project_files | grep '\.astro$')"
  [ -z "$files" ] && return 0

  # 1. set:html with anything other than a plain string
  : > "$OUT/astro-set-html.txt"
  echo "$files" | tr '\n' '\0' | xargs -0 grep -HnE 'set:html=\{[[:space:]]*[^"'"'"'`[:space:]}]' 2>/dev/null \
    | grep -v 'JSON\.stringify' | cut -d: -f1,2 | sort -u | head -20 \
    | sed 's|^|WARN  ASTRO-SET-HTML: raw HTML written into the page; make sure the value can never contain visitor input: |' >> "$OUT/astro-set-html.txt"
  result astro-set-html astro-set-html.txt

  # 2. Semgrep on the extracted code
  if ! has semgrep; then skip semgrep-astro "not installed ($(install_hint semgrep))"; return 0; fi
  rm -rf "$OUT/astro-extract"
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    dest="$OUT/astro-extract/$f"; mkdir -p "$(dirname "$dest")"
    astro_extract top "$f" > "$dest.ts"
    astro_extract script "$f" > "$dest.script.ts"
    grep -q '[^[:space:]]' "$dest.ts" 2>/dev/null || rm -f "$dest.ts"
    grep -q '[^[:space:]]' "$dest.script.ts" 2>/dev/null || rm -f "$dest.script.ts"
    n=$((n+1))
  done <<EOT
$files
EOT
  [ -n "$(find "$OUT/astro-extract" -name '*.ts' 2>/dev/null | head -1)" ] || return 0
  rel="${OUT#$ROOT/}/astro-extract"
  run --json --empty '"results": *\[ *\]' semgrep-astro semgrep-astro.json \
    semgrep scan --config p/default --json --quiet --metrics=off --no-git-ignore "$rel"
  # Findings in the original file names, for the report
  if json_looking "$OUT/semgrep-astro.json"; then
    json_eval "$OUT/semgrep-astro.json" \
      '(d.results||[]).map(r=>r.path+":"+r.start.line+" "+r.check_id.split(".").pop()).join("\n")' \
      '"\n".join(r["path"]+":"+str(r["start"]["line"])+" "+r["check_id"].split(".")[-1] for r in d.get("results",[]))' \
      | tr '\\' '/' \
      | awk '{ sub(/.*astro-extract\//, "")
               if ($0 ~ /\.astro\.script\.ts:/) { sub(/\.astro\.script\.ts:/, ".astro:"); $0 = $0 " (in a <script> block)" }
               else sub(/\.astro\.ts:/, ".astro:")
               print }' \
      > "$OUT/astro-findings.txt"
  fi
  echo "astro_files_extracted=$n" >> "$OUT/meta.txt"
}
