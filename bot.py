"""Point d'entrée : bot Discord + boucle LLM.

Écoute uniquement DISCORD_CHANNEL_ID. Chaque message déclenche une
complétion LLM multi-tour avec function calling. Les slash commands
sont gérées séparément du flux LLM.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

import discord
import structlog
from discord import app_commands

import config
from engine import LLMClient, run_conversation
from tools import _base
from tools.memory import append_exchange, context_messages

DEFAULT_RULES = (
    "Tu es un assistant Discord autonome. Tu utilises tes tools pour "
    "répondre aux questions et exécuter des tâches. Sois concis et utile."
)

MAX_DISCORD_LEN = 1990


def setup_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


log = structlog.get_logger()


def build_system_prompt() -> str:
    """Assemble le system prompt dynamiquement (rules + date + tools + hint)."""
    if config.RULES_FILE.is_file():
        rules = config.RULES_FILE.read_text(encoding="utf-8").strip()
    else:
        rules = DEFAULT_RULES

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tool_lines = [
        f"- {name}: {td.description}" for name, td in sorted(_base.all_tools().items())
    ]
    tools_block = "\n".join(tool_lines)

    introspect_hint = (
        "Tu disposes d'un tool introspect (list_tools, read_routine, "
        "explain_self, …) pour examiner tes propres tools, routines, "
        "scrapers et données. Utilise-le quand on te pose une question sur "
        "tes capacités ou ta configuration."
    )

    return (
        f"{rules}\n\n"
        f"Date et heure courantes : {now}\n\n"
        f"Tools disponibles :\n{tools_block}\n\n"
        f"{introspect_hint}"
    )


def chunk_message(text: str) -> list[str]:
    """Découpe un message > 1990 caractères pour Discord."""
    if not text:
        return ["(réponse vide)"]
    chunks = []
    while text:
        chunks.append(text[:MAX_DISCORD_LEN])
        text = text[MAX_DISCORD_LEN:]
    return chunks


class AutoBot(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        from commands import register_all

        register_all(self.tree)
        await self.tree.sync()
        log.info("commands_synced")

    async def on_ready(self) -> None:
        log.info("bot_ready", user=str(self.user), channel=config.DISCORD_CHANNEL_ID)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.channel.id != config.DISCORD_CHANNEL_ID:
            return

        log.info("message_received", author=str(message.author))
        try:
            async with message.channel.typing():
                reply = await self.handle_message(message.content)
        except Exception as exc:  # noqa: BLE001
            log.error("message_failed", error=str(exc))
            reply = f"Erreur lors du traitement : {exc}"

        for chunk in chunk_message(reply):
            await message.channel.send(chunk)

    async def handle_message(self, content: str) -> str:
        messages = [{"role": "system", "content": build_system_prompt()}]
        messages.extend(context_messages())
        messages.append({"role": "user", "content": content})

        reply = await run_conversation(LLMClient(), messages)
        append_exchange(content, reply)
        return reply


def main() -> None:
    setup_logging()
    config.ensure_dirs()
    if not config.DISCORD_BOT_TOKEN:
        log.error("missing_token", hint="DISCORD_BOT_TOKEN absent du .env")
        sys.exit(1)
    AutoBot().run(config.DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
