# Migrations Applied

| Migration | Applied at | Method | Result |
|---|---|---|---|
| `0001_init_curriculum.sql` | 2026-04-20 | Supabase Management API | Initial apply. |
| `0001_init_curriculum.sql` + `0002_activities.sql` | 2026-04-23 | Supabase Management API (re-apply after schema drift) | Tables dropped and re-created to match code (`syllabi`, `chapters`, `lessons`, `lesson_edits`, `activities`, `activity_edits`). Verified end-to-end via `curriculum-mcp` + `agent/graph.py`: 2 chapters / 4 lessons / 35-45 blocks per lesson. See `E2E_TEST_REPORT.md`. |

## Re-apply
```bash
export SUPABASE_MANAGEMENT_PAT=sbp_...
for f in supabase/migrations/*.sql; do
  curl -X POST "https://api.supabase.com/v1/projects/${SUPABASE_PROJECT_REF}/database/query" \
    -H "Authorization: Bearer $SUPABASE_MANAGEMENT_PAT" \
    -H "Content-Type: application/json" \
    --data "$(jq -Rs '{query: .}' "$f")"
done
```
