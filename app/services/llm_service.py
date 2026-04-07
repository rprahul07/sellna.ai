"""LLM Service — pluggable provider-aware async client.

Supports:
  - Groq          → LLM_PROVIDER=groq    + GROQ_API_KEY=gsk_...
  - Grok (xAI)    → LLM_PROVIDER=grok    + GROK_API_KEY=xai-...
  - OpenAI        → LLM_PROVIDER=openai  + OPENAI_API_KEY=sk-...
  - Ollama        → LLM_PROVIDER=ollama  (no key needed)
  - Custom        → LLM_PROVIDER=custom  + CUSTOM_BASE_URL + CUSTOM_API_KEY

All providers use the OpenAI Python SDK — only the base_url and api_key differ.
Switch providers simply by changing LLM_PROVIDER in your .env file.
"""

from __future__ import annotations

import asyncio
import json
import time
from functools import lru_cache
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_settings = get_settings()


class LLMService:
    """Async LLM wrapper — provider is selected at construction from settings."""

    def __init__(self) -> None:
        provider = _settings.llm_provider
        api_key = _settings.llm_api_key or "placeholder"
        base_url = _settings.llm_base_url

        logger.info(
            "llm_service.init",
            provider=provider,
            model=_settings.llm_model,
            base_url=base_url,
        )

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._provider = provider
        
        # Concurrency control to prevent hitting rate limits (especially for free tiers)
        limit = 1 if provider == "apifree" else 5
        self._semaphore = asyncio.Semaphore(limit)

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
        async with self._semaphore:
            model = model or _settings.llm_model
            temperature = temperature if temperature is not None else _settings.llm_temperature
            max_tokens = max_tokens or _settings.llm_max_tokens

            # ------------------------------------------------------------------
            # Custom Provider handling for APIFree (not OpenAI compatible)
            # ------------------------------------------------------------------
            if self._provider == "apifree":
                combined_message = ""
                for msg in messages:
                    role = msg.get("role", "user").upper()
                    content = msg.get("content", "")
                    combined_message += f"[{role}]: {content}\n\n"
                
                if json_mode:
                    combined_message += "\nIMPORTANT: You MUST respond with ONLY valid JSON. No markdown, no HTML, no explanation, no code fences."

                t0 = time.perf_counter()
                max_retries = 3
                retry_delay = 25  # apifreellm free tier enforces a strict 25s delay
                
                for attempt in range(max_retries):
                    try:
                        headers = {
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {_settings.llm_api_key}",
                        }
                        payload = {
                            "message": combined_message.strip(),
                            "model": model,
                        }
                        async with httpx.AsyncClient(timeout=120.0) as client:
                            endpoint = _settings.llm_base_url.rstrip("/") + "/chat"
                            resp = await client.post(endpoint, json=payload, headers=headers)
                            resp.raise_for_status()
                            data = resp.json()
                            
                            if not data.get("success"):
                                raise ValueError(f"APIFree returned failure: {data}")
                                
                            content = data.get("response", "")
                            
                        elapsed = time.perf_counter() - t0
                        logger.info(
                            "llm.chat.complete",
                            provider=self._provider,
                            model=model,
                            elapsed_ms=round(elapsed * 1000),
                        )
                        return content
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429 and attempt < max_retries - 1:
                            logger.warning(f"APIFree Rate Limit Hit (429). Waiting {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                            await asyncio.sleep(retry_delay)
                            continue
                        logger.error("llm.chat.error", provider=self._provider, error=str(exc), model=model)
                        raise
                    except Exception as exc:
                        logger.error("llm.chat.error", provider=self._provider, error=str(exc), model=model)
                        raise

            # ------------------------------------------------------------------
            # Standard OpenAI-Compatible SDK path
            # ------------------------------------------------------------------

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 0.8,
            }

            # JSON mode handling:
            #  - ollama  → inject prompt instruction + response_format
            #  - groq / openai / grok → native response_format param
            if json_mode:
                if self._provider == "ollama":
                    # Inject a JSON instruction at the top of the system message
                    if messages and messages[0]["role"] == "system":
                        messages[0]["content"] += "\nReturn ONLY JSON."
                    kwargs["response_format"] = {"type": "json_object"}
                else:
                    # Native JSON mode for Groq/OpenAI/Grok
                    kwargs["response_format"] = {"type": "json_object"}

            if extra_kwargs:
                kwargs.update(extra_kwargs)

            t0 = time.perf_counter()
            try:
                response = await self._client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                
                elapsed = time.perf_counter() - t0
                logger.info(
                    "llm.chat.complete",
                    provider=self._provider,
                    model=model,
                    elapsed_ms=round(elapsed * 1000),
                )
                return content
            except Exception as exc:
                logger.error(
                    "llm.chat.error",
                    provider=self._provider,
                    model=model,
                    error=str(exc),
                )
                raise


@lru_cache
def get_llm_service() -> LLMService:
    return LLMService()
