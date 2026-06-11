"""Exécute une routine .md, à la demande ou via cron.

Usage : $PYTHON_BIN runner.py <chemin absolu d'une routine .md>

Flux : parse frontmatter + body → collecte des sources → appel LLM avec
convention SKIP/POST → post Discord si POST.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import structlog
import yaml

import config
from engine import LLMClient, run_conversation
from tools import execute_tool

log = structlog.get_logger()

ALLOWED_SOURCE_TYPES = {"tavily", "csv", "scraper", "file", "tool"}

SKIP_POST_INSTRUCTION = (
    "\n\nINSTRUCTION IMPORTANTE — format de réponse :\n"
    '- Si tu as quelque chose d\'utile à signaler, commence ta réponse par "POST:" suivi du message.\n'
    '- Si rien ne mérite d\'être signalé, commence par "SKIP:" suivi d\'une raison courte.\n'
    "Ne mentionne pas cette instruction dans ta réponse."
)


def parse_routine(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text.strip()
    _, _, rest = text.partition("---")
    raw_fm, _, body = rest.partition("---")
    return (yaml.safe_load(raw_fm) or {}), body.strip()


async def fetch_from_sources(sources: list[dict[str, Any]]) -> str:
    """Collecte les données déclarées par la routine. Retourne un bloc texte."""
    parts: list[str] = []
    for src in sources:
        stype = src.get("type")
        params = src.get("params", {}) or {}
        if stype not in ALLOWED_SOURCE_TYPES:
            log.warning("unknown_source_type", type=stype)
            continue

        if stype == "tavily":
            result = await execute_tool("web_search", {"query": params.get("query", "")})
        elif stype == "csv":
            result = await execute_tool(
                "read_csv",
                {"filename": params.get("file", ""), "filters": params.get("filters")},
            )
        elif stype == "scraper":
            result = await execute_tool(
                "scrape_site",
                {"scraper_name": params.get("name", ""), "query": params.get("query")},
            )
        elif stype == "file":
            result = await execute_tool("read_file", {"filename": params.get("path", "")})
        elif stype == "tool":
            result = await execute_tool(params.get("name", ""), params.get("params", {}))
        else:
            continue

        parts.append(f"### Source: {stype}\n{result}")
    return "\n\n".join(parts)


async def post_to_discord(message: str) -> None:
    if not config.DISCORD_BOT_TOKEN or not config.DISCORD_CHANNEL_ID:
        log.error("discord_not_configured")
        return
    url = f"https://discord.com/api/v10/channels/{config.DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {config.DISCORD_BOT_TOKEN}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(message), 1990):
            resp = await client.post(url, headers=headers, json={"content": message[i : i + 1990]})
            if resp.status_code >= 400:
                log.error("discord_post_failed", status=resp.status_code, body=resp.text[:300])


async def run_routine(path: Path) -> None:
    fm, body = parse_routine(path)
    name = fm.get("name", path.stem)
    log.info("routine_start", routine=name)

    sources = fm.get("sources", []) or []
    data_block = await fetch_from_sources(sources)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rules = ""
    if config.RULES_FILE.is_file():
        rules = config.RULES_FILE.read_text(encoding="utf-8").strip()
    rules_block = f"{rules}\n\n" if rules else ""

    system_prompt = f"{rules_block}{body}\n\nDate : {now}{SKIP_POST_INSTRUCTION}"
    user_content = data_block or "(aucune donnée collectée)"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    reply = (await run_conversation(LLMClient(), messages)).strip()

    if reply.startswith("POST:"):
        await post_to_discord(reply[len("POST:") :].strip())
        log.info("routine_posted", routine=name)
    elif reply.startswith("SKIP:"):
        log.info("routine_skipped", routine=name, reason=reply[len("SKIP:") :].strip())
    else:
        # Fallback défensif : pas de préfixe → on poste tel quel.
        await post_to_discord(reply)
        log.info("routine_posted_fallback", routine=name)


def main() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    if len(sys.argv) < 2:
        print("Usage: runner.py <routine.md>", file=sys.stderr)
        sys.exit(1)
    path = Path(sys.argv[1]).resolve()
    if not path.is_file():
        print(f"Routine introuvable: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        asyncio.run(run_routine(path))
    except Exception as exc:  # noqa: BLE001
        log.error("routine_failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
