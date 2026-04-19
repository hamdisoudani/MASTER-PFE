"""LLM factory + provider family detection.

Emits a startup warning if LLM_API_KEY or SERPER_API_KEY is unset so
silent-auth failures don't surface mid-run as opaque 401s.
"""
from __future__ import annotations
import logging
import os

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

_WARNED = False


def _warn_once() -> None:
    global _WARNED
    if _WARNED:
        return
    _WARNED = True
    if not os.getenv("LLM_API_KEY"):
        logger.warning("LLM_API_KEY is not set — all LLM calls will fail with 401.")
    if not os.getenv("SERPER_API_KEY"):
        logger.warning("SERPER_API_KEY is not set — web_search will return an error dict.")


def get_model_family() -> str:
    """Return a coarse provider family derived from LLM_MODEL.

    Used by the message sanitizer and parallel_tool_calls gating.
    """
    name = os.getenv("LLM_MODEL", "").lower()
    if "mistral" in name or "mixtral" in name:
        return "mistral"
    if name.startswith("gpt-") or "openai" in name:
        return "openai"
    if "claude" in name:
        return "anthropic"
    if "gemini" in name:
        return "google"
    return "unknown"


def get_llm() -> ChatOpenAI:
    _warn_once()
    return ChatOpenAI(
        base_url=os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "mistralai/mistral-small-4-119b-2603"),
        temperature=0.2,
        streaming=True,
    )
