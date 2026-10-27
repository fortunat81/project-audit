# Structure: circular imports, duplication, function complexity, biggest files, folder sizes, docs facts.
# Scans the whole project (not one guessed folder), leaving out generated and vendored code.

mod_applies() { return 0; }
mod_tools() {
  echo npx      # madge and jscpd run through npx
  echo lizard   # function complexity, many languages (not Dart)
}

mod_run() {
  # Circular imports (JavaScript / TypeScript)
  DIM="architecture,modularity,spaghettiness"
  if has_trait node; then
    if shadowed madge; then skip madge-circular "untrusted mode: the project ships its own madge program in node_modules"
    elif has npx; then
      local tsarg=""
      [ -f tsconfig.json ] && tsarg="--ts-config tsconfig.json"   # follows @/ path aliases
      note_version madge "$MADGE_PKG"
      run --json madge-circular madge-circular.json $NPX_ENV npx --yes "$MADGE_PKG" --circular --json \
        --extensions ts,tsx,js,jsx,mjs,cjs $tsarg \
        --exclude '(^|/)(node_modules|dist|build|out|coverage|audit|\.expo|\.next|\.nuxt|\.svelte-kit|android|ios)/' .
    else skip madge-circular "npx not found ($(install_hint npx))"; fi
  fi

  # Duplication (any language)
  DIM="spaghettiness"
  if shadowed jscpd; then skip jscpd "untrusted mode: the project ships its own jscpd program in node_modules"
  elif has npx; then
    note_version jscpd "$JSCPD_PKG"
    mkdir -p "$OUT/jscpd"
    run --done --stdout jscpd.log jscpd jscpd/jscpd-report.json $NPX_ENV npx --yes "$JSCPD_PKG" . \
      --reporters json --output "$OUT/jscpd" --silent --ignore "$JSCPD_IGNORE,**/.git/**"
  else skip jscpd "npx not found ($(install_hint npx))"; fi

  # Function complexity and length
  DIM="spaghettiness,modularity"
  if has lizard; then
    note_version lizard "$(lizard --version 2>/dev/null | head -1)"
    local d
    set -- -w -C 15 -L 100     # warn on complexity above 15 or functions over 100 lines of code
    for d in node_modules dist build out coverage audit .git .expo .next .nuxt .svelte-kit .dart_tool Pods vendor; do
      set -- "$@" -x "*/$d/*"
    done
    if has_trait expo || has_trait flutter; then set -- "$@" -x "./android/*" -x "./ios/*"; fi
    run --codes "1" --match 'warning' lizard lizard.txt lizard "$@" .
    # lizard's JavaScript parser can crash on one odd file (unbalanced braces in vendored or
    # generated code) and then reports nothing at all. Retry without JavaScript, and say so.
    if tail -n 1 "$MANIFEST" | grep -Eq '^lizard[[:space:]]+failed-to-run' && grep -q 'Traceback' "$OUT/lizard.txt.err" 2>/dev/null; then
      sed '$d' "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
      cp "$OUT/lizard.txt.err" "$OUT/lizard-crash.err"
      run --codes "1" --match 'warning' lizard lizard.txt lizard "$@" -x "*.js" -x "*.jsx" -x "*.mjs" -x "*.cjs" .
      if tail -n 1 "$MANIFEST" | grep -Eq '^lizard[[:space:]]+(clean|findings)'; then
        awk -F'\t' -v OFS='\t' 'NR==FNR{n++; next} FNR==n{$2="partial: JavaScript files left out because lizard crashed on one (see lizard-crash.err); "$2} {print}' "$MANIFEST" "$MANIFEST" > "$MANIFEST.tmp" && mv "$MANIFEST.tmp" "$MANIFEST"
      fi
    fi
  else skip lizard "not installed ($(install_hint lizard))"; fi

  # Biggest files and folder sizes (no external tool)
  DIM="modularity,spaghettiness"
  if is_git; then
    project_files | grep -Ev "$NOISE_RE" \
      | tr '\n' '\0' | xargs -0 wc -l 2>/dev/null | grep -v ' total$' | sort -rn | head -30 > "$OUT/biggest-files.txt"
    record biggest-files done 0 biggest-files.txt
    DIM="architecture"
    project_files | grep -Ev "$NOISE_RE" | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -15 > "$OUT/files-per-folder.txt"
    record files-per-folder done 0 files-per-folder.txt
  else
    skip biggest-files "not a git repo"
  fi

  # Documentation facts
  DIM="documentation"
  {
    echo "readme_exists=$([ -f README.md ] && echo yes || echo no)"
    echo "readme_lines=$([ -f README.md ] && wc -l < README.md | tr -d ' ' || echo 0)"
    echo "claude_md_exists=$([ -f CLAUDE.md ] && echo yes || echo no)"
    echo "markdown_files=$(project_files | grep -Ec '\.md$')"
    echo "test_files=$(project_files | grep -Ec '(\.test\.|\.spec\.|_test\.|__tests__|(^|/)tests?/)')"
    echo "source_files=$(project_files | grep -Ev "$NOISE_RE" | grep -Ec '\.(ts|tsx|js|jsx|mjs|vue|svelte|astro|py|dart|swift|kt|java|php|rb|go)$')"
  } > "$OUT/docs-facts.txt"
  record docs-facts done 0 docs-facts.txt
}
