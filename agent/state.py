"""Agent state definitions."""
from typing import Optional, Literal
from copilotkit import CopilotKitState


class AgentState(CopilotKitState):
    """
    Full agent state that extends CopilotKitState.

    CopilotKitState already includes:
      - messages: list of LangChain BaseMessage
      - copilotkit: CopilotKitProperties (actions, context, ...)

    We add application-specific fields here.
    """

    # Current plan produced by the planner node
    plan: Optional[list[str]] = None

    # High-level mode the agent is operating in
    mode: Literal["chat", "research", "plan"] = "chat"

    # Whether the last run finished
    finished: bool = False
