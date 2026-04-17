from langchain_core.messages import AIMessage, ToolMessage
from agent.state import AgentState
from agent.tools import PYTHON_TOOLS
from agent.llm import get_llm

PYTHON_TOOL_NAMES = {t.name for t in PYTHON_TOOLS}


async def chat_node(state: AgentState, config: dict) -> dict:
    model = get_llm(config).bind_tools(PYTHON_TOOLS)
    messages = _maybe_trim(state["messages"])
    response: AIMessage = await model.ainvoke(messages, config)
    return {"messages": [response]}


async def python_tools_node(state: AgentState, config: dict) -> dict:
    last: AIMessage = state["messages"][-1]
    tool_map = {t.name: t for t in PYTHON_TOOLS}
    results: list[ToolMessage] = []
    state_patch: dict = {}

    for tc in last.tool_calls:
        if tc["name"] not in tool_map:
            results.append(ToolMessage(content=f"Unknown tool: {tc['name']}", tool_call_id=tc["id"]))
            continue

        raw = await tool_map[tc["name"]].ainvoke(tc["args"])
        results.append(ToolMessage(content=str(raw), tool_call_id=tc["id"]))

        import json
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}

        if tc["name"] == "plan_tasks":
            state_patch["plan"] = data
        elif tc["name"] == "search_web":
            state_patch["search_results"] = data
        elif tc["name"] == "scrape_website":
            state_patch["scraped_content"] = data

    return {"messages": results, **state_patch}


def _maybe_trim(messages: list) -> list:
    if len(messages) <= 20:
        return messages
    system = [m for m in messages if getattr(m, "type", None) == "system"]
    rest = [m for m in messages if getattr(m, "type", None) != "system"]
    return system + rest[-18:]
