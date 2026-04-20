# curriculum-mcp

FastMCP server that exposes the MASTER-PFE curriculum (syllabi → chapters → lessons) as MCP tools,
backed by Supabase Postgres. Consumed by:

- the LangGraph `syllabus_agent` (classic + deep variants) via `langchain-mcp-adapters`
- any external MCP client (Claude Desktop, Cursor, CLI)

## Env

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `MCP_TRANSPORT` = `stdio` | `streamable-http` (default `streamable-http`)
- `MCP_HOST` / `MCP_PORT` (http only)
- `CURRICULUM_MCP_TOKEN` (optional bearer for http transport)

## Tools

| tool | purpose |
| --- | --- |
| `getOrCreateSyllabus` | ensure a syllabus exists for a given thread id |
| `listChapters` | list chapters in a syllabus |
| `addChapter` | create a new chapter |
| `listLessons` | list lessons in a chapter |
| `addLesson` | create a new lesson with initial blocks |
| `updateLessonContent` | replace all blocks |
| `appendLessonContent` | atomically append blocks |
| `patchLessonBlocks` | surgical per-block patches |
| `readLessonBlocks` | read current blocks |
| `getSyllabusOutline` | full outline (syllabus + chapters + lesson titles) |

## Local dev

```bash
cd curriculum-mcp
python -m venv .venv && . .venv/bin/activate
pip install -e .
export $(grep -v '^#' ../.env | xargs)
curriculum-mcp  # streamable-http on :8080
```
