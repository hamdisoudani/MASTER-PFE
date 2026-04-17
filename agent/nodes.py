from langchain_core.messages import AIMessage, ToolMessage
from agent.state import AgentState
from agent.tools import get_tools, execute_tool
from agent.llm import get_llm


async def chat_node(state: AgentState, config: dict) -> dict:
    model = get_llm(config).bind_tools(get_tools())
    messages = _maybe_trim(state["messages"])
    response: AIMessage = await model.ainvoke(messages, config)
    return {"messages": [response]}


async def python_tools_node(state: AgentState, config: dict) -> dict:
    last: AIMessage = state["messages"][-1]
    output: dict = {"messages": []}
    for tc in last.tool_calls:
        state_patch = await execute_tool(tc["name"], tc["args"], config)
        output.update(state_patch)
        output["messages"].append(
            ToolMessage(content=str(state_patch), tool_call_id=tc["id"])
        )
    return output


def _maybe_trim(messages: list) -> list:
    if len(messages) <= 20:
        return messages
    system = [m for m in messages if getattr(m, "type", None) == "system"]
    rest = [m for m in messages if getattr(m, "type", None) != "system"]
    return system + rest[-18:]
