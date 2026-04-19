"""Pure LangGraph nodes (no CopilotKit).

Frontend tool schemas come from `config["configurable"]["frontend_tools"]`
(a list of dicts with `name`, `description`, `parameters`). They are bound
to the LLM alongside the Python tools. When the LLM emits a tool_call for
a frontend tool we stop the graph and let the client resume by submitting
the ToolMessage via `useStream.submit({messages:[ToolMessage]})`.
"""
from __future__ import annotations
import os
import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolNode

from agent.llm import get_llm
from agent.state import AgentState, PlanStep
from agent.tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES, PLAN_TOOL_NAMES
from agent.pusher_bridge import publish_tool_call, publish_activity

logger = logging.getLogger(__name__)

SYSTEM_BASE = """You are a course-syllabus building assistant. Plan first, then execute.

Call `set_plan` exactly ONCE at the start of every request with all steps
(mix of 'task' and 'search' steps). Use `mark_step_done` after each step.
Search steps run automatic web research — you do not need to call web_search
for those. When you have enough info, use the frontend tools (if provided) to
mutate the editor / syllabus."""


def _frontend_tools_from_config(config: RunnableConfig) -> list[StructuredTool]:
    """Convert frontend tool schemas from config into bindable LC tools.

    The client passes tool schemas like:
        {"name": "addChapter", "description": "...", "parameters": {...json-schema...}}
    We turn each into a no-op StructuredTool so the LLM can call it.
    """
    cfg = (config or {}).get("configurable", {}) or {}
    schemas = cfg.get("frontend_tools") or []
    out: list[StructuredTool] = []
    for s in schemas:
        name = s.get("name")
        if not name:
            continue
        params = s.get("parameters") or {"type": "object", "properties": {}}
        out.append(
            StructuredTool.from_function(
                func=lambda **_k: "",
                name=name,
                description=s.get("description", ""),
                args_schema=None,
                coroutine=None,
            )
        )
        # Override the args schema with raw JSON schema dict — LC supports this
        out[-1].args_schema = params  # type: ignore[assignment]
    return out


def _sanitize_for_mistral(messages: list) -> list:
    """Mistral rejects dangling tool results. Drop ToolMessages that don't match
    a preceding AIMessage tool_call, merge consecutive HumanMessages, and
    prepend an empty AIMessage if a ToolMessage appears after a Human/System."""
    cleaned: list = []
    pending_tool_ids: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage):
            pending_tool_ids = {tc["id"] for tc in (getattr(m, "tool_calls", None) or [])}
            cleaned.append(m)
            continue
        if isinstance(m, ToolMessage):
            if m.tool_call_id in pending_tool_ids:
                pending_tool_ids.discard(m.tool_call_id)
                cleaned.append(m)
            continue
        if isinstance(m, (HumanMessage, SystemMessage)):
            if cleaned and isinstance(cleaned[-1], ToolMessage):
                cleaned.append(AIMessage(content=""))
            if (
                isinstance(m, HumanMessage)
                and cleaned
                and isinstance(cleaned[-1], HumanMessage)
            ):
                prev = cleaned[-1]
                merged = (prev.content or "") + ("\n\n" if prev.content and m.content else "") + (m.content or "")
                cleaned[-1] = HumanMessage(content=merged)
                continue
            cleaned.append(m)
            continue
        cleaned.append(m)
    while cleaned and isinstance(cleaned[0], ToolMessage):
        cleaned.pop(0)
    return cleaned


def _build_system_prompt(state: AgentState) -> str:
    parts = [SYSTEM_BASE]
    ed = state.get("editor_context") or {}
    if ed:
        parts.append("\n\nCurrent editor context (read-only):\n" + str(ed)[:4000])
    plan = state.get("plan") or []
    if plan:
        lines = [f"  [{p['id']}] ({p['status']}) {p['type']}: {p['title']}" for p in plan]
        parts.append("\n\nCurrent plan:\n" + "\n".join(lines))
    return "".join(parts)


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = get_llm()
    frontend_tools = _frontend_tools_from_config(config)
    all_tools = frontend_tools + PYTHON_TOOLS
    bound = llm.bind_tools(all_tools, parallel_tool_calls=False)

    messages = list(state.get("messages", []))
    messages = _sanitize_for_mistral(messages)
    system_prompt = _build_system_prompt(state)
    full_messages = [SystemMessage(content=system_prompt)] + messages

    response: AIMessage = await bound.ainvoke(full_messages, config)

    new_plan = list(state.get("plan", []))
    current_index = state.get("currentStepIndex", 0)
    plan_status = state.get("planStatus", "idle")
    activity = state.get("current_activity", "")
    finished = state.get("finished", False)

    tool_messages: list[ToolMessage] = []
    thread_id = (config or {}).get("configurable", {}).get("thread_id") if config else None
    frontend_tool_names = {t.name for t in frontend_tools}

    if response.tool_calls:
        for tc in response.tool_calls:
            name = tc["name"]
            args = tc.get("args") or {}

            if name == "set_plan":
                steps_input = args.get("steps", []) if isinstance(args, dict) else []
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
                tool_messages.append(ToolMessage(content="Plan set successfully.", tool_call_id=tc["id"]))

            elif name == "mark_step_done":
                idx = args.get("step_id", current_index) if isinstance(args, dict) else current_index
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
                tool_messages.append(ToolMessage(content="Step marked done.", tool_call_id=tc["id"]))

            elif name in frontend_tool_names:
                # Notify UI over Pusher (best-effort); LangGraph stream will also deliver it.
                publish_tool_call(thread_id, tc.get("id", ""), name, args if isinstance(args, dict) else {})

    if activity:
        publish_activity(thread_id, activity)

    return {
        "messages": [response, *tool_messages],
        "plan": new_plan,
        "currentStepIndex": current_index,
        "planStatus": plan_status,
        "current_activity": activity,
        "finished": finished,
    }


async def search_node(state: AgentState) -> dict[str, Any]:
    from agent.search import run_search_step

    steps = list(state.get("plan", []))
    idx = state.get("currentStepIndex", 0)
    if idx >= len(steps):
        return {}
    step = steps[idx]
    queries = step.get("queries") or []
    results = await run_search_step(queries)
    steps[idx] = {**step, "status": "searching", "search_data": results}
    return {
        "plan": steps,
        "search_results": results,
        "current_activity": f"Searching: {queries[0] if queries else ''}",
    }


async def scraper_node(state: AgentState) -> dict[str, Any]:
    from agent.search import scrape_selected

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
    return {
        "plan": steps,
        "scraped_pages": list(state.get("scraped_pages", [])) + scraped,
        "search_results": search_data,
        "currentStepIndex": next_idx,
        "planStatus": plan_status,
        "current_activity": f"Scraped {len(scraped)} pages",
    }


def route_after_chat(state: AgentState) -> str:
    from langchain_core.messages import AIMessage as _AI, ToolMessage as _TM

    messages = state.get("messages", [])
    if not messages:
        return "end"

    finished = state.get("finished", False)
    last = messages[-1]

    if isinstance(last, _TM):
        return "end" if finished else "chat_node"

    tool_calls = getattr(last, "tool_calls", None) or []

    python_non_plan = [tc for tc in tool_calls if tc["name"] in PYTHON_TOOL_NAMES and tc["name"] not in PLAN_TOOL_NAMES]
    if python_non_plan:
        return "tools"

    plan = state.get("plan", [])
    current_index = state.get("currentStepIndex", 0)
    if 0 <= current_index < len(plan):
        step = plan[current_index]
        if step.get("type") == "search" and step.get("status") == "in_progress" and step.get("queries"):
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
