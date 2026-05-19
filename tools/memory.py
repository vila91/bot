"""Core tool : mémoire conversationnelle.

Fenêtre glissante (current.json) + archives Markdown par date.
À chaque message : les entrées hors fenêtre sont archivées dans
memory/YYYY-MM-DD.md (date du message), puis le reste est injecté
en contexte LLM.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import config

from ._base import tool, validate_name

_CURRENT = config.MEMORY_DIR / "current.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> list[dict[str, Any]]:
    if not _CURRENT.is_file():
        return []
    try:
        return json.loads(_CURRENT.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(entries: list[dict[str, Any]]) -> None:
    config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _CURRENT.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _archive(entries: list[dict[str, Any]]) -> None:
    """Ajoute des entrées aux archives MD, groupées par date du message."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        day = e.get("ts", _iso(_now()))[:10]
        by_day.setdefault(day, []).append(e)
    config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    for day, items in by_day.items():
        path = config.MEMORY_DIR / f"{day}.md"
        with path.open("a", encoding="utf-8") as fh:
            for e in items:
                fh.write(f"**[{e.get('ts', '')}] {e.get('role', '?')}**\n\n{e.get('content', '')}\n\n")


def _window_cutoff() -> datetime:
    return _now() - timedelta(hours=config.MEMORY_WINDOW_HOURS)


def load_window() -> list[dict[str, Any]]:
    """Archive les entrées expirées et retourne la fenêtre courante."""
    entries = _load()
    cutoff = _window_cutoff()
    fresh, stale = [], []
    for e in entries:
        try:
            ts = datetime.strptime(e.get("ts", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            fresh.append(e)
            continue
        (fresh if ts >= cutoff else stale).append(e)
    if stale:
        _archive(stale)
        _save(fresh)
    return fresh


def append_exchange(user_msg: str, assistant_msg: str) -> None:
    """Ajoute un échange user/assistant à la fenêtre mémoire."""
    entries = _load()
    ts = _iso(_now())
    entries.append({"ts": ts, "role": "user", "content": user_msg})
    entries.append({"ts": ts, "role": "assistant", "content": assistant_msg})
    _save(entries)


def context_messages() -> list[dict[str, str]]:
    """Retourne la fenêtre mémoire au format messages LLM."""
    return [
        {"role": e["role"], "content": e["content"]}
        for e in load_window()
        if e.get("role") in ("user", "assistant")
    ]


@tool(
    "get_context",
    "Retourne la fenêtre mémoire conversationnelle courante.",
    {"type": "object", "properties": {}},
)
def get_context() -> dict[str, Any]:
    entries = load_window()
    return {"window_hours": config.MEMORY_WINDOW_HOURS, "count": len(entries), "entries": entries}


@tool(
    "reset_memory",
    "Archive l'intégralité de la fenêtre mémoire puis la vide.",
    {"type": "object", "properties": {}},
)
def reset_memory() -> dict[str, Any]:
    entries = _load()
    if entries:
        _archive(entries)
    _save([])
    return {"archived": len(entries), "status": "mémoire réinitialisée"}


@tool(
    "recall_day",
    "Charge le contenu d'une archive mémoire d'un jour passé (YYYY-MM-DD).",
    {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "Date au format YYYY-MM-DD"},
        },
        "required": ["date"],
    },
)
def recall_day(date: str) -> dict[str, Any]:
    validate_name(date)
    path = config.MEMORY_DIR / f"{date}.md"
    if not path.is_file():
        return {"date": date, "found": False, "content": ""}
    return {"date": date, "found": True, "content": path.read_text(encoding="utf-8")}


def forget_before(before: str) -> int:
    """Supprime les archives antérieures à une date. Retourne le nombre supprimé."""
    validate_name(before)
    removed = 0
    if not config.MEMORY_DIR.is_dir():
        return 0
    for path in config.MEMORY_DIR.glob("*.md"):
        if path.stem < before:
            path.unlink()
            removed += 1
    return removed
