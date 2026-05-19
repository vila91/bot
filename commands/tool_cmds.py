"""Slash commands tools : /tools, /tool_info, /reload_tools."""
from __future__ import annotations

import json

import discord
from discord import app_commands

from tools import reload_dynamic
from tools.introspect import list_tools, read_tool_definition


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="tools", description="Liste tous les tools disponibles")
    async def tools_cmd(interaction: discord.Interaction) -> None:
        items = list_tools("all")["tools"]
        lines = [f"**{len(items)} tools disponibles**"]
        for t in items:
            lines.append(f"- `{t['name']}` ({t['source']}) — {t['description']}")
        text = "\n".join(lines)
        await interaction.response.send_message(text[:1990], ephemeral=True)

    @tree.command(name="tool_info", description="Affiche le schéma d'un tool")
    @app_commands.describe(name="Nom du tool")
    async def tool_info(interaction: discord.Interaction, name: str) -> None:
        info = read_tool_definition(name)
        if "error" in info:
            await interaction.response.send_message(info["error"], ephemeral=True)
            return
        text = json.dumps(info, ensure_ascii=False, indent=2)
        await interaction.response.send_message(f"```json\n{text[:1900]}\n```", ephemeral=True)

    @tree.command(name="reload_tools", description="Recharge les tools MD et scrapers")
    async def reload_tools(interaction: discord.Interaction) -> None:
        result = reload_dynamic()
        await interaction.response.send_message(
            f"Tools rechargés : {result['md']} MD, {result['scrapers']} scrapers.",
            ephemeral=True,
        )
