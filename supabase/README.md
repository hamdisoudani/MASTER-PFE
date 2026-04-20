# Supabase migrations

SQL migrations for the MASTER-PFE curriculum store.

Hierarchy:
- `syllabi` — one per LangGraph thread (`thread_id` is unique).
- `chapters` — N per syllabus, ordered by `position`.
- `lessons` — N per chapter, ordered by `position`, blocks stored as BlockNote JSON.
- `lesson_edits` — append-only audit log.

Realtime is enabled for `syllabi`, `chapters`, `lessons` via the `supabase_realtime` publication.
RLS is **disabled** intentionally (no auth yet — single-tenant). Re-enable before going multi-user.

## Apply

Option A — psql (needs DB password):
```bash
psql "postgresql://postgres:$SUPABASE_DB_PASSWORD@db.$SUPABASE_PROJECT_REF.supabase.co:5432/postgres" \
     -f supabase/migrations/0001_init_curriculum.sql
```

Option B — Supabase SQL Editor: paste the file contents and run.

Option C — Supabase CLI: `supabase db push` after linking the project.
