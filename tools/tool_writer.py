"""Création / suppression de tools MD depuis le chat ou un slash command.

Les tools MD sont **toujours** écrits dans `DATA_DIR/tools_md/` (jamais dans
le repo). Ce module factorise la validation et l'écriture pour
`/create_tool` et le core tool `create_md_tool`. Les secrets sont stockés
dans le `.env` de l'instance ; un secret ne peut être écrit que s'il est
déclaré dans le frontmatter d'au moins un tool MD (anti-écrasement).
"""
from __future__ import annotations

import os
from typing import Any

import structlog
import yaml

import config

from ._base import tool, validate_name
from .md_loader import (
    ALLOWED_SOURCE_TYPES,
    FORBIDDEN_FRONTMATTER_KEYS,
    collect_declared_secrets,
)

log = structlog.get_logger()

# Clés .env qu'on n'accepte JAMAIS d'écraser via store_secret, même si un
# tool MD les déclare. C'est la dernière ligne de défense contre une
# injection de prompt qui ferait croire au LLM qu'il doit modifier la
# config système.
PROTECTED_ENV_KEYS = frozenset(
    {
        "DISCORD_BOT_TOKEN",
        "DISCORD_CHANNEL_ID",
        "LLM_API_KEY",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "DATA_DIR",
        "TAVILY_KEY",
    }
)


def _tool_path(name: str) -> "os.PathLike[str]":
    validate_name(name)
    return config.TOOLS_MD_DIR / f"{name}.md"


def write_md_tool(
    name: str,
    description: str,
    parameters: list[dict[str, Any]] | None,
    source: dict[str, Any],
    logic: str = "",
    body: str = "",
    secrets: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Écrit un tool MD dans DATA_DIR/tools_md/ après validation.

    Renvoie {path, missing_secrets} en cas de succès. Lève ValueError sinon.
    """
    validate_name(name)
    if not description or not isinstance(description, str):
        raise ValueError("description requise")
    if not isinstance(source, dict) or "type" not in source:
        raise ValueError("source.type requis")
    stype = source["type"]
    if stype not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"source.type inconnu: {stype} (autorisés: {sorted(ALLOWED_SOURCE_TYPES)})")

    frontmatter: dict[str, Any] = {
        "name": name,
        "description": description,
        "parameters": parameters or [],
        "source": source,
    }
    if logic:
        frontmatter["logic"] = logic
    if secrets:
        frontmatter["secrets"] = [str(s).strip() for s in secrets if str(s).strip()]

    forbidden = FORBIDDEN_FRONTMATTER_KEYS & set(frontmatter.keys())
    if forbidden:
        raise ValueError(f"clés interdites: {sorted(forbidden)}")

    config.TOOLS_MD_DIR.mkdir(parents=True, exist_ok=True)
    path = _tool_path(name)
    if path.exists() and not overwrite:
        raise ValueError(f"Tool {name!r} existe déjà — passe overwrite=true pour écraser")

    content = "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n"
    if body:
        content += "\n" + body.strip() + "\n"
    path.write_text(content, encoding="utf-8")

    from . import reload_dynamic

    reload_dynamic()

    missing = [s for s in (secrets or []) if not os.environ.get(s)]
    log.info("md_tool_written", name=name, missing_secrets=missing)
    return {"path": str(path), "missing_secrets": missing}


# === Core tools exposés au LLM ===


@tool(
    "create_md_tool",
    "Crée un nouveau tool déclaratif (.md) dans DATA_DIR/tools_md/. "
    "Si le tool nécessite des clés API, déclare-les dans `secrets` ; le "
    "résultat indique celles qui manquent — demande-les ensuite à "
    "l'utilisateur et appelle store_secret pour les stocker.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nom du tool (snake_case, sans extension)"},
            "description": {"type": "string"},
            "parameters": {
                "type": "array",
                "description": "Liste de {name, type, description, required?, items?}",
                "items": {"type": "object"},
            },
            "source": {
                "type": "object",
                "description": "{type: csv|api|scraper|computed|file, ...}. Pour api : url, headers?, params?. Pour csv : file. Pour scraper : name.",
            },
            "logic": {"type": "string", "description": "Étapes en langage naturel (jamais de code)"},
            "body": {"type": "string", "description": "Doc libre (contexte, hypothèses)"},
            "secrets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Noms d'env vars (ex: ['POLYGON_API_KEY']) à utiliser dans source via ${VAR}",
            },
            "overwrite": {"type": "boolean"},
        },
        "required": ["name", "description", "source"],
    },
)
def create_md_tool(
    name: str,
    description: str,
    source: dict[str, Any],
    parameters: list[dict[str, Any]] | None = None,
    logic: str = "",
    body: str = "",
    secrets: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    return write_md_tool(
        name=name,
        description=description,
        parameters=parameters,
        source=source,
        logic=logic,
        body=body,
        secrets=secrets,
        overwrite=overwrite,
    )


@tool(
    "delete_md_tool",
    "Supprime un tool MD de DATA_DIR/tools_md/.",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
def delete_md_tool(name: str) -> dict[str, Any]:
    path = _tool_path(name)
    if not path.exists():
        return {"error": f"Tool inconnu: {name}"}
    path.unlink()
    from . import reload_dynamic

    reload_dynamic()
    return {"ok": True, "deleted": name}


@tool(
    "list_required_secrets",
    "Liste tous les secrets déclarés par les tools MD avec leur état "
    "(set / unset). Permet au bot de savoir lesquels manquent.",
    {"type": "object", "properties": {}},
)
def list_required_secrets() -> dict[str, Any]:
    declared = collect_declared_secrets()
    all_keys = sorted({k for keys in declared.values() for k in keys})
    return {
        "by_tool": declared,
        "status": {k: ("set" if os.environ.get(k) else "unset") for k in all_keys},
    }


@tool(
    "store_secret",
    "Stocke un secret dans le .env de l'instance. Le nom doit être déclaré "
    "dans le `secrets:` d'au moins un tool MD ; les clés système sont "
    "protégées. À utiliser après avoir demandé la valeur à l'utilisateur.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nom de la variable d'environnement"},
            "value": {"type": "string", "description": "Valeur du secret"},
        },
        "required": ["name", "value"],
    },
)
def store_secret(name: str, value: str) -> dict[str, Any]:
    name = (name or "").strip()
    if not name or not name.replace("_", "").isalnum() or not name[0].isalpha():
        return {"error": f"nom invalide: {name!r}"}
    if name.upper() != name:
        return {"error": "le nom doit être en MAJUSCULES (convention env var)"}
    if name in PROTECTED_ENV_KEYS:
        return {"error": f"{name} est une clé système protégée — modifier via /set_llm ou .env directement"}
    declared = {k for keys in collect_declared_secrets().values() for k in keys}
    if name not in declared:
        return {
            "error": f"{name} n'est déclaré dans aucun tool MD. Crée d'abord le tool avec ce secret dans `secrets:`.",
        }
    if not value:
        return {"error": "valeur vide"}
    config.update_env({name: value})
    log.info("secret_stored", name=name)
    return {"ok": True, "stored": name}
