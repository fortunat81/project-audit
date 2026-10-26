# Review checklist: Supabase (trait `supabase`)

The anon key ships inside the app or website by design. Row-level security (RLS) policies are the only thing between that key and the whole database.

## Always (quick and full)
- **`supabase-rls.txt`:** every "NO RLS" table is **critical** if it holds anything not meant to be public. Open the migration to confirm (RLS may be enabled in a later file or under another name; check before confirming).
- **Open policies:** a `with check (true)` on insert/update/delete, or `using (true)` on tables with personal data, is **high**. `using (true)` on a public catalogue table is fine; say so.
- **service_role key:** any use outside server code (`supabase-service-role.txt`) is **critical**: it bypasses all policies.
- **No migrations in the repo:** say the tables couldn't be checked from code and tell the user to run the Security Advisor in the Supabase dashboard.

## Full mode
- Policies that check `auth.uid()` against the right column (owner), not just `auth.role() = 'authenticated'` (any signed-in user sees everyone's rows).
- Storage buckets marked public that hold user uploads.
- Edge Functions (`supabase/functions/`) apply the server-code checklist; they often use the service_role key, so they must check the caller themselves.
- Database functions marked `security definer` without a fixed `search_path`.
