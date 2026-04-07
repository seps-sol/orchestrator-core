from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from seps.config import Settings


def get_chat_model(settings: Settings) -> BaseChatModel | None:
    provider = settings.effective_llm_provider()
    model = settings.model
    if provider == "anthropic" and settings.anthropic_api_key:
        amodel = model
        if amodel.startswith("gpt-"):
            amodel = "claude-sonnet-4-20250514"
        return ChatAnthropic(
            model=amodel,
            api_key=settings.anthropic_api_key,
            max_tokens=4096,
        )
    if provider == "openai" and settings.openai_api_key:
        openai_model = model if model.startswith("gpt-") else "gpt-5.4"
        return ChatOpenAI(model=openai_model, api_key=settings.openai_api_key)
    return None
