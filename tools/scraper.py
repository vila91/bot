"""Core tool : scraping ciblé + génération dynamique de tools scraper.

Chaque .md de DATA_DIR/scrapers/ décrit un site cible. Le framework en
génère un tool LLM dédié. `scrape_site` permet aussi d'invoquer un
scraper par son nom.
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog
import yaml
from bs4 import BeautifulSoup

import config

from ._base import ToolDefinition, register, tool, unregister_by_source, validate_name

log = structlog.get_logger()

_USER_AGENT = "AutoBot/1.0 (+https://github.com/autobot)"


def _parse_descriptor(path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    fm: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        _, _, rest = text.partition("---")
        raw_fm, _, body = rest.partition("---")
        fm = yaml.safe_load(raw_fm) or {}
    return fm, body.strip()


async def _fetch(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=30.0, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def _run_scraper(name: str, query: str | None = None) -> dict[str, Any]:
    validate_name(name)
    path = config.SCRAPERS_DIR / f"{name}.md"
    if not path.is_file():
        return {"error": f"Scraper introuvable: {name}"}

    fm, body = _parse_descriptor(path)
    base_url = fm.get("base_url", "")
    selectors = fm.get("selectors") or {}

    url_template = selectors.get("url_template") or fm.get("url_template")
    if url_template:
        url = url_template.format(base_url=base_url, query=query or "")
    elif query:
        sep = "&" if "?" in base_url else "?"
        url = f"{base_url}{sep}q={query}"
    else:
        url = base_url

    try:
        html = await _fetch(url)
    except httpx.HTTPError as exc:
        return {"error": f"Échec du fetch: {exc}"}

    soup = BeautifulSoup(html, "html.parser")

    item_sel = selectors.get("item")
    if item_sel:
        fields = selectors.get("fields") or {}
        results = []
        for node in soup.select(item_sel):
            row: dict[str, Any] = {}
            for fname, fsel in fields.items():
                el = node.select_one(fsel)
                row[fname] = el.get_text(strip=True) if el else None
            link = node.select_one("a[href]")
            if link:
                row["link"] = link.get("href")
            results.append(row)
        return {"scraper": name, "url": url, "count": len(results), "results": results}

    # Pas de sélecteurs structurés : on retourne le texte pour le LLM.
    text = soup.get_text(separator="\n", strip=True)
    return {
        "scraper": name,
        "url": url,
        "extraction_method": body,
        "text": text[:8000],
    }


def _make_scraper_func(name: str):
    async def _func(query: str | None = None, **_: Any) -> dict[str, Any]:
        return await _run_scraper(name, query)

    return _func


def load_scraper_tools() -> int:
    """Recharge les tools scraper depuis DATA_DIR/scrapers/. Retourne le compte."""
    unregister_by_source("scraper")
    if not config.SCRAPERS_DIR.is_dir():
        return 0
    count = 0
    for path in sorted(config.SCRAPERS_DIR.glob("*.md")):
        try:
            fm, body = _parse_descriptor(path)
            name = fm.get("name") or path.stem
            validate_name(name)
            params = {"type": "object", "properties": {}, "required": []}
            for p in fm.get("parameters", []) or []:
                params["properties"][p["name"]] = {
                    "type": p.get("type", "string"),
                    "description": p.get("description", ""),
                }
                if p.get("required"):
                    params["required"].append(p["name"])
            register(
                ToolDefinition(
                    name=name,
                    description=fm.get("description", f"Scraper {name}"),
                    parameters=params,
                    func=_make_scraper_func(name),
                    source="scraper",
                    raw=path.read_text(encoding="utf-8"),
                )
            )
            count += 1
        except Exception as exc:  # noqa: BLE001 — un scraper cassé ne doit pas tout bloquer
            log.warning("scraper_load_failed", file=path.name, error=str(exc))
    return count


@tool(
    "scrape_site",
    "Scrape un site configuré selon son descripteur .md.",
    {
        "type": "object",
        "properties": {
            "scraper_name": {"type": "string"},
            "query": {"type": "string", "description": "Terme de recherche (optionnel)"},
        },
        "required": ["scraper_name"],
    },
)
async def scrape_site(scraper_name: str, query: str | None = None) -> dict[str, Any]:
    return await _run_scraper(scraper_name, query)


@tool(
    "list_scrapers",
    "Liste les scrapers configurés dans DATA_DIR/scrapers/.",
    {"type": "object", "properties": {}},
)
def list_scrapers() -> dict[str, Any]:
    scrapers = []
    if config.SCRAPERS_DIR.is_dir():
        for path in sorted(config.SCRAPERS_DIR.glob("*.md")):
            fm, _ = _parse_descriptor(path)
            scrapers.append(
                {
                    "name": fm.get("name") or path.stem,
                    "base_url": fm.get("base_url", ""),
                    "description": fm.get("description", ""),
                }
            )
    return {"scrapers": scrapers}
