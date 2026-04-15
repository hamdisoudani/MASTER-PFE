"""LLM factory \u2014 ChatOpenAI pointed at NVIDIA NIM."""
import os
from langchain_openai import ChatOpenAI


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=os.getenv("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "mistralai/mistral-small-4-119b-2603"),
        streaming=True,
    )


# Alias used by nodes.py
build_llm = get_llm
