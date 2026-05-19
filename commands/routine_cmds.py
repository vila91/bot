"""Slash commands routines : /routines, /run, /pause, /resume,
/create_routine, /delete_routine."""
from __future__ import annotations

import discord
import yaml
from discord import app_commands

from tools import scheduler


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="routines", description="Liste les routines et leur statut")
    async def routines(interaction: discord.Interaction) -> None:
        items = scheduler.list_routines()["routines"]
        if not items:
            await interaction.response.send_message("Aucune routine.", ephemeral=True)
            return
        lines = []
        for r in items:
            status = f"planifiée (`{r['cron']}`)" if r["scheduled"] else "en pause"
            lines.append(f"- **{r['name']}** — {status}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @tree.command(name="run", description="Exécute une routine immédiatement")
    @app_commands.describe(name="Nom de la routine")
    async def run(interaction: discord.Interaction, name: str) -> None:
        try:
            result = scheduler.run_now(name)
        except (ValueError, FileNotFoundError) as exc:
            await interaction.response.send_message(f"Erreur : {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Routine `{name}` lancée. Log : `{result['log']}`", ephemeral=True
        )

    @tree.command(name="pause", description="Retire une routine du cron sans la supprimer")
    @app_commands.describe(name="Nom de la routine")
    async def pause(interaction: discord.Interaction, name: str) -> None:
        try:
            scheduler.unschedule(name)
        except ValueError as exc:
            await interaction.response.send_message(f"Erreur : {exc}", ephemeral=True)
            return
        await interaction.response.send_message(f"Routine `{name}` mise en pause.", ephemeral=True)

    @tree.command(name="resume", description="Replanifie une routine")
    @app_commands.describe(name="Nom de la routine", cron="Expression cron (optionnel)")
    async def resume(
        interaction: discord.Interaction, name: str, cron: str | None = None
    ) -> None:
        try:
            cron_expr = cron
            if not cron_expr:
                path = scheduler._routine_path(name)
                if not path.exists():
                    raise FileNotFoundError(f"Routine introuvable: {name}")
                text = path.read_text(encoding="utf-8")
                fm = {}
                if text.startswith("---"):
                    _, _, rest = text.partition("---")
                    raw_fm, _, _ = rest.partition("---")
                    fm = yaml.safe_load(raw_fm) or {}
                cron_expr = fm.get("cron")
            if not cron_expr:
                await interaction.response.send_message(
                    "Aucun cron fourni et aucun cron dans le frontmatter.", ephemeral=True
                )
                return
            scheduler.schedule(name, cron_expr)
        except (ValueError, FileNotFoundError) as exc:
            await interaction.response.send_message(f"Erreur : {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Routine `{name}` replanifiée (`{cron_expr}`).", ephemeral=True
        )

    @tree.command(name="create_routine", description="Crée une routine vide à compléter")
    @app_commands.describe(name="Nom de la nouvelle routine")
    async def create_routine(interaction: discord.Interaction, name: str) -> None:
        try:
            scheduler.create_routine(
                name=name,
                system_prompt=(
                    "Décris ici le rôle de la routine. Édite ce fichier pour "
                    "ajouter des sources et une expression cron."
                ),
                sources=[],
            )
        except (ValueError, FileExistsError) as exc:
            await interaction.response.send_message(f"Erreur : {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Routine `{name}` créée. Édite le fichier .md puis `/resume {name} <cron>`.",
            ephemeral=True,
        )

    @tree.command(name="delete_routine", description="Supprime une routine et son cron")
    @app_commands.describe(name="Nom de la routine")
    async def delete_routine(interaction: discord.Interaction, name: str) -> None:
        try:
            result = scheduler.delete_routine(name)
        except ValueError as exc:
            await interaction.response.send_message(f"Erreur : {exc}", ephemeral=True)
            return
        msg = "supprimée" if result["deleted"] else "introuvable"
        await interaction.response.send_message(f"Routine `{name}` {msg}.", ephemeral=True)
