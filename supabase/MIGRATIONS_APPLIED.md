# Migrations Applied

| Migration | Applied at | Method | Result |
|---|---|---|---|
| `0001_init_curriculum.sql` | 2026-04-20 | Supabase Management API (`POST /v1/projects/{ref}/database/query`) | ✅ Tables `syllabi`, `chapters`, `lessons`, `lesson_edits` created. Realtime publication `supabase_realtime` includes all three data tables. RLS disabled (single-tenant). Verified via PostgREST `200 OK` on all four tables. |

## Smoke test (live Supabase, 2026-04-20)
End-to-end MCP tool run via `curriculum-mcp`:

- `getOrCreateSyllabus` → created syllabus
- `addChapter` → position auto=0
- `addLesson` → v=1, block_count=1 (generated column)
- `appendLessonContent` → v=2, block_count=2
- `patchLessonBlocks` (replace) → v=3
- `readLessonBlocks` → correct merged blocks
- `getSyllabusOutline` → nested chapters[lessons] shape

Test rows cleaned up afterwards.

## How to re-apply
```bash
export SUPABASE_MANAGEMENT_PAT=sbp_...
curl -X POST "https://api.supabase.com/v1/projects/${SUPABASE_PROJECT_REF}/database/query" \
  -H "Authorization: Bearer $SUPABASE_MANAGEMENT_PAT" \
  -H "Content-Type: application/json" \
  --data "$(jq -Rs '{query: .}' supabase/migrations/0001_init_curriculum.sql)"
```
