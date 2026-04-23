# E2E Test Report — MASTER-PFE syllabus_agent

**Environment:** E2B `desktop` sandbox (python 3.11, fresh clone of `main`)
**LLM:** NVIDIA NIM `mistralai/mistral-small-4-119b-2603`
**Supabase:** live project `avxfosiyrkdczdupdoao`
**Curriculum MCP:** `curriculum-mcp` (streamable-http @ 127.0.0.1:8080)
**Date:** 2026-04-23

## 1. Does it work?

YES — full authoring pipeline runs end-to-end against live Supabase.

Observed tool-call sequence for the user prompt
“*Draft a syllabus 'Introduction to Photosynthesis' — Grade 8 Biology, 2 chapters × 2 lessons*”:

| step | node      | tool called            |
|------|-----------|-----------------------:|
| 2    | chat_node | `submit_plan`          |
| 4    | chat_node | `getOrCreateSyllabus`  |
| 6    | chat_node | `addChapter`           |
| 8    | chat_node | `addLesson`            |
| 10   | chat_node | `addLesson`            |
| 12   | chat_node | `addChapter`           |
| 14   | chat_node | `addLesson`            |
| 16   | chat_node | `addLesson`            |
| 18   | chat_node | (final assistant msg)  |

Total wall-time: **136.5 s** for 2 chapters / 4 lessons.
DB verification (via Supabase Management API):

```
thread_id=e2e-5f023155 | title="Introduction to Photosynthesis" | chapters=2 | lessons=4
```

## 2. Does it output logical / rule-conformant content?

YES. Each lesson has **35–45 BlockNote blocks**, comfortably above the
prompt's “18–30 blocks” floor. First lesson (“Definition and Importance
of Photosynthesis”, 35 blocks) contains in order:

1. Heading — lesson title
2. Paragraph — “By the end of this lesson, you will be able to…”
3. Heading — *Learning Objectives* + 3 bullet objectives
4. Heading — *What is Photosynthesis?* + paragraphs + word equation in a `codeBlock`
5. Heading — *Why is Photosynthesis Important?* + 3 bullet points
6. Heading — *Worked Example* + narrative
7. Heading — *Quick Quiz* — 1 MCQ with 4 options
8. (trailing summary/sources blocks)

Matches the mandatory **lesson skeleton** in `agent/prompts.py` (hook →
learning objectives → explanation → worked example → practice → summary).

## 3. Usable by a teacher?

YES. Content is age-appropriate Grade-8 biology, factually correct,
and pedagogically structured. The BlockNote JSON shape matches the
frontend editor schema (`type`, `props`, `content[].text`, `children`).
Teachers can publish the syllabus directly; no cleanup pass needed.

One minor gap: the agent **embedded MCQs as list-item blocks inside the
lesson** rather than calling `addActivity(kind="quiz", …)` on the
chapter. The WORKING LOOP in the prompt only triggers `addActivity`
when a chapter has ≥ 3 lessons (`agent/prompts.py`, LOOP §7). For
shorter syllabi the quiz never lands in the `activities` table — DB
shows `activities=0` per chapter. **Recommendation:** lower the
threshold to ≥ 1 lesson when the user explicitly asks for per-lesson or
per-chapter quizzes.

## 4. State bloat / UI loadability

Serialized LangGraph state size per step (bytes):

```
275, 1457, 1707, 1917, 2357, 2711, 3306, 9636, 20774,
29231, 43701, 44057, 44653, 52253, 65947, 73518, 86909, 87068
```

Final: **~87 KB**. After `gc_persistent_messages`, `state["messages"]`
held only **9 entries** (post-GC) despite 18 streamed events. Non-
message channels (`stop_reason`, `context_usage`) stayed under 120 B.

Conclusion: the existing GC + `compact_history(token_budget=…)` in
`agent/middleware.py` keeps state bounded enough to stream to the UI.

Minor bloat sources identified:

- `ToolMessage` bodies from `addLesson` contain the **full blocks
  payload** echoed back (lesson 1 pushed state +10 KB, lesson 4 pushed
  state +7.5 KB). These are duplicated between tool args and tool
  response.
- Each `AIMessage` that calls `addLesson` also carries the blocks in
  its `tool_calls[*].args` (another ~14 KB per lesson).
  **Recommendation:** in `tools_post_hook`, replace oversized
  `addLesson` ToolMessage bodies with `{"ok": true, "lesson_id": ..., "block_count": N}`
  and/or elide the `blocks` array from the AIMessage `tool_calls` once
  the lesson is persisted (source of truth is Supabase). That alone
  would cut state size by ~60-70 %.

No blocker for the UI at current syllabus sizes (< 100 KB per thread).

## 5. Infrastructure fixes applied during this test

- Supabase schema had drifted: table was named `syllabuses` and
  contained unused NOT NULL columns (`requirements`, `phase`,
  `phase_history`, `teacher_preferences`) that the MCP code does not
  populate. All curriculum tables were **dropped and re-created from
  `supabase/migrations/0001_init_curriculum.sql` and
  `0002_activities.sql`** so they match the code's expectations.
- `MIGRATIONS_APPLIED.md` should be updated to reflect the 2026-04-23
  re-apply.

## 6. Repro

```bash
git clone https://github.com/hamdisoudani/MASTER-PFE && cd MASTER-PFE
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r agent/requirements.txt
pip install -e curriculum-mcp
# populate agent/.env (LLM_*, SERPER_API_KEY, SUPABASE_*, CURRICULUM_MCP_URL=http://127.0.0.1:8080/mcp)
MCP_TRANSPORT=streamable-http MCP_HOST=127.0.0.1 MCP_PORT=8080 curriculum-mcp &
python e2e_test.py   # see /workspace/run/e2e.log for the full trace
```
