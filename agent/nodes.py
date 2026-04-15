"""LangGraph node implementations."""
from typing import cast
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from copilotkit.langgraph import copilotkit_emit_state, copilotkit_customize_config
from .state import AgentState
from .llm import build_llm

_llm = build_llm()


async def chat_node(state: AgentState, config: RunnableConfig) -> dict:
    config = copilotkit_customize_config(
        config,
        emit_messages=True,
        emit_intermediate_state=[
            {"state_key": "plan", "tool": "update_plan", "tool_argument": "steps"},
        ],
    )

    copilotkit_props = state.get("copilotkit", {})
    frontend_actions = copilotkit_props.get("actions", [])
    model = _llm.bind_tools(frontend_actions) if frontend_actions else _llm

    system_message = SystemMessage(
        content=(
            "You are a helpful AI assistant. "
            "When you create a plan, call the update_plan tool with the list of steps. "
            "Be concise, accurate, and collaborative."
        )
    )

    messages = [system_message, *cast(list, state["messages"])]
    response = await model.ainvoke(messages, config)

    return {
        "messages": [response],
        "finished": True,
    }


async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    config = copilotkit_customize_config(
        config,
        emit_messages=True,
        emit_intermediate_state=[
            {"state_key": "plan", "tool": "update_plan", "tool_argument": "steps"},
        ],
    )

    from langchain_core.tools import tool

    @tool
    def update_plan(steps: list[str]) -> str:
        """Update the current plan with a list of steps."""
        return "Plan updated"

    model = _llm.bind_tools([update_plan])

    system_message = SystemMessage(
        content=(
            "You are a planning assistant. "
            "Your only job is to call update_plan with a clear, ordered list of steps "
            "to accomplish the user's request. Keep each step short and actionable."
        )
    )

    messages = [system_message, *cast(list, state["messages"])]
    response = await model.ainvoke(messages, config)

    plan: list[str] = []
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            if tc.get("name") == "update_plan":
                plan = tc.get("args", {}).get("steps", [])
                break

    await copilotkit_emit_state(config, {"plan": plan})

    return {
        "messages": [response],
        "plan": plan,
        "mode": "plan",
    }
