# The deployed site, when a URL is given (url= in .audit.conf, or AUDIT_URL for one run).
# Only point this at sites you own or have the owner's permission to test.
#   live-site    HTTPS redirect, security headers, files that must never be public (.env, .git),
#                public source maps, certificate expiry. Response bodies are never saved.
#   lighthouse   accessibility, SEO, performance and best-practice scores (needs Chrome)

mod_applies() { has_trait live-url; }
mod_tools() { echo curl; echo npx; }

mod_run() {
  DIM="security"
  if ! has curl; then skip live-site "curl not found"; skip lighthouse "curl not found"; return; fi

  local url="${AUDIT_URL%/}" host scheme out="$OUT/live-site.txt" code body p
  scheme="${url%%://*}"; host="${url#*://}"; host="${host%%/*}"
  : > "$out"
  local C="curl -s --max-time 20 -A project-audit"

  # Reachable at all?
  code="$($C -o /dev/null -w '%{http_code}' -L "$url" 2>/dev/null)"
  if [ -z "$code" ] || [ "$code" = "000" ]; then
    record live-site "failed-to-run (could not reach $url)" "-" "-"
    return
  fi
  echo "INFO $url answered HTTP $code" >> "$out"

  # 1. Plain http should redirect to https
  local redir
  redir="$($C -o /dev/null -w '%{redirect_url}' "http://$host/" 2>/dev/null)"
  case "$redir" in https://*) echo "OK   http:// redirects to https://" >> "$out" ;;
    *) echo "FAIL http://$host/ does not redirect to https:// (got: ${redir:-no redirect})" >> "$out" ;; esac
  [ "$scheme" = "https" ] || echo "FAIL the audited URL is not https" >> "$out"

  # 2. Security headers on the final response
  local hdr
  hdr="$($C -o /dev/null -D - -L "$url" 2>/dev/null | tr -d '\r' | tr 'A-Z' 'a-z')"
  for p in strict-transport-security content-security-policy x-content-type-options referrer-policy; do
    if echo "$hdr" | grep -q "^$p:"; then echo "OK   header $p" >> "$out"; else echo "WARN missing header: $p" >> "$out"; fi
  done
  if echo "$hdr" | grep -q '^x-frame-options:' || echo "$hdr" | grep -q '^content-security-policy:.*frame-ancestors'; then
    echo "OK   clickjacking protection (x-frame-options or frame-ancestors)" >> "$out"
  else echo "WARN no clickjacking protection (x-frame-options or CSP frame-ancestors)" >> "$out"; fi
  echo "$hdr" | grep -E '^(x-powered-by|server):' | sed 's/^/INFO reveals: /' >> "$out"

  # 3. Files that must never be public. The body is checked for the file's real content
  #    (many hosts answer 200 with the home page for any path) and never saved.
  check_path() {  # check_path <path> <regex the real file would contain>
    body="$($C -L "$url$1" 2>/dev/null | head -c 4000)"
    code="$($C -o /dev/null -w '%{http_code}' -L "$url$1" 2>/dev/null)"
    if [ "$code" = "200" ] && printf '%s' "$body" | grep -Eq "$2" && ! printf '%s' "$body" | grep -qi '<html'; then
      echo "FAIL publicly readable: $1" >> "$out"
    fi
  }
  check_path "/.env" '^[A-Z_][A-Z0-9_]*='
  check_path "/.env.local" '^[A-Z_][A-Z0-9_]*='
  check_path "/.env.production" '^[A-Z_][A-Z0-9_]*='
  check_path "/.git/HEAD" '^ref: '
  check_path "/.git/config" '\[core\]'
  grep -q '^FAIL publicly' "$out" || echo "OK   no .env or .git files served" >> "$out"

  # 4. Public source maps (they hand out the original source code)
  local js maps=0
  for js in $($C -L "$url" 2>/dev/null | head -c 2000000 | grep -oE '<script[^>]+src="[^"]+\.js[^"]*"' | sed -E 's/.*src="([^"]+)".*/\1/' | head -5); do
    case "$js" in http*) ;; //*) js="$scheme:$js" ;; /*) js="$scheme://$host$js" ;; *) js="$url/$js" ;; esac
    js="${js%%\?*}"
    if [ "$($C -o /dev/null -w '%{http_code}' "$js.map" 2>/dev/null)" = "200" ] \
       && $C "$js.map" 2>/dev/null | head -c 200 | grep -q '"version"'; then
      echo "WARN public source map: $js.map" >> "$out"; maps=1
    fi
  done
  [ $maps -eq 0 ] && echo "OK   no public source maps found (first 5 scripts checked)" >> "$out"

  # 5. Certificate expiry (best effort; curl's verbose format differs between systems)
  if [ "$scheme" = "https" ]; then
    local exp
    exp="$(curl -sv --max-time 20 -o /dev/null "$url" 2>&1 | grep -i 'expire date' | head -1 | sed 's/.*expire date: *//')"
    [ -n "$exp" ] && echo "INFO certificate expires: $exp" >> "$out"
  fi

  if grep -qE '^(FAIL|WARN)' "$out"; then record live-site findings "-" live-site.txt
  else record live-site clean "-" live-site.txt; fi

  # Lighthouse
  DIM="quality"
  if has npx; then
    note_version lighthouse "$LIGHTHOUSE_PKG"
    run --done --json --stdout lighthouse.log lighthouse lighthouse.json npx --yes "$LIGHTHOUSE_PKG" "$url" \
      --output=json --output-path="$OUT/lighthouse.json" --quiet --chrome-flags="--headless=new"
  else skip lighthouse "npx not found ($(install_hint npx))"; fi
}
