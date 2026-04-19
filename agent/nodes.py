"""
chat_node — binds Python tools + CopilotKit frontend tools to the LLM.

IMPORTANT: parallel_tool_calls=False is required when mixing frontend and
Python tools. Without it the LLM may emit both types in one AIMessage;
ToolNode only executes Python calls, leaving frontend calls without a
ToolMessage result and causing the LLM to loop.

CONTEXT INJECTION:
  useCopilotReadable() on the frontend serializes the value to a JSON string,
  then stores {description, value} into state.copilotkit["context"]. We read
  those here, parse the JSON string back, and inject everything into the
  system prompt so the agent sees the current editor state on every turn.
"""
import json
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from copilotkit.langchain import copilotkit_emit_state

from .state import AgentState, PlanStep
from .llm import get_llm
from .tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES, PLAN_TOOL_NAMES

MAX_MESSAGES = 30
KEEP_RECENT = 14


async def _maybe_summarize(messages: list, llm) -> list:
    """Compress old messages when the conversation gets long."""
    if len(messages) <= MAX_MESSAGES:
        return messages

    to_compress = messages[:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]

    lines = []
    for m in to_compress:
        role = getattr(m, "type", "msg")
        raw = m.content if isinstance(m.content, str) else json.dumps(m.content)[:300]
        lines.append(f"[{role}] {raw[:250]}")

    summary_req = HumanMessage(
        content=(
            "Summarise the conversation so far in <= 120 words, preserving key"
            " decisions, tool results, and open questions:\n\n"
            + "\n".join(lines)
        )
    )
    summary_msg = await llm.ainvoke([summary_req])
    summary_text = (
        summary_msg.content
        if isinstance(summary_msg.content, str)
        else json.dumps(summary_msg.content)
    )
    return [SystemMessage(content=f"[Conversation summary]\n{summary_text}")] + recent


def _build_system_prompt(state: AgentState) -> str:
    """Build the full system prompt with context injection."""
    base = (
        "You are an expert course-creation assistant.\n"
        "Your job is to help users build rich, well-structured syllabuses.\n\n"
        "## How you work\n"
        "1. When the user asks you to create a syllabus, first call `set_plan` with all steps.\n"
        "2. Execute each step in order. For search steps, call `web_search` / `scrape_page`.\n"
        "3. Use the frontend tools to build the syllabus structure and content.\n"
        "4. Call `mark_step_done` after completing each step.\n\n"
        "## Tools available\n"
        "### Frontend tools (dispatched automatically by CopilotKit)\n"
        "- create_syllabus(id, title, subject, description?)\n"
        "- add_chapter(syllabusId, chapterId, title, description?)\n"
        "- add_lesson(chapterId, lessonId, title, content) -> validates content\n"
        "- update_lesson_content(lessonId, content) -> REPLACES content, validates\n"
        "- append_lesson_content(lessonId, blocks) -> APPENDS blocks, validates\n"
        "- read_lesson(lessonId, from?, to?) -> fetch full BlockNote content\n"
        "- remove_chapter(chapterId)\n"
        "- remove_lesson(lessonId)\n"
        "- report_render_error(lessonId, error)\n\n"
        "### Mutation contract (CRITICAL)\n"
        "Every mutation tool (`add_lesson`, `update_lesson_content`, `append_lesson_content`)\n"
        "returns a JSON object:\n"
        "  - on success: { ok: true, lessonId, blocks | appended | totalBlocks }\n"
        "  - on failure: { ok: false, error: '<message>', hint: '<what to do>' }\n"
        "If you receive { ok: false }, the store was NOT modified. Read the `error`\n"
        "and `hint`, fix the BlockNote JSON, and retry the SAME tool with corrected\n"
        "content. Do NOT proceed as if the write succeeded. Do NOT call a different\n"
        "tool to 'work around' the validation error.\n\n"
        "### Self-verification (REQUIRED after content mutations)\n"
        "After a successful `add_lesson`, `update_lesson_content`, or\n"
        "`append_lesson_content`, call `read_lesson(lessonId)` to confirm the\n"
        "content is actually in the store and matches what you intended to write.\n"
        "If the returned `totalBlocks` or content does not match your intent, fix\n"
        "it with another mutation tool. Do this ONCE per mutation (not in a loop).\n\n"
        "### When to append vs replace\n"
        "- Use `append_lesson_content` whenever you are ADDING material to an\n"
        "  existing lesson. This is the default for enrichment.\n"
        "- Use `update_lesson_content` only when you must REPLACE the entire lesson\n"
        "  (e.g. complete rewrite). Avoid it for incremental additions — it loses\n"
        "  the previous content.\n\n"
        "### Server-side tools\n"
        "- set_plan(steps) -> create execution plan\n"
        "- mark_step_done(step_id) -> mark step complete\n"
        "- web_search(query) -> search the web\n"
        "- scrape_page(url) -> scrape a page\n\n"
        "## BlockNote content format\n"
        "Every lesson's `content` field must be a valid BlockNote JSON array.\n"
        "Each block:\n"
        "  { type, props?, content?, children? }\n\n"
        "Supported block types and their props:\n"
        "  paragraph          - props: textAlignment\n"
        "  heading            - props: level (1|2|3), textAlignment\n"
        "  bulletListItem     - props: textAlignment\n"
        "  numberedListItem   - props: textAlignment\n"
        "  checkListItem      - props: checked (bool), textAlignment\n"
        "  table              - content: tableContent (see below)\n"
        "  image              - props: url, caption, textAlignment\n"
        "  video              - props: url, caption, textAlignment\n"
        "  audio              - props: url, caption\n"
        "  file               - props: url, name, caption\n"
        "  codeBlock          - props: language\n\n"
        "Inline content array (used in most block types):\n"
        "  { type: 'text', text: '..', styles?: { bold, italic, underline,\n"
        "    strikethrough, code, textColor, backgroundColor } }\n"
        "  { type: 'link', href: '..', content: [text nodes] }\n\n"
        "Table format:\n"
        "  content: { type: 'tableContent', rows: [\n"
        "    { cells: [ [inlineContent], ... ] }\n"
        "  ]}\n\n"
        "RULES:\n"
        "1. NEVER output plain text outside a block.\n"
        "2. Always use inline content arrays for text-bearing blocks.\n"
        "3. Use heading level 2 for section titles, level 3 for sub-sections.\n"
        "4. Keep lessons focused; split large topics into multiple lessons.\n"
        "5. Do NOT wrap the JSON in markdown fences.\n\n"
        "## CONCRETE EXAMPLES (copy this shape exactly)\n"
        "Minimal single paragraph (for a request like \"replace content with: hamdi is wow\"):\n"
        "  content: [\n"
        "    { \"type\": \"paragraph\", \"content\": [ { \"type\": \"text\", \"text\": \"hamdi is wow\" } ] }\n"
        "  ]\n\n"
        "Heading + paragraph + bullet list:\n"
        "  content: [\n"
        "    { \"type\": \"heading\", \"props\": { \"level\": 2 }, \"content\": [ { \"type\": \"text\", \"text\": \"Greetings\" } ] },\n"
        "    { \"type\": \"paragraph\", \"content\": [ { \"type\": \"text\", \"text\": \"Say hi in English:\" } ] },\n"
        "    { \"type\": \"bulletListItem\", \"content\": [ { \"type\": \"text\", \"text\": \"Hello\" } ] },\n"
        "    { \"type\": \"bulletListItem\", \"content\": [ { \"type\": \"text\", \"text\": \"Hi\" } ] }\n"
        "  ]\n\n"
        "Bold text inside a paragraph:\n"
        "  { \"type\": \"paragraph\", \"content\": [\n"
        "      { \"type\": \"text\", \"text\": \"This is \" },\n"
        "      { \"type\": \"text\", \"text\": \"important\", \"styles\": { \"bold\": true } }\n"
        "  ] }\n\n"
        "## COMMON MISTAKES that produce `block[i].type must be a string`\n"
        "WRONG  { \"paragraph\": \"hamdi is wow\" }                       <- no top-level `type` field\n"
        "WRONG  { \"text\": \"hamdi is wow\" }                              <- inline node used as a block\n"
        "WRONG  \"hamdi is wow\"                                           <- plain string, not an object\n"
        "WRONG  [ \"hamdi is wow\" ]                                       <- array of strings\n"
        "WRONG  { \"type\": \"paragraph\", \"text\": \"hamdi is wow\" }      <- `text` must live inside a `content` array\n"
        "RIGHT  { \"type\": \"paragraph\", \"content\": [ { \"type\": \"text\", \"text\": \"hamdi is wow\" } ] }\n\n"
        "## ANTI-LOOP RULE (CRITICAL)\n"
        "If a mutation tool returns { ok: false } with the SAME error message twice\n"
        "in a row, STOP retrying blindly. You are producing the same invalid JSON.\n"
        "Instead: (a) re-read the examples above, (b) mentally write out the exact\n"
        "object {\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"...\"}]},\n"
        "(c) send ONE corrected call. If it still fails, respond to the user with\n"
        "the error and stop — do not call the tool a third time.\n"
    )

    ctx_entries: list = state.get("copilotkit", {}).get("context", [])
    if ctx_entries:
        ctx_lines = ["## Current editor state"]
        for entry in ctx_entries:
            desc = entry.description if hasattr(entry, "description") else entry.get("description", "")
            raw = entry.value if hasattr(entry, "value") else entry.get("value", "[]")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                value_str = json.dumps(parsed, indent=2)
            except Exception:
                value_str = str(raw)
            ctx_lines.append(f"### {desc}")
            ctx_lines.append(value_str)
        base += "\n" + "\n".join(ctx_lines)

    plan = state.get("plan", [])
    plan_status = state.get("planStatus", "idle")
    current_index = state.get("currentStepIndex", 0)
    finished = state.get("finished", False)
    if plan:
        total = len(plan)
        done_count = sum(1 for s in plan if s.get("status") == "done")
        active_step = plan[current_index] if 0 <= current_index < total else None

        plan_lines = [
            "\n## Your active plan",
            "You previously committed to the following plan. It is live state, "
            "not a suggestion. You MUST work it to completion before replying to "
            "the user with a final answer.",
            "",
            f"Progress: {done_count}/{total} done   |   planStatus={plan_status}   |   "
            f"currentStepIndex={current_index}   |   finished={finished}",
            "",
            "Steps:",
        ]
        for step in plan:
            sid = step.get("id", "?")
            status = step.get("status", "")
            marker = {
                "pending": "[ ]",
                "in_progress": "[>]",
                "searching": "[~]",
                "done": "[x]",
            }.get(status, "[?]")
            arrow = "  <-- CURRENT" if sid == current_index and status != "done" else ""
            plan_lines.append(
                f"  {marker} Step {sid} ({step.get('type', '?')}, {status}): "
                f"{step.get('title', '')}{arrow}"
            )

        plan_lines += [
            "",
            "### Plan rules (read every turn)",
            "1. You OWN this plan. After you finish the work for the CURRENT step "
            "(step " + str(current_index) + " above), you MUST call "
            "`mark_step_done(step_id=" + str(current_index) + ")` in the SAME turn "
            "or the turn immediately after the final tool result, so the UI and "
            "state advance to the next step. Do not wait for the user to ask.",
            "2. Do NOT call `mark_step_done` before the step's work is actually "
            "complete (e.g. before the frontend tool has returned `ok: true`, "
            "or before you have verified with `read_lesson`).",
            "3. If the plan is wrong, out-of-date, or the user changed direction, "
            "replace it with a fresh `set_plan(...)` call. A new `set_plan` "
            "resets progress to step 0.",
            "4. Only stop taking actions (reply in plain text with no tool calls) "
            "when EITHER `planStatus == 'done'` / `finished == true`, OR the "
            "user asked a pure question that does not require plan work.",
            "5. Never silently abandon an in-progress plan. If you cannot proceed, "
            "tell the user why, then either `mark_step_done` (if genuinely "
            "done) or `set_plan` with a corrected plan.",
            "",
        ]
        if active_step is not None and active_step.get("status") != "done":
            plan_lines.append(
                f"### Focus right now: step {current_index} "
                f"({active_step.get('type','?')}) -> {active_step.get('title','')}"
            )
        elif plan_status == "done" or finished:
            plan_lines.append(
                "### Plan is complete. Summarize the result to the user; do not "
                "call more mutation tools unless the user asks for something new."
            )
        base += "\n".join(plan_lines)

    scraped = state.get("scraped_pages", [])
    if scraped:
        base += "\n\n## Research results (scraped pages)\n"
        for page in scraped[-6:]:
            base += f"### {page.get('title', page.get('url', ''))}\n"
            base += f"URL: {page.get('url', '')}\n"
            md = page.get("markdown", "")
            base += md[:3000] + ("[truncated]" if len(md) > 3000 else "") + "\n\n"

    return base


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Main chat node with system prompt, frontend+server tools, inline plan handling."""
    llm = get_llm()

    copilotkit_config = state.get("copilotkit", {})
    frontend_tools = copilotkit_config.get("actions", [])
    all_tools = frontend_tools + PYTHON_TOOLS

    bound = llm.bind_tools(all_tools, parallel_tool_calls=False)

    messages = list(state.get("messages", []))
    messages = await _maybe_summarize(messages, llm)

    system_prompt = _build_system_prompt(state)
    full_messages = [SystemMessage(content=system_prompt)] + messages

    response: AIMessage = await bound.ainvoke(full_messages, config)

    new_plan = list(state.get("plan", []))
    current_index = state.get("currentStepIndex", 0)
    plan_status = state.get("planStatus", "idle")
    activity = state.get("current_activity", "")
    finished = state.get("finished", False)

    tool_messages: list[ToolMessage] = []
    has_python_calls = False
    has_frontend_calls = False

    if response.tool_calls:
        for tc in response.tool_calls:
            name = tc["name"]
            args = tc["args"]

            if name == "set_plan":
                steps_input = args.get("steps", [])
                new_plan = [
                    PlanStep(
                        id=i,
                        type=s.get("type", "task"),
                        title=s.get("title", s.get("description", "")),
                        status="pending",
                        queries=s.get("queries"),
                        search_data=None,
                    )
                    for i, s in enumerate(steps_input)
                ]
                if new_plan:
                    new_plan[0] = {**new_plan[0], "status": "in_progress"}
                current_index = 0
                plan_status = "in_progress"
                activity = f"Plan created with {len(new_plan)} steps"
                tool_messages.append(
                    ToolMessage(content="Plan set successfully.", tool_call_id=tc["id"])
                )

            elif name == "mark_step_done":
                idx = args.get("step_id", current_index)
                if 0 <= idx < len(new_plan):
                    new_plan[idx] = {**new_plan[idx], "status": "done"}
                next_idx = idx + 1
                if next_idx >= len(new_plan):
                    plan_status = "done"
                    finished = True
                    current_index = next_idx
                    activity = "All steps completed"
                else:
                    new_plan[next_idx] = {**new_plan[next_idx], "status": "in_progress"}
                    current_index = next_idx
                    activity = f"Step {idx} done, starting step {next_idx}"
                tool_messages.append(
                    ToolMessage(content="Step marked done.", tool_call_id=tc["id"])
                )

            elif name in PYTHON_TOOL_NAMES:
                has_python_calls = True
            else:
                has_frontend_calls = True

    updated: dict[str, Any] = {
        "messages": [response, *tool_messages],
        "plan": new_plan,
        "currentStepIndex": current_index,
        "planStatus": plan_status,
        "current_activity": activity,
        "finished": finished,
    }

    await copilotkit_emit_state(state, updated)
    return updated


async def search_node(state: AgentState) -> dict[str, Any]:
    """Run search queries for the current pending search step."""
    from .search import run_search_step

    steps = list(state.get("plan", []))
    idx = state.get("currentStepIndex", 0)

    if idx >= len(steps):
        return {}

    step = steps[idx]
    queries = step.get("queries") or []
    results = await run_search_step(queries)

    steps[idx] = {**step, "status": "searching", "search_data": results}

    updated: dict[str, Any] = {
        "plan": steps,
        "search_results": results,
        "current_activity": f"Searching: {queries[0] if queries else ''}",
    }
    await copilotkit_emit_state(state, updated)
    return updated


async def scraper_node(state: AgentState) -> dict[str, Any]:
    """Scrape top URLs from the last search results."""
    from .search import scrape_selected

    search_data = state.get("search_results", [])
    scraped = await scrape_selected(search_data)

    steps = list(state.get("plan", []))
    idx = state.get("currentStepIndex", 0)

    if 0 <= idx < len(steps):
        steps[idx] = {**steps[idx], "status": "done", "search_data": search_data}

    next_idx = idx + 1
    plan_status = state.get("planStatus", "in_progress")
    if next_idx < len(steps):
        steps[next_idx] = {**steps[next_idx], "status": "in_progress"}
    else:
        plan_status = "done"

    updated: dict[str, Any] = {
        "plan": steps,
        "scraped_pages": state.get("scraped_pages", []) + scraped,
        "search_results": search_data,
        "currentStepIndex": next_idx,
        "planStatus": plan_status,
        "current_activity": f"Scraped {len(scraped)} pages",
    }
    await copilotkit_emit_state(state, updated)
    return updated


def route_after_chat(state: AgentState) -> str:
    """Route after chat_node.

    Rules (in order):
      1. If the last message is a ToolMessage (e.g. CopilotKit frontend tool
         just resumed us), loop back into chat_node so the LLM can react,
         unless the run is already `finished`.
      2. If the last AIMessage has python non-plan tool calls -> tools node.
      3. If the current plan step is a pending `search` step -> search_subgraph.
      4. If the last AIMessage has only plan tool calls
         (`set_plan` / `mark_step_done`) -> loop chat_node.
      5. If the last AIMessage has only frontend tool calls -> end (the
         CopilotKit client will execute the tool and resume us with a
         ToolMessage; the graph entry is chat_node so execution continues).
      6. If the last AIMessage has no tool calls but `planStatus` is still
         `in_progress` and we are not `finished`, loop chat_node so the LLM
         can advance the plan (emit the next mutation or `mark_step_done`).
      7. Otherwise -> end.
    """
    from langchain_core.messages import AIMessage as _AI, ToolMessage as _TM

    messages = state.get("messages", [])
    if not messages:
        return "end"

    finished = state.get("finished", False)
    last = messages[-1]

    if isinstance(last, _TM):
        return "end" if finished else "chat_node"

    tool_calls = getattr(last, "tool_calls", None) or []

    python_non_plan = [
        tc for tc in tool_calls
        if tc["name"] in PYTHON_TOOL_NAMES and tc["name"] not in PLAN_TOOL_NAMES
    ]
    if python_non_plan:
        return "tools"

    plan = state.get("plan", [])
    current_index = state.get("currentStepIndex", 0)
    if 0 <= current_index < len(plan):
        step = plan[current_index]
        if (
            step.get("type") == "search"
            and step.get("status") == "in_progress"
            and step.get("queries")
        ):
            return "search_subgraph"

    plan_calls = [tc for tc in tool_calls if tc["name"] in PLAN_TOOL_NAMES]
    non_plan_calls = [tc for tc in tool_calls if tc["name"] not in PLAN_TOOL_NAMES]

    if plan_calls and not non_plan_calls:
        return "end" if finished else "chat_node"

    if non_plan_calls:
        return "end"

    plan_status = state.get("planStatus", "idle")
    if plan_status == "in_progress" and not finished and plan:
        return "chat_node"

    return "end"


python_tools_node = ToolNode([t for t in PYTHON_TOOLS if t.name not in PLAN_TOOL_NAMES])
