import json
from typing import Any
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from copilotkit.langchain import copilotkit_emit_state

from .state import AgentState, PlanStep
from .tools import set_plan, mark_step_done, write_lesson_content, search_tool

SYSTEM_PROMPT = """You are **Syllabus Agent**, an AI research-and-writing assistant
that helps users build structured lesson plans (syllabi).

You operate inside a CopilotKit + LangGraph pipeline. Your capabilities:

1. **Plan**: Given a topic, create a multi-step research plan.
   - Each step is either a *search* step or a *write* step.
   - Emit the plan with `set_plan`.

2. **Search**: Use `search_tool` to query the web for relevant information.
   - After each search step completes, call `mark_step_done`.

3. **Write**: Synthesise search results into lesson content.
   - Call `write_lesson_content` to persist the content.

Always keep the user informed of progress via `copilotkit_emit_state`.
"""


def make_llm(temperature: float = 0.2):
    return ChatOpenAI(model="gpt-4o-mini", temperature=temperature, streaming=True)


tools = [set_plan, mark_step_done, write_lesson_content, search_tool]
tool_node = ToolNode(tools)


async def agent_node(state: AgentState) -> dict[str, Any]:
    llm = make_llm().bind_tools(tools)
    messages = state["messages"]

    if not any(m.content == SYSTEM_PROMPT for m in messages if isinstance(m, AIMessage)):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + list(messages)

    response = await llm.ainvoke(messages)

    await copilotkit_emit_state(
        {
            "plan_steps": [s.model_dump() for s in state.get("plan_steps", [])],
            "current_step_index": state.get("current_step_index", 0),
            "plan_status": state.get("plan_status", "idle"),
            "current_activity": state.get("current_activity", ""),
        }
    )

    return {"messages": [response]}


async def tool_executor(state: AgentState) -> dict[str, Any]:
    result = await tool_node.ainvoke(state)
    return result


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"
