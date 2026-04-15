"""LLM factory — reads provider/model/key from environment variables."""
import os
from typing import Union
from langchain_core.language_models.chat_models import BaseChatModel


def build_llm() -> BaseChatModel:
    """
    Return a LangChain chat model configured from environment variables.

    ENV VARS:
        LLM_PROVIDER  - openai | anthropic | google | custom  (default: openai)
        LLM_MODEL     - model name (default: gpt-4o)
        LLM_API_KEY   - provider API key
        LLM_BASE_URL  - optional custom base URL (for proxied / local LLMs)
    """
    provider: str = os.getenv("LLM_PROVIDER", "openai").lower()
    model: str = os.getenv("LLM_MODEL", "gpt-4o")
    api_key: str = os.getenv("LLM_API_KEY", "")
    base_url: Union[str, None] = os.getenv("LLM_BASE_URL") or None

    if provider in ("openai", "custom"):
        from langchain_openai import ChatOpenAI
        kwargs: dict = {"model": model, "streaming": True}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        kwargs = {"model_name": model, "streaming": True}
        if api_key:
            kwargs["anthropic_api_key"] = api_key
        return ChatAnthropic(**kwargs)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        kwargs = {"model": model, "streaming": True}
        if api_key:
            kwargs["google_api_key"] = api_key
        return ChatGoogleGenerativeAI(**kwargs)

    raise ValueError(
        f"Unsupported LLM_PROVIDER='{provider}'. "
        "Valid values: openai, anthropic, google, custom"
    )
