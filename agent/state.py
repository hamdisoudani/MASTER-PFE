from __future__ import annotations
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Pure ReAct agent state. Messages are the only persisted channel.

    Frontend tool schemas are supplied per-run via
    `config["configurable"]["frontend_tools"]` and are bound alongside the
    Python tools. When the LLM calls a frontend tool we pause the graph via
    `langgraph.types.interrupt(...)`; the browser executes the mutation and
    resumes with `Command(resume=result)` which becomes the ToolMessage
    content for the next chat turn.

    `stop_reason` is set by `chat_node` at terminal steps so the UI can
    show WHY the run ended (graceful completion, internal error, user
    rejection of a tool, etc.) — inspired by OpenAI stop_reasons and
    open-swe's per-run status chips.
    """

    messages: Annotated[list, add_messages]
    editor_context: Optional[dict[str, Any]]
    stop_reason: Optional[str]
