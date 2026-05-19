"""Chargement des tools déclaratifs Markdown (DATA_DIR/tools_md/).

Un .md décrit un tool : frontmatter YAML (name, description, parameters,
source, logic, output) + corps documentaire. Le framework le traduit en
JSON schema + fonction d'exécution. Les .md ne contiennent JAMAIS de code
exécutable : la `logic` est interprétée, jamais évaluée.
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog
import yaml

import config

from ._base import ToolDefinition, register, unregister_by_source, validate_name

log = structlog.get_logger()


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
            url = source.get("url", "")
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=kwargs)
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
