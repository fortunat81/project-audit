import { createClient } from "@supabase/supabase-js";
// Fine: the anon key is designed to be public. Must NOT be flagged.
export const supabase = createClient(process.env.EXPO_PUBLIC_SUPABASE_URL!, process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!);
