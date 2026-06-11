"""Slash commands tools : /tools, /tool_info, /reload_tools, /create_tool, /delete_tool."""
from __future__ import annotations

import json

import discord
from discord import app_commands

from tools import reload_dynamic
from tools.introspect import list_tools, read_tool_definition
from tools.tool_writer import write_md_tool, delete_md_tool


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

    @tree.command(
        name="create_tool",
        description="Crée un tool MD dans DATA_DIR/tools_md/",
    )
    @app_commands.describe(
        name="Nom du tool (snake_case)",
        description="Ce que fait le tool",
        source_type="csv | api | scraper | computed | file",
        source_target="Selon le type : nom de fichier (csv/file), URL (api), nom de scraper",
        parameters_json="Liste JSON de paramètres [{name,type,description,required?}] (optionnel)",
        logic="Étapes en langage naturel (optionnel)",
        secrets="Liste d'env vars séparées par des virgules (ex: POLYGON_API_KEY,X_KEY)",
    )
    async def create_tool(
        interaction: discord.Interaction,
        name: str,
        description: str,
        source_type: str,
        source_target: str,
        parameters_json: str | None = None,
        logic: str | None = None,
        secrets: str | None = None,
    ) -> None:
        try:
            params = json.loads(parameters_json) if parameters_json else []
            source: dict = {"type": source_type}
            if source_type in ("csv", "file"):
                source["file"] = source_target
            elif source_type == "api":
                source["url"] = source_target
            elif source_type == "scraper":
                source["name"] = source_target
            secret_list = (
                [s.strip() for s in secrets.split(",") if s.strip()] if secrets else []
            )
            result = write_md_tool(
                name=name,
                description=description,
                parameters=params,
                source=source,
                logic=logic or "",
                secrets=secret_list,
            )
        except Exception as exc:  # noqa: BLE001
            await interaction.response.send_message(f"Erreur : {exc}", ephemeral=True)
            return
        msg = f"Tool `{name}` créé → `{result['path']}`"
        if result["missing_secrets"]:
            msg += (
                f"\nSecrets manquants : {', '.join(result['missing_secrets'])}\n"
                f"Renseigne-les avec `/set_secret`."
            )
        await interaction.response.send_message(msg, ephemeral=True)

    @tree.command(name="delete_tool", description="Supprime un tool MD")
    @app_commands.describe(name="Nom du tool")
    async def delete_tool_cmd(interaction: discord.Interaction, name: str) -> None:
        result = delete_md_tool(name)
        msg = result.get("error") or f"Tool `{name}` supprimé."
        await interaction.response.send_message(msg, ephemeral=True)
