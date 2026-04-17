from langchain_core.messages import AIMessage, ToolMessage
from agent.state import AgentState
from agent.tools import get_tools, execute_tool
from agent.model import get_model


async def chat_node(state: AgentState, config: dict) -> dict:
    model = get_model().bind_tools(get_tools())
    messages = _maybe_trim(state["messages"])
    response: AIMessage = await model.ainvoke(messages, config)
    return {"messages": [response]}


async def python_tools_node(state: AgentState, config: dict) -> dict:
    last: AIMessage = state["messages"][-1]
    results: list[ToolMessage] = []
    for tc in last.tool_calls:
        result = await execute_tool(tc["name"], tc["args"], config)
        results.append(
            ToolMessage(content=str(result), tool_call_id=tc["id"])
        )
    return {"messages": results}


def _maybe_trim(messages: list, max_tokens: int = 80_000) -> list:
    """Very rough trim: drop oldest non-system messages when list grows large."""
    if len(messages) <= 20:
        return messages
    system = [m for m in messages if getattr(m, "type", None) == "system"]
    rest = [m for m in messages if getattr(m, "type", None) != "system"]
    return system + rest[-18:]
