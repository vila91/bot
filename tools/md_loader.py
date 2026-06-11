"""Chargement des tools déclaratifs Markdown (DATA_DIR/tools_md/).

Un .md décrit un tool : frontmatter YAML (name, description, parameters,
source, logic, output) + corps documentaire. Le framework le traduit en
JSON schema + fonction d'exécution. Les .md ne contiennent JAMAIS de code
exécutable : la `logic` est interprétée, jamais évaluée.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx
import structlog
import yaml

import config

from ._base import ToolDefinition, register, unregister_by_source, validate_name

log = structlog.get_logger()

ALLOWED_SOURCE_TYPES = {"csv", "api", "scraper", "computed", "file"}
FORBIDDEN_FRONTMATTER_KEYS = {"python", "exec", "eval", "code", "import"}

_SECRET_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


def _substitute_secrets(value: Any) -> Any:
    """Remplace ${VAR} par os.environ[VAR] dans une str ou récursivement dans dict/list.

    Si la variable est absente, on garde le placeholder tel quel — le tool
    pourra alors signaler la clé manquante au LLM.
    """
    if isinstance(value, str):
        return _SECRET_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _substitute_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_secrets(v) for v in value]
    return value


def collect_declared_secrets() -> dict[str, list[str]]:
    """Pour chaque tool MD, retourne la liste de secrets déclarés. {tool_name: [SECRETS]}."""
    out: dict[str, list[str]] = {}
    if not config.TOOLS_MD_DIR.is_dir():
        return out
    for path in sorted(config.TOOLS_MD_DIR.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            fm, _ = _parse(path)
            secrets = fm.get("secrets") or []
            if isinstance(secrets, list) and secrets:
                out[fm.get("name") or path.stem] = [str(s) for s in secrets]
        except Exception:  # noqa: BLE001
            continue
    return out


def _parse(path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, _, rest = text.partition("---")
    raw_fm, _, body = rest.partition("---")
    return (yaml.safe_load(raw_fm) or {}), body.strip()


def _json_schema(parameters: list[dict[str, Any]] | None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    for p in parameters or []:
        prop: dict[str, Any] = {
            "type": p.get("type", "string"),
            "description": p.get("description", ""),
        }
        if prop["type"] == "array":
            prop["items"] = {"type": p.get("items", "string")}
        schema["properties"][p["name"]] = prop
        if p.get("required"):
            schema["required"].append(p["name"])
    return schema


def _make_func(fm: dict[str, Any], body: str):
    source = fm.get("source") or {}
    stype = source.get("type", "computed")
    logic = fm.get("logic", "")

    async def _func(**kwargs: Any) -> dict[str, Any]:
        if stype == "csv":
            from .data_reader import read_csv

            filename = source.get("file", "")
            validate_name(filename)
            data = read_csv(filename)
            return {
                "tool": fm.get("name"),
                "logic": logic,
                "context": body,
                "data": data["rows"],
                "args": kwargs,
            }
        if stype == "api":
            url = _substitute_secrets(source.get("url", ""))
            headers = _substitute_secrets(source.get("headers") or {})
            extra_params = _substitute_secrets(source.get("params") or {})
            missing = _SECRET_RE.findall(
                url + " " + " ".join(f"{k}={v}" for k, v in {**headers, **extra_params}.items())
            )
            if missing:
                return {
                    "tool": fm.get("name"),
                    "error": "missing_secrets",
                    "secrets": sorted(set(missing)),
                    "hint": "Demande à l'utilisateur de fournir ces clés puis appelle store_secret.",
                }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params={**extra_params, **kwargs}, headers=headers)
                resp.raise_for_status()
                try:
                    payload = resp.json()
                except ValueError:
                    payload = resp.text
            return {"tool": fm.get("name"), "logic": logic, "data": payload}
        if stype == "scraper":
            from .scraper import scrape_site

            return await scrape_site(source.get("name", ""), kwargs.get("query"))
        # computed : le LLM interprète la logique sur les args fournis.
        return {
            "tool": fm.get("name"),
            "logic": logic,
            "context": body,
            "args": kwargs,
        }

    return _func


def load_md_tools() -> int:
    """Recharge les tools MD depuis DATA_DIR/tools_md/. Retourne le compte."""
    unregister_by_source("md")
    if not config.TOOLS_MD_DIR.is_dir():
        return 0
    count = 0
    for path in sorted(config.TOOLS_MD_DIR.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            fm, body = _parse(path)
            name = fm.get("name") or path.stem
            validate_name(name)
            forbidden = FORBIDDEN_FRONTMATTER_KEYS & set(fm.keys())
            if forbidden:
                raise ValueError(f"clés interdites dans le frontmatter: {sorted(forbidden)}")
            stype = (fm.get("source") or {}).get("type", "computed")
            if stype not in ALLOWED_SOURCE_TYPES:
                raise ValueError(f"source.type inconnu: {stype}")
            register(
                ToolDefinition(
                    name=name,
                    description=fm.get("description", f"Tool MD {name}"),
                    parameters=_json_schema(fm.get("parameters")),
                    func=_make_func(fm, body),
                    source="md",
                    raw=path.read_text(encoding="utf-8"),
                )
            )
            count += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("md_tool_load_failed", file=path.name, error=str(exc))
    return count
