from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class Block(BaseModel):
    id: Optional[str] = None
    type: str
    props: dict[str, Any] = Field(default_factory=dict)
    content: Any = None
    children: list["Block"] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class BlockPatch(BaseModel):
    op: Literal["replace", "insert_after", "insert_before", "delete"]
    block_id: str
    block: Optional[dict[str, Any]] = None
