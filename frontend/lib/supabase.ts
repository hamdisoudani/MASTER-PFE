"use client";
import { createClient, SupabaseClient } from "@supabase/supabase-js";

/**
 * Browser Supabase client.
 *
 * Used for:
 *   1. Realtime subscriptions to `syllabi` / `chapters` / `lessons` so the
 *      UI reflects writes made by `curriculum-mcp` (which uses the service
 *      role key on the server side) in real time.
 *   2. Read-only fetches of syllabus / chapters / lessons / lesson blocks
 *      on demand (lazy per user action).
 *
 * IMPORTANT: browser bundle — use the ANON key only. Never expose
 * the service-role key here.
 *
 * RLS is currently disabled on curriculum tables (see
 * `supabase/migrations/0001_init_curriculum.sql`), so the anon key has
 * read+write access. If you ever turn RLS on, update policies accordingly.
 */

let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  if (_client) return _client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    if (typeof window !== "undefined") {
      console.warn(
        "[supabase] NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY missing — realtime disabled."
      );
    }
    return null;
  }
  _client = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
    realtime: { params: { eventsPerSecond: 10 } },
  });
  return _client;
}
