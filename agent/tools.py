from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool


class StepInput(BaseModel):
    type: Literal["task", "search"] = Field(
        description="'task' for a plain execution step, 'search' for a step that requires web research first"
    )
    title: str = Field(description="Short description of what this step accomplishes")
    queries: Optional[list[str]] = Field(
        default=None,
        description="2-4 specific web search queries (REQUIRED when type='search', omit for 'task')"
    )


class SetPlanInput(BaseModel):
    steps: list[StepInput] = Field(
        description="Ordered list of all steps needed to complete this request. "
                    "Mix task and search steps. Search steps will automatically "
                    "trigger web research before you write any content."
    )


@tool(args_schema=SetPlanInput)
def set_plan(steps: list) -> str:
    """
    Create the full execution plan for this request.
    Call this ONCE at the very beginning before doing any work.
    Each step is either a plain 'task' or a 'search' step with queries.
    Search steps run web research automatically — you will receive the
    scraped content in your context before being asked to write content.
    """
    return "Plan created"


class MarkStepDoneInput(BaseModel):
    step_id: int = Field(description="ID of the step you just finished")


@tool(args_schema=MarkStepDoneInput)
def mark_step_done(step_id: int) -> str:
    """
    Mark a plan step as completed.
    Call this after you finish all work for the current step.
    The next step will be activated automatically.
    """
    return "Step marked done"


PLAN_TOOLS = [set_plan, mark_step_done]
PLAN_TOOL_NAMES: set[str] = {t.name for t in PLAN_TOOLS}
