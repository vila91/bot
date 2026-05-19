"""Boucle function calling multi-tour.

Appelle le LLM, exécute les tools demandés, réinjecte les résultats, et
recommence jusqu'à une réponse finale ou la limite MAX_TOOL_ROUNDS.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

import config

log = structlog.get_logger()


async def run_conversation(
    llm: Any,
    messages: list[dict[str, Any]],
    max_rounds: int | None = None,
) -> str:
    """Fait tourner la boucle LLM/tools. Modifie `messages` en place.

    Retourne le texte de la réponse finale de l'assistant.
    """
    from tools import TOOLS_DEFINITIONS, execute_tool

    rounds = max_rounds or config.MAX_TOOL_ROUNDS
    tools = TOOLS_DEFINITIONS()

    for _ in range(rounds):
        resp = await llm.complete(messages, tools=tools or None)
        choice = resp["choices"][0]
        msg = choice["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content") or ""

        for call in tool_calls:
            name = call["function"]["name"]
            raw_args = call["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            log.info("tool_call", tool=name, args=args)
            result = await execute_tool(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                }
            )

    log.warning("max_tool_rounds_reached", rounds=rounds)
    return "(Limite de tours d'outils atteinte — réponse interrompue.)"
