"""Static frontend-tool shells for the deep agent.

The classic graph builds frontend tool definitions dynamically from
`config.configurable.frontend_tools` and routes them through a custom node.
`deepagents.create_deep_agent` compiles tools at build time, so we pre-declare
the known mutations as real LangChain tools whose body calls
`langgraph.types.interrupt(...)` — the frontend already handles that interrupt
shape via `useStream`. After confirmation we return a `Command(update=...)`
that also writes `last_authored_lesson` so the critic can run downstream.

IMPORTANT: to return a `Command(update=[ToolMessage(...)])` from a tool, the
`ToolMessage.tool_call_id` MUST match the AIMessage's pending tool_call. We get
it via `InjectedToolCallId` — reading it from `get_config().metadata` does NOT
work (metadata does not contain the tool_call_id at runtime) and produces the
error: ``Expected to have a matching ToolMessage in Command.update for tool
'X', got: [ToolMessage(..., tool_call_id='')]``.
"""
from __future__ import annotations
import json
from typing import Annotated, Any

from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage, SystemMessage
from langgraph.types import Command, interrupt


LESSON_MUTATION_TOOLS = {
    "addLesson",
    "updateLessonContent",
    "appendLessonContent",
    "patchLessonBlocks",
}


def _was_rejected(v: Any) -> bool:
    return isinstance(v, dict) and v.get("error") == "user_rejected"


def _finish(tc_id: str, tool_name: str, args: dict[str, Any], resume_value: Any):
    if _was_rejected(resume_value):
        tm = ToolMessage(
            content=json.dumps({"error": "user_rejected"}),
            tool_call_id=tc_id,
            status="error",
        )
        return Command(update={
            "messages": [tm, SystemMessage(content=(
                "The user rejected your last tool call. Do NOT retry the same "
                "mutation. Ask what they want changed or propose an alternative."
            ))],
            "stop_reason": "interrupted_by_user",
        })

    if isinstance(resume_value, (dict, list)):
        content = json.dumps(resume_value)
    elif resume_value is None:
        content = "ok"
    else:
        content = str(resume_value)
    tm = ToolMessage(content=content, tool_call_id=tc_id)

    update: dict[str, Any] = {"messages": [tm]}
    if tool_name in LESSON_MUTATION_TOOLS:
        lesson_id = args.get("lessonId") or args.get("chapterId") or "unknown"
        if tool_name in {"patchLessonBlocks", "appendLessonContent"}:
            blocks = args.get("blocks")
        else:
            blocks = args.get("content")
        update["last_authored_lesson"] = {
            "lesson_id": lesson_id,
            "tool": tool_name,
            "blocks": blocks if isinstance(blocks, list) else [],
            "title": args.get("title"),
        }
    return Command(update=update)


def _make_shell(name: str, description: str):
    @tool(name, description=description)
    def _shell(
        tool_call_id: Annotated[str, InjectedToolCallId],
        **kwargs,
    ) -> Command:
        """Frontend-executed mutation. The deep agent never sees the return
        value synchronously — LangGraph pauses on interrupt(), the browser
        executes the mutation, then resumes with a tool result."""
        resume = interrupt({
            "type": "frontend_tool_call",
            "tool_call_id": tool_call_id,
            "name": name,
            "args": kwargs,
        })
        return _finish(tool_call_id, name, kwargs, resume)
    _shell.name = name
    return _shell


# ---------------------------------------------------------------------------
# DEPRECATED (PR4) — lesson-mutation frontend shells.
# These used to pause the graph with `interrupt()` so the browser could mutate
# the zustand syllabus store. As of the `feat/supabase-mcp-curriculum` branch
# the agent writes lessons directly to Supabase through the curriculum-mcp
# server (see `agent/mcp_client.py` + `curriculum-mcp/`). The browser now
# subscribes to Supabase realtime and does NOT execute these tools anymore.
# Kept commented for reference while we finish migrating.
# ---------------------------------------------------------------------------
# addLesson = _make_shell(
#     "addLesson",
#     "Create a NEW lesson inside a given chapter with full BlockNote content."
#     " Args: chapterId (str), title (str), content (list of BlockNote blocks).",
# )
# updateLessonContent = _make_shell(
#     "updateLessonContent",
#     "Replace an existing lesson's entire content."
#     " Args: lessonId (str), title (str, optional), content (list of blocks).",
# )
# appendLessonContent = _make_shell(
#     "appendLessonContent",
#     "Append blocks to the end of an existing lesson."
#     " Args: lessonId (str), blocks (list of BlockNote blocks).",
# )
# patchLessonBlocks = _make_shell(
#     "patchLessonBlocks",
#     "Surgically patch specific blocks by id inside an existing lesson."
#     " Args: lessonId (str), blocks (list of {id, block}).",
# )
setPlan = _make_shell(
    "setPlan",
    "Publish a multi-step plan to the UI. Args: items (list of {id,title,status}).",
)


askUser = _make_shell(
    "askUser",
    "Ask the end user one or more structured questions BEFORE doing work that "
    "needs their input (topic, audience, language, grade, tone, length, etc.). "
    "The frontend renders each question as an interactive card: the user can "
    "pick one of the choices you provide, pick multiple if `multi` is true, or "
    "type their own answer when `allow_custom` is true. This is ALWAYS "
    "preferred over asking in plain chat — it guarantees every question gets "
    "an answer and dramatically reduces user typing.\n"
    "Args: questions (list of objects), each {\n"
    "  id: str (stable key, e.g. 'audience'),\n"
    "  prompt: str (the question to show),\n"
    "  choices: list[str] (2-6 suggested answers; optional if allow_custom),\n"
    "  allow_custom: bool (default true — let the user type a free answer),\n"
    "  multi: bool (default false — allow picking several choices),\n"
    "  placeholder: str (optional hint for the free-text input)\n"
    "}.\n"
    "Returns: {answers: {<id>: <string | list[string]>}}. Use those answers "
    "verbatim for the rest of the job. Do NOT call askUser again for the same "
    "ids unless the user asked to change them.",
)

updatePlanItem = _make_shell(
    "updatePlanItem",
    "Update a single plan item's status. Args: id (str), status (str).",
)


FRONTEND_SHELL_TOOLS = [
    askUser,
    # DEPRECATED (PR4) — moved to curriculum-mcp:
    # addLesson,
    # updateLessonContent,
    # appendLessonContent,
    # patchLessonBlocks,
    setPlan,
    updatePlanItem,
]

# DEPRECATED (PR4) — lesson mutations are now MCP tools, not frontend shells.
# Kept as an empty list so existing imports (e.g. in agent/graph.py, nodes.py)
# don't break while the migration finishes.
LESSON_SHELL_TOOLS: list = []
# LESSON_SHELL_TOOLS = [
#     addLesson,
#     updateLessonContent,
#     appendLessonContent,
#     patchLessonBlocks,
# ]
