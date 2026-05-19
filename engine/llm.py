"""Client LLM abstrait — endpoint OpenAI-compatible (DeepSeek par défaut).

Le provider détermine l'URL de base par défaut ; LLM_BASE_URL la surcharge
(utile pour un LLM local ou un proxy).
"""
from __future__ import annotations

from typing import Any

import httpx

import config

PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
    "local": "http://localhost:8000/v1",
}

TIMEOUT = httpx.Timeout(120.0, connect=15.0)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.LLM_MODEL
        self.api_key = api_key or config.LLM_API_KEY
        self.base_url = (base_url or config.LLM_BASE_URL or PROVIDER_BASE_URLS.get(self.provider, "")).rstrip("/")
        if not self.base_url:
            raise LLMError(f"Aucune URL de base pour le provider '{self.provider}'")

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise LLMError(f"LLM {resp.status_code}: {resp.text[:500]}")
            return resp.json()
