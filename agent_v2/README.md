# agent_v2 — router-controlled syllabus agent

A deterministic rewrite of the syllabus agent. The LLM no longer decides the
next step; a pure Python router walks a static plan.

## Graph

```
entry ─▶ router ─┬─▶ info_gather ──▶ router
                 ├─▶ planner     ──▶ router
                 ├─▶ advance     ──▶ router
                 ├─▶ writer_(lesson|activity) ─▶ critic
                 │                                │ pass   ─▶ persist ─▶ router
                 │                                │ fail<N ─▶ writer
                 │                                │ fail≥N ─▶ escalate ─▶ router
                 └─▶ promote ─▶ END
```

## Key properties

1. **Auto-accept moved off the frontend.** There is no `auto_accept` toggle in
   the graph. The agent simply issues `interrupt({type:"askUser",...})` once in
   `info_gather` and waits for the user's resume. The frontend only needs to
   render the card and resume the thread — no "auto accept" policy required.

2. **LLM never routes.** `router.py` picks the next substep by scanning
   `plan.chapters[*].substeps` for the first `done=false` entry. Chapters and
   their lessons finish in order — no jumping.

3. **Writer ↔ critic exchange is state-only.** The exchange lives in
   `current_draft` / `current_critic` / `current_attempts`. Nothing is appended
   to `messages`. The UI is therefore not polluted and the LLM context is not
   inflated by internal iterations.

4. **Per-substep cleanup prevents garbage accumulation.** When the critic
   passes, `persist_node` clears `current_draft`, `current_critic`,
   `current_attempts` before the router advances. The checkpoint stays small
   regardless of how many lessons you write.

5. **Activities are real JSON, not prose.** `ActivityDraftSchema` forces
   `{question, options, correct_index, multi, explanation}`. The frontend can
   render an interactive quiz directly — no parsing, no heuristics.

6. **Hidden research.** `info_gather` runs Serper queries + an LLM digest
   entirely inside the node. Nothing is appended to `messages`; the research is
   dropped from state after the profile is saved.

## Env (same as agent/)

```
LLM_API_KEY=xai-...
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-4.20-0309-non-reasoning
SERPER_API_KEY=...
CURRICULUM_MCP_URL=https://mcp-curriculum.up.railway.app/mcp
DATABASE_URL=postgresql://...
```

## Local test

```bash
pip install -r agent/requirements.txt pydantic
langgraph dev --config langgraph.json   # picks up syllabus_agent_v2
```

The new graph id is `syllabus_agent_v2`. The old `syllabus_agent` and
`syllabus_agent_deep` are untouched.

## TODO / follow-up

- Add `addActivity` tool to `curriculum-mcp` so activity substeps actually
  persist (currently `persist._persist_activity` no-ops when the tool is
  missing).
- Wire frontend to render the activity JSON as an interactive quiz card.
- Remove frontend `auto_accept` toggle (the UI no longer needs it — the graph
  only interrupts in `info_gather`).
