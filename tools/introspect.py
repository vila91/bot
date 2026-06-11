"""Core tool : auto-analyse du bot (lecture seule).

Le bot examine sa propre config — tools, routines, scrapers, règles,
données — pour raisonner sur ses capacités. Aucun de ces tools ne
modifie de fichier. Les clés API sont masquées.
"""
from __future__ import annotations

import csv
from typing import Any

import yaml

import config

from . import _base
from ._base import tool, validate_name


@tool(
    "list_tools",
    "Liste les tools enregistrés. `type` filtre : core, md, scraper, all.",
    {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["core", "md", "scraper", "all"],
                "description": "Filtre par source de tool",
            }
        },
    },
)
def list_tools(type: str = "all") -> dict[str, Any]:  # noqa: A002 — nom imposé par le schéma
    out = []
    for name, td in sorted(_base.all_tools().items()):
        if type not in ("all", None) and td.source != type:
            continue
        out.append({"name": name, "description": td.description, "source": td.source})
    return {"count": len(out), "tools": out}


@tool(
    "read_tool_definition",
    "Retourne la définition complète d'un tool : schéma JSON pour un core "
    "tool, fichier .md brut pour un tool MD ou un scraper.",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
def read_tool_definition(name: str) -> dict[str, Any]:
    td = _base.get(name)
    if not td:
        return {"error": f"Tool inconnu: {name}"}
    result: dict[str, Any] = {"name": name, "source": td.source, "description": td.description}
    if td.raw is not None:
        result["raw"] = td.raw
    else:
        result["schema"] = td.schema()
        result["docstring"] = (td.func.__doc__ or "").strip()
    return result


@tool(
    "list_routines_full",
    "Liste toutes les routines avec leur contenu complet (frontmatter + prompt).",
    {"type": "object", "properties": {}},
)
def list_routines_full() -> dict[str, Any]:
    routines = []
    if config.ROUTINES_DIR.is_dir():
        for path in sorted(config.ROUTINES_DIR.glob("*.md")):
            routines.append({"name": path.stem, "content": path.read_text(encoding="utf-8")})
    return {"count": len(routines), "routines": routines}


@tool(
    "read_routine",
    "Retourne le .md brut d'une routine (frontmatter YAML + system_prompt).",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
)
def read_routine(name: str) -> dict[str, Any]:
    validate_name(name)
    path = config.ROUTINES_DIR / f"{name}.md"
    if not path.is_file():
        return {"error": f"Routine introuvable: {name}"}
    return {"name": name, "content": path.read_text(encoding="utf-8")}


@tool(
    "read_rules",
    "Retourne le contenu de RULES.md (règles appliquées au chat et aux routines).",
    {"type": "object", "properties": {}},
)
def read_rules() -> dict[str, Any]:
    if not config.RULES_FILE.is_file():
        return {"rules": "", "exists": False}
    return {"rules": config.RULES_FILE.read_text(encoding="utf-8"), "exists": True}


@tool(
    "list_data_schemas",
    "Pour chaque CSV de data/, retourne en-têtes, nombre de lignes et un "
    "échantillon des 5 premières lignes.",
    {"type": "object", "properties": {}},
)
def list_data_schemas() -> dict[str, Any]:
    schemas = []
    if config.DATA_FILES_DIR.is_dir():
        for path in sorted(config.DATA_FILES_DIR.glob("*.csv")):
            with path.open(newline="", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
            headers = rows[0] if rows else []
            data = rows[1:]
            schemas.append(
                {
                    "file": path.name,
                    "headers": headers,
                    "row_count": len(data),
                    "sample": data[:5],
                }
            )
    return {"count": len(schemas), "schemas": schemas}


def _config_summary() -> dict[str, Any]:
    tools = _base.all_tools()
    by_source: dict[str, int] = {}
    for td in tools.values():
        by_source[td.source] = by_source.get(td.source, 0) + 1
    routines = len(list(config.ROUTINES_DIR.glob("*.md"))) if config.ROUTINES_DIR.is_dir() else 0
    return {
        "instance": config.INSTANCE,
        "llm_provider": config.LLM_PROVIDER,
        "llm_model": config.LLM_MODEL,
        "llm_api_key": "***" if config.LLM_API_KEY else "(non configurée)",
        "memory_window_hours": config.MEMORY_WINDOW_HOURS,
        "max_tool_rounds": config.MAX_TOOL_ROUNDS,
        "tools": {"total": len(tools), **by_source},
        "routines": routines,
        "scrapers": by_source.get("scraper", 0),
        "data_dir": str(config.DATA_DIR),
    }


@tool(
    "get_config_summary",
    "Retourne la config active (LLM, mémoire, compteurs). Clés API masquées.",
    {"type": "object", "properties": {}},
)
def get_config_summary() -> dict[str, Any]:
    return _config_summary()


@tool(
    "explain_self",
    "Meta-tool : reçoit une question et un dump complet de la config du "
    "bot, et génère une réponse cohérente sur ses propres capacités.",
    {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    },
)
async def explain_self(question: str) -> dict[str, Any]:
    from engine import LLMClient

    dump = {
        "config": _config_summary(),
        "rules": read_rules()["rules"],
        "tools": list_tools("all")["tools"],
        "routines": [r["name"] for r in list_routines_full()["routines"]],
        "data_schemas": [s["file"] for s in list_data_schemas()["schemas"]],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un bot AutoBot. Voici un dump de ta configuration. "
                "Réponds à la question de l'utilisateur sur tes propres "
                "capacités, de façon claire et concise.\n\n"
                f"{yaml.safe_dump(dump, allow_unicode=True)}"
            ),
        },
        {"role": "user", "content": question},
    ]
    try:
        resp = await LLMClient().complete(messages)
        answer = resp["choices"][0]["message"].get("content", "")
    except Exception as exc:  # noqa: BLE001
        return {"question": question, "error": str(exc), "dump": dump}
    return {"question": question, "answer": answer}
