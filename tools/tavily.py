"""Core tool : recherche web via l'API Tavily."""
from __future__ import annotations

from typing import Any

import httpx

import config

from ._base import tool

_TAVILY_URL = "https://api.tavily.com/search"


@tool(
    "web_search",
    "Effectue une recherche web via Tavily et retourne les résultats "
    "ainsi qu'un résumé IA.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Requête de recherche"},
            "max_results": {
                "type": "integer",
                "description": "Nombre de résultats (défaut 5)",
            },
        },
        "required": ["query"],
    },
)
async def web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    if not config.TAVILY_KEY:
        return {"error": "TAVILY_KEY non configurée"}
    payload = {
        "api_key": config.TAVILY_KEY,
        "query": query,
        "max_results": max(1, min(int(max_results), 20)),
        "include_answer": True,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_TAVILY_URL, json=payload)
        if resp.status_code >= 400:
            return {"error": f"Tavily {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
    return {
        "query": query,
        "answer": data.get("answer", ""),
        "results": [
            {"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
            for r in data.get("results", [])
        ],
    }
