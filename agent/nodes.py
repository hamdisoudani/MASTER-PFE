"""Pure-LangGraph ReAct nodes.

- `chat_node` calls the LLM with Python tools + frontend tool schemas
  (provided per-run via config.configurable.frontend_tools).
- When the LLM calls a Python tool, we route to the built-in `ToolNode`.
- When the LLM calls a *frontend* tool, we route to `frontend_tool_node`
  which calls `langgraph.types.interrupt(...)` so the browser can execute
  the mutation locally. The browser resumes with `Command(resume=result)`
  and the resumed value becomes the ToolMessage content.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.llm import get_llm
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a course-syllabus building assistant.

You have two kinds of tools:
  - Python tools (`web_search`, `scrape_page`) — you call them and receive results in the same turn.
  - Frontend tools (provided per session, e.g. `createSyllabus`, `addChapter`, `addLesson`, `updateLessonContent`, `appendLessonContent`) — these mutate the user's editor. You call them the same way; the browser applies the change and returns a short result.

Working style:
  - Think step-by-step in plain text before each action.
  - When the user asks you to build, edit, or extend a syllabus, DO IT with the frontend tools — do not just describe the change.
  - Use `web_search` + `scrape_page` only when you actually need fresh information.
  - Prefer short, well-formatted markdown in your assistant replies (headings, lists, bold).
  - After each frontend tool finishes, continue the work until the user's request is satisfied, then reply with a brief summary.
"""


def _frontend_tool_defs(config: RunnableConfig) -> list[dict[str, Any]]:
    cfg = (config or {}).get("configurable", {}) or {}
    schemas = cfg.get("frontend_tools") or []
    out: list[dict[str, Any]] = []
    for s in schemas:
        name = s.get("name")
        if not name:
            continue
        params = s.get("parameters") or {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": s.get("description", ""),
                    "parameters": params,
                },
            }
        )
    return out


def _frontend_tool_names(config: RunnableConfig) -> set[str]:
    return {
        d["function"]["name"]
        for d in _frontend_tool_defs(config)
        if d.get("function", {}).get("name")
    }


def _sanitize_for_mistral(messages: list) -> list:
    """Mistral rejects dangling tool results and double-user turns."""
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
    parts = [SYSTEM_PROMPT]
    ed = state.get("editor_context") or {}
    if ed:
        try:
            snap = json.dumps(ed)[:4000]
        except Exception:
            snap = str(ed)[:4000]
        parts.append("\n\nCurrent editor context (read-only):\n" + snap)
    return "".join(parts)


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    llm = get_llm()
    frontend_defs = _frontend_tool_defs(config)
    all_tools: list[Any] = list(PYTHON_TOOLS) + list(frontend_defs)
    bound = llm.bind_tools(all_tools, parallel_tool_calls=False)

    messages = _sanitize_for_mistral(list(state.get("messages", [])))
    full_messages = [SystemMessage(content=_build_system_prompt(state))] + messages

    response: AIMessage = await bound.ainvoke(full_messages, config)
    return {"messages": [response]}


async def frontend_tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Pause the graph and wait for the browser to execute a frontend tool.

    The client sees the interrupt payload on `stream.interrupt.value` and
    resumes via `Command(resume=<result>)`. The resumed value is wrapped in
    a ToolMessage keyed by the matching `tool_call_id`.
    """
    messages = list(state.get("messages", []))
    if not messages or not isinstance(messages[-1], AIMessage):
        return {}
    last: AIMessage = messages[-1]
    frontend_names = _frontend_tool_names(config)

    tool_messages: list[ToolMessage] = []
    for tc in last.tool_calls or []:
        if tc["name"] not in frontend_names:
            continue
        resume_value: Any = interrupt(
            {
                "type": "frontend_tool_call",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "args": tc.get("args") or {},
            }
        )
        if isinstance(resume_value, (dict, list)):
            content = json.dumps(resume_value)
        elif resume_value is None:
            content = "ok"
        else:
            content = str(resume_value)
        tool_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    return {"messages": tool_messages}


def route_after_chat(state: AgentState, config: RunnableConfig) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last = messages[-1]
    if not isinstance(last, AIMessage):
        return "end"
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return "end"

    frontend_names = _frontend_tool_names(config)
    has_frontend = any(tc["name"] in frontend_names for tc in tool_calls)
    has_python = any(tc["name"] in PYTHON_TOOL_NAMES for tc in tool_calls)

    if has_frontend:
        return "frontend_tools"
    if has_python:
        return "tools"
    return "end"
