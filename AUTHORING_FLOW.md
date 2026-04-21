# Syllabus Authoring Flow — v2

**Problem.** The classic `syllabus_agent` writes everything into the
in-memory `draft_store` and never promotes. Root causes, top-down:

1. `agent/tools.py` loads MCP tools in `mode="draft"` only → the
   persistent `addChapter` / `addLesson` / `appendLessonContent` tools
   are **not bound to the LLM**. Even if the model wanted to write to
   Supabase it has no callable surface.
2. The `plan` is a flat list of lessons, so there's no place in state
   to carry real Supabase IDs for the syllabus / chapter / lesson
   being authored.
3. The writer and the critic talk to each other through `AIMessage`
   content (free text), which burns tokens and drifts.
4. `plan_router` only knows about `draft_lesson_id`; it never tells
   the agent to commit anything to the real DB.

## Target flow

```
planning ─── user confirms scope ───────────────────────────────┐
                                                                │
submit_plan(chapters=[{title, summary,                          │
                        lessons:[{title, brief}]}])             │
                                                                ▼
syllabus_create ── getOrCreateSyllabus(thread_id, title)  ◄─ commit
                                                                │
                                                                ▼
┌─ for each chapter in plan.chapters ──────────────────────────┐│
│ chapter_propose ── writer proposeChapter(...)                ││
│    ↕ critic_node (pass/fail, function-calling only)          ││
│ chapter_commit  ── addChapter(syllabus_id, title, summary)   ││
│                                                              ││
│ ┌─ for each lesson in chapter.lessons ────────────────────┐  ││
│ │ lesson_outline  ── writer proposeLessonOutline(outline) │  ││
│ │    ↕ critic                                             │  ││
│ │ lesson_create   ── addLesson(chapter_id, title,         │  ││
│ │                              blocks=[scaffold_blocks])  │  ││
│ │ lesson_content  ── appendLessonContent(lesson_id, ...)  │  ││
│ │    ↕ critic (existing block rubric)                     │  ││
│ │    repeat until critic PASS or max revisions            │  ││
│ │ lesson_commit   ── advance lesson_cursor                │  ││
│ └─────────────────────────────────────────────────────────┘  ││
│ advance chapter_cursor                                       ││
└──────────────────────────────────────────────────────────────┘│
                                                                ▼
done ── summarize, mark stop_reason=completed
```

The loop is **graph-driven**, not LLM-driven. The LLM only chooses
what to say inside a stage; the graph always decides the next stage.

## State additions (`agent/state.py`)

```python
plan: list[{                       # hierarchical, replaces v1 flat list
    "title":    str,               # chapter title
    "summary":  str,
    "status":   "pending"|"writing"|"done"|"failed",
    "chapter_id": Optional[str],   # Supabase id after commit
    "lessons": list[{
        "title":   str,
        "brief":   str,
        "status":  "pending"|"outline"|"content"|"done"|"failed",
        "lesson_id": Optional[str],
        "attempts": int,
    }],
}]
chapter_cursor: int                # index into plan
lesson_cursor: int                 # index into plan[chapter_cursor].lessons
phase: "planning" | "authoring" | "done"
stage: "syllabus_create"           # fine-grained stage WITHIN authoring
     | "chapter_propose" | "chapter_commit"
     | "lesson_outline" | "lesson_create"
     | "lesson_content" | "lesson_commit"
syllabus_id: Optional[str]         # Supabase syllabus id
```

## Tool surface

**Kill** `mode="draft"` load. The classic agent uses persistent tools:

| Stage            | Tool called                                    |
|------------------|------------------------------------------------|
| syllabus_create  | `getOrCreateSyllabus(thread_id, title)`        |
| chapter_commit   | `addChapter(syllabus_id, title, summary, pos)` |
| lesson_create    | `addLesson(chapter_id, title, blocks=scaffold)`|
| lesson_content   | `appendLessonContent(lesson_id, blocks)`       |
| lesson revision  | `updateLessonContent` / `patchLessonBlocks`    |

Plus two new **server-side Python tools** for the structured
writer↔critic handshake (v3, optional):
- `proposeChapter(index, title, summary, rationale)`
- `proposeLessonOutline(chapter_index, lesson_index, outline, rationale)`

These do not write anywhere; they only carry structured payload into
a tool message the critic can read. The goal is to let the writer
speak via function calls and keep `AIMessage.content` empty during
authoring to minimize tokens. **v2 does not require them** — we can
reuse the existing tool-message / critic loop by keying on the real
persistent mutation tools.

## Routing changes (`agent/graph.py`, `agent/nodes.py`)

1. `chat_node` gets a new knob: during `authoring`/`done` phases it
   binds tools with `tool_choice="required"` so the model **must**
   emit a tool call — no free-text turns.
2. `tools_post_hook` extends to recognize the persistent tool names
   (`addChapter`, `addLesson`, `appendLessonContent`, …) and writes
   resulting IDs back into the plan:
   - `getOrCreateSyllabus` result → `syllabus_id`
   - `addChapter` result → `plan[chapter_cursor].chapter_id`
   - `addLesson` result   → `plan[cc].lessons[lc].lesson_id`
   - `appendLessonContent`/`updateLessonContent` → `last_authored_lesson`
3. `plan_router` is rewritten as a hierarchical state machine:
   - advance cursors,
   - flip `stage`,
   - inject a concise SystemMessage telling the writer **exactly
     which tool to call next** (with the known IDs filled in).
4. `critic_node` gates only the `lesson_content` stage (existing
   block rubric). Chapter / lesson-outline reviews in v2 are a
   deterministic structural check (non-empty, no placeholders,
   sensible length) — LLM-backed critique is v3.

## v2 deliverable (this PR)

- Switch to `mode="persistent"`.
- Nested `plan` + hierarchical cursors in state.
- `submit_plan(chapters=[{title, summary, lessons:[{title,brief}]}])`
  rewritten; old flat signature dropped.
- `plan_router` rewritten as hierarchical machine.
- `tools_post_hook` ingests IDs from persistent tool results.
- `chat_node` forces `tool_choice="required"` during authoring.
- Prompt (`agent/prompts.py`) updated to reflect the new stages and
  explicitly tell the agent to use persistent tools, not `draft*`.

## v3 (follow-up)

- `proposeChapter` / `proposeLessonOutline` structured handshake tools.
- LLM-backed critic for chapter titles & lesson outlines.
- Concurrency guardrail: allow `addChapter` calls to prefetch outline
  for the next chapter while content authoring for current chapter
  is in flight.
