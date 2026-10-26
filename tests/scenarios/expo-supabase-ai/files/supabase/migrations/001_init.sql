-- PLANTED: bookings has no row level security.
create table public.bookings (id uuid primary key, customer_name text, address text);
create table if not exists "profiles" (id uuid primary key, display_name text);
alter table profiles enable row level security;
create policy "own profile" on profiles for select using (auth.uid() = id);
-- PLANTED: anyone can insert bookings.
create policy "anyone can insert" on bookings for insert with check (true);
