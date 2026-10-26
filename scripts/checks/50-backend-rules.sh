# Backend access rules. With Supabase or Firebase, the key in the app is public by design;
# the database rules are the only thing stopping anyone from reading or changing all the data.
#   Supabase: tables created in SQL migrations without row-level security, policies open to everyone,
#             the service_role key referenced outside server code
#   Firebase: rules that allow everyone, test-mode rules with an expiry date, "any signed-in user" rules

mod_applies() { has_trait supabase || has_trait firebase; }

mod_run() {
  DIM="security"
  local f

  if has_trait supabase; then
    local sql
    sql="$(project_files | grep -Ei '\.sql$' | grep -Ev "$NOISE_RE")"
    if [ -z "$sql" ]; then
      skip supabase-rls "no SQL migrations in the repo; tables made in the Supabase dashboard can't be checked from code (use the Security Advisor in the dashboard)"
    else
      : > "$OUT/supabase-rls.txt"
      # Tables created anywhere vs tables that get "enable row level security" anywhere
      echo "$sql" | tr '\n' '\0' | xargs -0 cat 2>/dev/null | tr 'A-Z' 'a-z' | tr '\n' ' ' | tr ';' '\n' > "$OUT/.sql-statements"   # one statement per line
      grep -oE 'create table (if not exists )?("?[a-z0-9_]+"?\.)?"?[a-z0-9_]+"?' "$OUT/.sql-statements" \
        | sed -E 's/create table (if not exists )?//; s/"//g; s/^public\.//' | sort -u > "$OUT/.tables"
      grep -E 'alter table .*enable row level security' "$OUT/.sql-statements" \
        | sed -E 's/.*alter table (only )?(if exists )?//; s/ .*//; s/"//g; s/^public\.//' | sort -u > "$OUT/.rls"
      while IFS= read -r t; do
        [ -z "$t" ] && continue
        case "$t" in auth.*|storage.*|realtime.*|extensions.*|supabase_*) continue ;; esac
        grep -qx "$t" "$OUT/.rls" || echo "NO RLS: table '$t' is created in a migration but never gets 'enable row level security'" >> "$OUT/supabase-rls.txt"
      done < "$OUT/.tables"
      # Policies that let everyone in (fine for public reads; risky for writes)
      echo "$sql" | while IFS= read -r f; do
        grep -niE '(using|with check)[[:space:]]*\([[:space:]]*true[[:space:]]*\)' "$f" 2>/dev/null \
          | sed "s|^|REVIEW open policy: $f:|" | cut -c1-200 >> "$OUT/supabase-rls.txt"
      done
      rm -f "$OUT/.sql-statements" "$OUT/.tables" "$OUT/.rls"
      result supabase-rls supabase-rls.txt
    fi

    # The service_role key bypasses every rule; it must only appear in server code.
    : > "$OUT/supabase-service-role.txt"
    project_files | grep -Ev "$NOISE_RE" | grep -Ev '(^|/)(supabase/functions|api|server|functions|scripts|backend)/|\.(md|sql)$' \
      | tr '\n' '\0' | xargs -0 grep -HnIi 'service_role' 2>/dev/null | cut -d: -f1,2 \
      | sed 's/^/REVIEW service_role referenced outside server folders: /' >> "$OUT/supabase-service-role.txt"
    result supabase-service-role supabase-service-role.txt
  fi

  if has_trait firebase; then
    local rules
    rules="$(project_files | grep -E '(^|/)(firestore\.rules|storage\.rules|database\.rules\.json|[^/]*\.rules)$')"
    if [ -z "$rules" ]; then
      skip firebase-rules "no rules files in the repo; check them in the Firebase console (Rules tab)"
    else
      : > "$OUT/firebase-rules.txt"
      echo "$rules" | while IFS= read -r f; do
        grep -nE 'if[[:space:]]+true|allow[[:space:]]+(read|write|read,[[:space:]]*write)[[:space:]]*;|"\.(read|write)"[[:space:]]*:[[:space:]]*true' "$f" 2>/dev/null \
          | sed "s|^|OPEN TO EVERYONE: $f:|" | cut -c1-200 >> "$OUT/firebase-rules.txt"
        grep -nE 'request\.time[[:space:]]*<' "$f" 2>/dev/null \
          | sed "s|^|TEST MODE (expires, then locks or was left open): $f:|" | cut -c1-200 >> "$OUT/firebase-rules.txt"
        grep -nE 'request\.auth[[:space:]]*!=[[:space:]]*null[[:space:]]*;?[[:space:]]*$' "$f" 2>/dev/null \
          | sed "s|^|REVIEW any signed-in user allowed: $f:|" | cut -c1-200 >> "$OUT/firebase-rules.txt"
      done
      result firebase-rules firebase-rules.txt
    fi
  fi
}
