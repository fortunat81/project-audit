"""Backend access rules. With Supabase or Firebase, the key in the app is public by design;
the database rules are the only thing stopping anyone from reading or changing all the data.
  Supabase: tables created in SQL migrations without row-level security, policies open to everyone,
            the service_role key referenced outside server code
  Firebase: rules that allow everyone, test-mode rules with an expiry date, "any signed-in user" rules"""
import os
import re

from audit_core import read_text

NAME = "50-backend-rules"

CREATE_TABLE = re.compile(r'create table (if not exists )?("?[a-z0-9_]+"?\.)?"?[a-z0-9_]+"?')
ENABLE_RLS = re.compile(r"alter table .*enable row level security")
OPEN_POLICY = re.compile(r"(using|with check)\s*\(\s*true\s*\)", re.I)
SYSTEM_SCHEMAS = ("auth.", "storage.", "realtime.", "extensions.", "supabase_")
SERVICE_ROLE_SKIP = re.compile(r"(^|/)(supabase/functions|api|server|functions|scripts|backend)/|\.(md|sql)$")
FIREBASE_RULE_FILES = re.compile(r"(^|/)(firestore\.rules|storage\.rules|database\.rules\.json|[^/]*\.rules)$")
FIREBASE_OPEN = re.compile(r"if\s+true|allow\s+(read|write|read,\s*write)\s*;|\"\.(read|write)\"\s*:\s*true")
FIREBASE_TEST_MODE = re.compile(r"request\.time\s*<")
FIREBASE_ANY_USER = re.compile(r"request\.auth\s*!=\s*null\s*;?\s*$")


def applies(ctx):
    return ctx.has_trait("supabase") or ctx.has_trait("firebase")


def _clean_table(name):
    name = name.replace('"', "")
    return name[len("public."):] if name.startswith("public.") else name


def _supabase_rls(ctx):
    sql_files = [f for f in ctx.project_files() if f.lower().endswith(".sql") and not ctx.noise(f)]
    if not sql_files:
        ctx.skip("supabase-rls", "no SQL migrations in the repo; tables made in the Supabase dashboard can't be checked from code (use the Security Advisor in the dashboard)")
        return
    lines = []
    text = " ".join(read_text(os.path.join(ctx.root, f)) for f in sql_files).lower().replace("\n", " ")
    statements = text.split(";")   # one statement each
    tables, rls = set(), set()
    for st in statements:
        m = CREATE_TABLE.search(st)
        if m:
            tables.add(_clean_table(re.sub(r"create table (if not exists )?", "", m.group(0))))
        if ENABLE_RLS.search(st):
            m2 = re.search(r"alter table (only )?(if exists )?(\S+)", st)
            if m2:
                rls.add(_clean_table(m2.group(3)))
    for t in sorted(tables):
        if not t or t.startswith(SYSTEM_SCHEMAS):
            continue
        if t not in rls:
            lines.append("NO RLS: table '%s' is created in a migration but never gets 'enable row level security'" % t)
    # Policies that let everyone in (fine for public reads; risky for writes)
    for f in sql_files:
        for n, line in enumerate(read_text(os.path.join(ctx.root, f)).splitlines(), 1):
            if OPEN_POLICY.search(line):
                lines.append(("REVIEW open policy: %s:%d:%s" % (f, n, line))[:200])
    ctx.write("supabase-rls.txt", "".join(ln + "\n" for ln in lines))
    ctx.result("supabase-rls", "supabase-rls.txt")


def _service_role(ctx):
    """The service_role key bypasses every rule; it must only appear in server code."""
    hits = []
    for f in ctx.project_files():
        if ctx.noise(f) or SERVICE_ROLE_SKIP.search(f):
            continue
        for n, line in enumerate(read_text(os.path.join(ctx.root, f), 2000000).splitlines(), 1):
            if "service_role" in line.lower():
                hits.append("REVIEW service_role referenced outside server folders: %s:%d" % (f, n))
    ctx.write("supabase-service-role.txt", "".join(h + "\n" for h in hits))
    ctx.result("supabase-service-role", "supabase-service-role.txt")


def _firebase(ctx):
    rule_files = [f for f in ctx.project_files() if FIREBASE_RULE_FILES.search(f)]
    if not rule_files:
        ctx.skip("firebase-rules", "no rules files in the repo; check them in the Firebase console (Rules tab)")
        return
    lines = []
    for f in rule_files:
        for n, line in enumerate(read_text(os.path.join(ctx.root, f)).splitlines(), 1):
            if FIREBASE_OPEN.search(line):
                lines.append(("OPEN TO EVERYONE: %s:%d:%s" % (f, n, line))[:200])
        for n, line in enumerate(read_text(os.path.join(ctx.root, f)).splitlines(), 1):
            if FIREBASE_TEST_MODE.search(line):
                lines.append(("TEST MODE (expires, then locks or was left open): %s:%d:%s" % (f, n, line))[:200])
        for n, line in enumerate(read_text(os.path.join(ctx.root, f)).splitlines(), 1):
            if FIREBASE_ANY_USER.search(line):
                lines.append(("REVIEW any signed-in user allowed: %s:%d:%s" % (f, n, line))[:200])
    ctx.write("firebase-rules.txt", "".join(ln + "\n" for ln in lines))
    ctx.result("firebase-rules", "firebase-rules.txt")


def run(ctx):
    ctx.dim = "security"
    if ctx.has_trait("supabase"):
        _supabase_rls(ctx)
        _service_role(ctx)
    if ctx.has_trait("firebase"):
        _firebase(ctx)
