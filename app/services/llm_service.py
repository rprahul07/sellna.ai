"""LLM Service — pluggable provider-aware async client.

Supports:
  - Grok (xAI)    → LLM_PROVIDER=grok    + GROK_API_KEY=xai-...
  - OpenAI        → LLM_PROVIDER=openai  + OPENAI_API_KEY=sk-...
  - Ollama        → LLM_PROVIDER=ollama  (no key needed)
  - Custom        → LLM_PROVIDER=custom  + CUSTOM_BASE_URL + CUSTOM_API_KEY

All providers use the OpenAI Python SDK — only the base_url and api_key differ.
Switch providers simply by changing LLM_PROVIDER in your .env file.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


class LLMService:
    """Async LLM wrapper — provider is selected at construction from settings."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        provider = _settings.llm_provider
        api_key = _settings.llm_api_key or "placeholder"   # Ollama/local don't need a real key
        base_url = _settings.llm_base_url

        logger.info(
            "llm_service.init",
            provider=provider,
            model=_settings.llm_model,
            base_url=base_url,
        )

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._provider = provider

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat request and return the assistant reply as a string."""
        model = model or _settings.llm_model
        temperature = temperature if temperature is not None else _settings.llm_temperature
        max_tokens = max_tokens or _settings.llm_max_tokens

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # JSON mode handling — Ollama supports it via the API BUT requires the
        # system prompt to explicitly ask for JSON too (belt-and-suspenders).
        # For openai/grok we use the native response_format parameter.
        if json_mode:
            if self._provider == "ollama":
                # Inject a JSON instruction at the top of the system message
                msgs = list(messages)
                if msgs and msgs[0]["role"] == "system":
                    msgs[0] = {
                        "role": "system",
                        "content": msgs[0]["content"] + "\n\nIMPORTANT: You MUST respond with ONLY valid JSON. No markdown, no explanation, no code fences.",
                    }
                else:
                    msgs.insert(0, {
                        "role": "system",
                        "content": "You MUST respond with ONLY valid JSON. No markdown, no explanation, no code fences.",
                    })
                kwargs["messages"] = msgs
                # Ollama also supports format param via response_format
                kwargs["response_format"] = {"type": "json_object"}
            else:
                kwargs["response_format"] = {"type": "json_object"}

        if extra_kwargs:
            kwargs.update(extra_kwargs)

        t0 = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(**kwargs)
            elapsed = time.perf_counter() - t0
            content = response.choices[0].message.content or ""
            logger.info(
                "llm.chat.complete",
                provider=self._provider,
                model=model,
                elapsed_ms=round(elapsed * 1000),
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
            )
            return content
        except Exception as exc:
            logger.error("llm.chat.error", provider=self._provider, error=str(exc), model=model)
            raise

    async def classify(self, text: str, categories: list[str], context: str = "") -> str:
        """Single-turn classification helper — returns the best matching category."""
        system = (
            f"You are a precise classifier. Given text, choose the SINGLE best category from: "
            f"{', '.join(categories)}. Respond with ONLY the category name, no explanation."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{context}\n\nText: {text}"},
        ]
        result = await self.chat(messages, temperature=0.0, max_tokens=50)
        result = result.strip().strip('"').strip("'")
        return result if result in categories else categories[0]


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    return LLMService()
