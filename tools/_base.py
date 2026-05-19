"""Classe de base des tools + registre + décorateur @tool.

Tous les tools (core Python, MD déclaratifs, scrapers) sont enregistrés
ici dans un registre unique partagé par le LLM engine et l'introspection.
"""
from __future__ import annotations

import re
from typing import Any, Callable

# === Registre global ===
_REGISTRY: dict[str, "ToolDefinition"] = {}

# Caractères dangereux en tête de cellule CSV (injection de formule).
_CSV_INJECTION_PREFIX = ("=", "+", "-", "@", "\t", "\r")

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_name(name: str) -> str:
    """Vérifie qu'un nom de fichier/routine est sûr (anti path-traversal)."""
    if not name or not isinstance(name, str):
        raise ValueError("Nom vide ou invalide")
    if name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError(f"Nom invalide (path-traversal): {name!r}")
    if not _NAME_RE.match(name):
        raise ValueError(f"Nom invalide (caractères interdits): {name!r}")
    return name


def sanitize_cell(value: Any) -> Any:
    """Préfixe une cellule CSV par une apostrophe si elle peut être une formule."""
    if isinstance(value, str) and value.startswith(_CSV_INJECTION_PREFIX):
        return "'" + value
    return value


class ToolDefinition:
    """Un tool exposé au LLM via function calling."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None,
        func: Callable[..., Any],
        source: str = "core",
        raw: str | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}
        self.func = func
        self.source = source  # core | md | scraper
        self.raw = raw  # contenu brut (.md) pour les tools déclaratifs

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def tool(name: str, description: str, parameters: dict[str, Any] | None = None):
    """Décorateur d'enregistrement d'un core tool."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        register(ToolDefinition(name, description, parameters, func, source="core"))
        return func

    return decorator


def register(td: ToolDefinition) -> None:
    _REGISTRY[td.name] = td


def unregister_by_source(source: str) -> None:
    """Retire tous les tools d'une source (utilisé au rechargement à chaud)."""
    for name in [n for n, t in _REGISTRY.items() if t.source == source]:
        del _REGISTRY[name]


def get(name: str) -> ToolDefinition | None:
    return _REGISTRY.get(name)


def all_tools() -> dict[str, ToolDefinition]:
    return dict(_REGISTRY)
