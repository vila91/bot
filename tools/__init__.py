"""Registre des tools : core + MD déclaratifs + scrapers.

Importer ce module enregistre les core tools (via leurs décorateurs) et
charge les tools dynamiques. `TOOLS_DEFINITIONS()` donne les schémas
exposés au LLM ; `execute_tool()` dispatche un appel.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

import structlog

from . import _base

# Import des modules core → exécute les décorateurs @tool.
from . import data_reader, introspect, memory, scheduler, scraper, tavily, tool_writer  # noqa: F401
from .md_loader import load_md_tools
from .scraper import load_scraper_tools

log = structlog.get_logger()


def reload_dynamic() -> dict[str, int]:
    """Recharge à chaud les tools MD et scrapers depuis DATA_DIR."""
    md = load_md_tools()
    sc = load_scraper_tools()
    log.info("tools_reloaded", md=md, scrapers=sc)
    return {"md": md, "scrapers": sc}


# Chargement initial des tools dynamiques.
reload_dynamic()


def TOOLS_DEFINITIONS() -> list[dict[str, Any]]:
    return [td.schema() for td in _base.all_tools().values()]


async def execute_tool(name: str, args: dict[str, Any] | None) -> str:
    """Exécute un tool et retourne son résultat sérialisé en JSON string."""
    td = _base.get(name)
    if td is None:
        return json.dumps({"error": f"Tool inconnu: {name}"}, ensure_ascii=False)
    args = args or {}
    try:
        if inspect.iscoroutinefunction(td.func):
            result = await td.func(**args)
        else:
            result = await asyncio.to_thread(lambda: td.func(**args))
    except Exception as exc:  # noqa: BLE001 — toute erreur tool est renvoyée au LLM
        log.warning("tool_error", tool=name, error=str(exc))
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


__all__ = ["TOOLS_DEFINITIONS", "execute_tool", "reload_dynamic"]
