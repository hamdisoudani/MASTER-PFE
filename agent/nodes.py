"""Pure-LangGraph ReAct nodes.

- `chat_node` calls the LLM with Python tools + frontend tool schemas
  (provided per-run via config.configurable.frontend_tools).
- When the LLM calls a Python tool, we route to the built-in `ToolNode`.
- When the LLM calls a *frontend* tool, we route to `frontend_tool_node`
  which calls `langgraph.types.interrupt(...)` so the browser can execute
  the mutation locally. The browser resumes with `Command(resume=result)`
  and the resumed value becomes the ToolMessage content.

Context/robustness middleware (see agent/middleware.py) is applied inside
`chat_node` before every model call, ported from langchain-ai/open-swe.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.llm import get_llm, get_model_family
from agent.middleware import compact_history, ensure_no_empty_ai
from agent.prompts import build_system_prompt
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS, PYTHON_TOOL_NAMES

logger = logging.getLogger(__name__)

# Default context budget ~ 60% of a 20k window; override via env.
CONTEXT_TOKEN_BUDGET = int(os.getenv("AGENT_CONTEXT_TOKEN_BUDGET", "12000"))


def _frontend_tool_defs(config: RunnableConfig) -> list[dict[str, Any]]:
    cfg = (config or {}).get("configurable", {}) or {}
    schemas = cfg.get("frontend_tools") or []
    out: list[dict[str, Any]] = []
    for item in schemas:
        name = item.get("name")
        if not name:
            continue
        params = item.get("parameters") or {"type": "object", "properties": {}}
        fn: dict[str, Any] = {
            "name": name,
            "description": item.get("description", ""),
            "parameters": params,
        }
        if item.get("strict") is True:
            fn["strict"] = True
        out.append({"type": "function", "function": fn})
    return out


def _frontend_tool_names(config: RunnableConfig) -> set[str]:
    return {
        d["function"]["name"]
        for d in _frontend_tool_defs(config)
        if d.get("function", {}).get("name")
    }


def _sanitize_for_mistral(messages: list) -> list:
    """Mistral rejects dangling tool results and double-user turns.

    FIXED: the old version overwrote `pending_tool_ids` on every AIMessage,
    so if two AIMessages appeared back-to-back (e.g. after an error retry)
    tool_call_ids from the first were silently dropped. We now union new
    ids in and only discard them when their matching ToolMessage arrives.
    """
    cleaned: list = []
    pending_tool_ids: set[str] = set()
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in (getattr(m, "tool_calls", None) or []):
                if tc.get("id"):
                    pending_tool_ids.add(tc["id"])
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


def _provider_sanitize(messages: list) -> list:
    """Provider-aware message cleanup. Mistral needs aggressive cleanup;
    other providers accept canonical histories."""
    family = get_model_family()
    if family == "mistral":
        return _sanitize_for_mistral(messages)
    return messages


async def chat_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Run one LLM step.

    Errors raised by the model provider (invalid tool args, auth, rate
    limit, network) are caught and persisted onto the thread as an
    AIMessage with `additional_kwargs["error"]`.

    `parallel_tool_calls` is gated on model family: disabled for Mistral
    (Structured Outputs + parallel calls is known-incompatible on some
    providers), enabled elsewhere. Override via LLM_PARALLEL_TOOLS=0|1.
    """
    llm = get_llm()
    frontend_defs = _frontend_tool_defs(config)
    all_tools: list[Any] = list(PYTHON_TOOLS) + list(frontend_defs)

    parallel_env = os.getenv("LLM_PARALLEL_TOOLS")
    if parallel_env is not None:
        parallel = parallel_env == "1"
    else:
        parallel = get_model_family() != "mistral"
    bound = llm.bind_tools(all_tools, parallel_tool_calls=parallel)

    raw = list(state.get("messages", []))
    compacted = compact_history(raw, token_budget=CONTEXT_TOKEN_BUDGET)
    compacted = ensure_no_empty_ai(compacted)
    messages = _provider_sanitize(compacted)

    full_messages = [SystemMessage(content=build_system_prompt(state, _frontend_tool_defs(config)))] + messages

    try:
        response: AIMessage = await bound.ainvoke(full_messages, config)
    except Exception as e:  # noqa: BLE001 — user-visible surfaced errors
        logger.exception("chat_node LLM call failed")
        err_payload = {"message": str(e) or repr(e), "type": type(e).__name__}
        err_msg = AIMessage(
            content=("⚠️ The run failed: " + (err_payload["message"][:500] or err_payload["type"])),
            additional_kwargs={"error": err_payload},
        )
        return {"messages": [err_msg], "stop_reason": "error"}

    has_tool_calls = bool(getattr(response, "tool_calls", None))
    out: dict[str, Any] = {"messages": [response]}
    if not has_tool_calls:
        out["stop_reason"] = "completed"
    return out


def _was_user_rejected(resume_value: Any) -> bool:
    return isinstance(resume_value, dict) and resume_value.get("error") == "user_rejected"


async def frontend_tool_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Pause the graph and wait for the browser to execute a frontend tool.

    If ANY tool call in the batch was rejected by the user, we append a
    SystemMessage telling the model to ask for clarification instead of
    retrying blindly, and we set stop_reason for the UI.
    """
    messages = list(state.get("messages", []))
    if not messages or not isinstance(messages[-1], AIMessage):
        return {}
    last: AIMessage = messages[-1]
    frontend_names = _frontend_tool_names(config)

    tool_messages: list[ToolMessage] = []
    any_rejected = False
    for tc in last.tool_calls or []:
        if tc["name"] not in frontend_names:
            continue
        try:
            resume_value: Any = interrupt(
                {
                    "type": "frontend_tool_call",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "args": tc.get("args") or {},
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("frontend tool interrupt failed")
            tool_messages.append(
                ToolMessage(
                    content=json.dumps({"error": str(exc), "type": exc.__class__.__name__}),
                    tool_call_id=tc["id"],
                    status="error",
                )
            )
            continue

        if _was_user_rejected(resume_value):
            any_rejected = True

        if isinstance(resume_value, (dict, list)):
            content = json.dumps(resume_value)
        elif resume_value is None:
            content = "ok"
        else:
            content = str(resume_value)
        tool_messages.append(ToolMessage(content=content, tool_call_id=tc["id"]))

    out: dict[str, Any] = {"messages": list(tool_messages)}
    if any_rejected:
        out["messages"].append(SystemMessage(
            content=(
                "The user rejected your last tool call. Do NOT retry the same mutation. "
                "Ask the user briefly what they want changed, or propose an alternative."
            )
        ))
        out["stop_reason"] = "interrupted_by_user"
    return out


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
