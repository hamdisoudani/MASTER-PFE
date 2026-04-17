import json
from typing import Any
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from copilotkit.langchain import copilotkit_emit_state

from .state import AgentState, PlanStep
crom .tools import set_plan, mark_step_done
from .search import run_search_step, scrape_selected

import os

llm = ChatOpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ.get("NVIDIA_API_KEY", ""),
    model="mistralai/mistral-small-4-119b-2603",
    temperature=0.2,
)

tools = [set_plan, mark_step_done]
llm_with_tools = llm.bind_tools(tools)


async def chat_node(state: AgentState) -> dict[str, Any]:
    """Main chat node — calls LLM, handles plan tools inline, detects pending search."""

    messages = state["messages"]
    response: AIMessage = await llm_with_tools.ainvoke(messages)

    new_plan_steps = list(state.get("planSteps", []))
    current_index = state.get("currentStepIndex", 0)
    plan_status = state.get("planStatus", "idle")
    activity = state.get("current_activity", "")

    tool_messages: list[ToolMessage] = []

    if response.tool_calls:
        for tc in response.tool_calls:
            name = tc["name"]
            args = tc["args"]

            if name == "set_plan":
                steps_input = args.get("steps", [])
                new_plan_steps = [
                    PlanStep(
                        type=s["type"],
                        description=s["description"],
                        status="pending",
                        queries=s.get("queries"),
                        search_data=None,
                    )
                    for s in steps_input
                ]
                current_index = 0
                plan_status = "in_progress"
                activity = "Plan created"
                tool_messages.append(
                    ToolMessage(content="Plan set successfully.", tool_call_id=tc["id"])
                )

            elif name == "mark_step_done":
                idx = args.get("step_index", current_index)
                if 0 <= idx < len(new_plan_steps):
                    new_plan_steps[idx] = {**new_plan_steps[idx], "status": "done"}
                    current_index = idx + 1
                    if current_index >= len(new_plan_steps):
                        plan_status = "done"
                    activity = f"Step {idx} completed"
                tool_messages.append(
                    ToolMessage(content="Step marked done.", tool_call_id=tc["id"])
                )

    updated_state: dict[str, Any] = {
        "messages": [response, *tool_messages],
        "planSteps": new_plan_steps,
        "currentStepIndex": current_index,
        "planStatus": plan_status,
        "current_activity": activity,
    }

    await copilotkit_emit_state(state, updated_state)
    return updated_state


async def search_node(state: AgentState) -> dict[str, Any]:
    """Run search queries for the current pending search step."""
    steps = list(state.get("planSteps", []))
    idx = state.get("currentStepIndex", 0)

    if idx >= len(steps):
        return {}

    step = steps[idx]
    queries = step.get("queries") or []
    results = await run_search_step(queries)

    steps[idx] = {**step, "status": "searching", "search_data": {"results": results}}

    updated: dict[str, Any] = {
        "planSteps": steps,
        "search_results": results,
        "current_activity": f"Searched: {queries[0] if queries else ''}",
    }
    await copilotkit_emit_state(state, updated)
    return updated


async def scraper_node(state: AgentState) -> dict[str, Any]:
    """Scrape top URLs from the last search results."""
    results = state.get("search_results", [])
    urls = [r.get("link", "") for r in results[:3] if r.get("link")]
    scraped = await scrape_selected(urls)

    steps = list(state.get("planSteps", []))
    idx = state.get("currentStepIndex", 0)

    if 0 <= idx < len(steps):
        step = steps[idx]
        existing_data = step.get("search_data") or {}
        steps[idx] = {
            **step,
            "status": "done",
            "search_data": {**existing_data, "scraped": scraped},
        }

    updated: dict[str, Any] = {
        "planSteps": steps,
        "scraped_pages": scraped,
        "currentStepIndex": idx + 1,
        "current_activity": f"Scraped {len(scraped)} pages",
    }
    await copilotkit_emit_state(state, updated)
    return updated


python_tools_node = ToolNode(tools)
