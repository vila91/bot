"""Slash commands mémoire : /reset, /recall, /forget."""
from __future__ import annotations

import discord
from discord import app_commands

from tools.memory import forget_before, recall_day, reset_memory


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="reset", description="Archive la mémoire courante et la vide")
    async def reset(interaction: discord.Interaction) -> None:
        result = reset_memory()
        await interaction.response.send_message(
            f"Mémoire réinitialisée ({result['archived']} entrées archivées).",
            ephemeral=True,
        )

    @tree.command(name="recall", description="Affiche l'archive mémoire d'un jour passé")
    @app_commands.describe(date="Date au format YYYY-MM-DD")
    async def recall(interaction: discord.Interaction, date: str) -> None:
        try:
            result = recall_day(date)
        except ValueError as exc:
            await interaction.response.send_message(f"Date invalide : {exc}", ephemeral=True)
            return
        if not result.get("found"):
            await interaction.response.send_message(
                f"Aucune archive pour {date}.", ephemeral=True
            )
            return
        content = result["content"]
        await interaction.response.send_message(content[:1990], ephemeral=True)

    @tree.command(name="forget", description="Supprime les archives antérieures à une date")
    @app_commands.describe(before="Date au format YYYY-MM-DD")
    async def forget(interaction: discord.Interaction, before: str) -> None:
        try:
            removed = forget_before(before)
        except ValueError as exc:
            await interaction.response.send_message(f"Date invalide : {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"{removed} archive(s) supprimée(s) avant {before}.", ephemeral=True
        )
