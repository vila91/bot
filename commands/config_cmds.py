"""Slash commands de configuration : /set_llm, /set_scraper, /set_memory_window,
/set_rules, /status."""
from __future__ import annotations

import discord
from discord import app_commands

import config
from tools import reload_dynamic
from tools._base import validate_name
from tools.introspect import get_config_summary
from tools.tool_writer import store_secret


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="set_llm", description="Change le LLM (provider, modèle, clé API)")
    @app_commands.describe(
        provider="deepseek | openai | anthropic | local",
        model="Nom du modèle",
        api_key="Clé API (optionnel)",
    )
    async def set_llm(
        interaction: discord.Interaction,
        provider: str,
        model: str,
        api_key: str | None = None,
    ) -> None:
        updates = {"LLM_PROVIDER": provider, "LLM_MODEL": model}
        if api_key:
            updates["LLM_API_KEY"] = api_key
        config.update_env(updates)
        config.LLM_PROVIDER = provider
        config.LLM_MODEL = model
        if api_key:
            config.LLM_API_KEY = api_key
        await interaction.response.send_message(
            f"LLM configuré : `{provider}` / `{model}`", ephemeral=True
        )

    @tree.command(name="set_scraper", description="Configure un site cible pour le scraping")
    @app_commands.describe(name="Nom du scraper", url="URL de base du site")
    async def set_scraper(interaction: discord.Interaction, name: str, url: str) -> None:
        try:
            validate_name(name)
        except ValueError as exc:
            await interaction.response.send_message(f"Nom invalide : {exc}", ephemeral=True)
            return
        config.SCRAPERS_DIR.mkdir(parents=True, exist_ok=True)
        path = config.SCRAPERS_DIR / f"{name}.md"
        path.write_text(
            f"---\n"
            f"name: {name}\n"
            f"base_url: {url}\n"
            f'description: "Scraper {name}"\n'
            f"parameters:\n"
            f"  - name: query\n"
            f"    type: string\n"
            f'    description: "Terme de recherche"\n'
            f"    required: false\n"
            f"# selectors:\n"
            f"#   url_template: \"{{base_url}}/search?q={{query}}\"\n"
            f"#   item: .result\n"
            f"#   fields:\n"
            f"#     title: .result__title\n"
            f"---\n\n"
            f"## Méthode d'extraction\n\n"
            f"Décrire ici comment extraire les données de {url}.\n",
            encoding="utf-8",
        )
        reload_dynamic()
        await interaction.response.send_message(
            f"Scraper `{name}` créé. Éditez `{path}` pour ajouter les sélecteurs.",
            ephemeral=True,
        )

    @tree.command(name="set_memory_window", description="Durée de la fenêtre mémoire")
    @app_commands.describe(hours="Durée en heures")
    async def set_memory_window(interaction: discord.Interaction, hours: int) -> None:
        if hours < 1:
            await interaction.response.send_message("La durée doit être ≥ 1h.", ephemeral=True)
            return
        config.update_env({"MEMORY_WINDOW_HOURS": str(hours)})
        config.MEMORY_WINDOW_HOURS = hours
        await interaction.response.send_message(
            f"Fenêtre mémoire : {hours}h", ephemeral=True
        )

    @tree.command(name="set_rules", description="Modifie les règles générales du bot (RULES.md)")
    @app_commands.describe(text="Nouveau contenu de RULES.md")
    async def set_rules(interaction: discord.Interaction, text: str) -> None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.RULES_FILE.write_text(text.strip() + "\n", encoding="utf-8")
        await interaction.response.send_message("RULES.md mis à jour.", ephemeral=True)

    @tree.command(
        name="set_secret",
        description="Stocke un secret (clé API) déclaré par un tool MD dans le .env",
    )
    @app_commands.describe(name="Nom de l'env var (MAJUSCULES)", value="Valeur du secret")
    async def set_secret(interaction: discord.Interaction, name: str, value: str) -> None:
        result = store_secret(name, value)
        msg = result.get("error") or f"Secret `{name}` stocké."
        await interaction.response.send_message(msg, ephemeral=True)

    @tree.command(name="status", description="Affiche la configuration courante")
    async def status(interaction: discord.Interaction) -> None:
        summary = get_config_summary()
        lines = [f"**AutoBot — instance `{summary['instance']}`**"]
        lines.append(f"LLM : `{summary['llm_provider']}` / `{summary['llm_model']}`")
        lines.append(f"Mémoire : {summary['memory_window_hours']}h")
        lines.append(
            f"Tools : {summary['tools']['total']} "
            f"(core {summary['tools'].get('core', 0)}, "
            f"md {summary['tools'].get('md', 0)}, "
            f"scraper {summary['tools'].get('scraper', 0)})"
        )
        lines.append(f"Routines : {summary['routines']}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
