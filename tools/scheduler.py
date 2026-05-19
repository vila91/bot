"""Core tool : gestion des routines de veille (fichiers .md + crontab).

Invariants critiques (voir CLAUDE.md) :
- PYTHON_BIN unique : toute invocation Python passe par config.PYTHON_BIN.
- Matching par marker : `<ROUTINES_DIR>/<name>.md ` (absolu + espace final).
- Crontab isolée par instance : on ne touche qu'aux lignes contenant
  le ROUTINES_DIR de l'instance courante.
- _validate_name en première instruction de chaque fonction publique.
"""
from __future__ import annotations

import subprocess
from typing import Any

import structlog
import yaml

import config

log = structlog.get_logger()

from ._base import tool, validate_name

ALLOWED_SOURCE_TYPES = {"tavily", "csv", "scraper", "file", "tool"}

_RUNNER = config.REPO_DIR / "runner.py"
_CRONTAB_RECORD = config.ROUTINES_DIR / "crontab"
_CRONTAB_BAK = config.ROUTINES_DIR / "crontab.bak"


def _validate_name(name: str) -> str:
    return validate_name(name)


def _routine_path(name: str):
    return config.ROUTINES_DIR / f"{name}.md"


def _routine_marker(name: str) -> str:
    """Sous-chaîne identifiant les lignes crontab d'une routine de CETTE instance."""
    return f"{_routine_path(name)} "


def _instance_marker() -> str:
    """Sous-chaîne identifiant toutes les lignes crontab de cette instance."""
    return f"{config.ROUTINES_DIR}/"


def _log_path(name: str) -> str:
    return f"/tmp/autobot-{config.INSTANCE}_{name}.log"


def _cron_line(name: str, cron_expr: str) -> str:
    return (
        f"{cron_expr} {config.PYTHON_BIN} {_RUNNER} "
        f"{_routine_path(name)} >> {_log_path(name)} 2>&1"
    )


def _read_crontab() -> list[str]:
    try:
        res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except FileNotFoundError:
        return []
    if res.returncode != 0:
        return []
    return [ln for ln in res.stdout.splitlines()]


def _write_crontab(lines: list[str]) -> None:
    current = _read_crontab()
    config.ROUTINES_DIR.mkdir(parents=True, exist_ok=True)
    _CRONTAB_BAK.write_text("\n".join(current) + "\n", encoding="utf-8")
    content = "\n".join(lines).rstrip("\n") + "\n"
    # Trace lisible des lignes de cette instance (toujours écrite).
    own = [ln for ln in lines if _instance_marker() in ln]
    _CRONTAB_RECORD.write_text("\n".join(own) + "\n", encoding="utf-8")
    try:
        subprocess.run(["crontab", "-"], input=content, text=True, check=True)
    except FileNotFoundError:
        log.warning(
            "crontab_unavailable",
            hint="commande crontab absente — planification enregistrée dans routines/crontab uniquement",
        )


def _set_cron(name: str, cron_expr: str | None) -> None:
    """Installe (ou retire si cron_expr est None) l'entrée crontab d'une routine."""
    marker = _routine_marker(name)
    lines = [ln for ln in _read_crontab() if marker not in ln]
    if cron_expr:
        lines.append(_cron_line(name, cron_expr))
    _write_crontab(lines)


def _cron_of(name: str) -> str | None:
    marker = _routine_marker(name)
    for ln in _read_crontab():
        if marker in ln:
            return " ".join(ln.split()[:5])
    return None


@tool(
    "list_routines",
    "Liste les routines avec leur statut (planifié / non planifié).",
    {"type": "object", "properties": {}},
)
def list_routines() -> dict[str, Any]:
    routines = []
    if config.ROUTINES_DIR.is_dir():
        for path in sorted(config.ROUTINES_DIR.glob("*.md")):
            name = path.stem
            cron = _cron_of(name)
            routines.append(
                {"name": name, "scheduled": cron is not None, "cron": cron}
            )
    return {"routines": routines}


@tool(
    "create_routine",
    "Crée une routine .md (frontmatter + system_prompt) et la planifie "
    "si un cron est fourni.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "sources": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Sources de données (type + params)",
            },
            "system_prompt": {"type": "string"},
            "cron_expr": {"type": "string", "description": "Expression cron (optionnel)"},
        },
        "required": ["name", "system_prompt"],
    },
)
def create_routine(
    name: str,
    system_prompt: str,
    sources: list[dict[str, Any]] | None = None,
    cron_expr: str | None = None,
) -> dict[str, Any]:
    _validate_name(name)
    sources = sources or []
    for src in sources:
        st = src.get("type")
        if st not in ALLOWED_SOURCE_TYPES:
            raise ValueError(f"Type de source invalide: {st!r}")

    path = _routine_path(name)
    if path.exists():
        raise FileExistsError(f"La routine {name} existe déjà")

    frontmatter: dict[str, Any] = {"name": name, "sources": sources}
    if cron_expr:
        frontmatter["cron"] = cron_expr
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    config.ROUTINES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}---\n\n{system_prompt}\n", encoding="utf-8")

    if cron_expr:
        _set_cron(name, cron_expr)
    return {"name": name, "scheduled": bool(cron_expr), "cron": cron_expr}


@tool(
    "delete_routine",
    "Supprime une routine : son fichier .md et son entrée crontab.",
    {
        "type": "object",
        "properties": {"routine_name": {"type": "string"}},
        "required": ["routine_name"],
    },
)
def delete_routine(routine_name: str) -> dict[str, Any]:
    _validate_name(routine_name)
    path = _routine_path(routine_name)
    _set_cron(routine_name, None)
    existed = path.exists()
    if existed:
        path.unlink()
    return {"name": routine_name, "deleted": existed}


@tool(
    "schedule",
    "Planifie une routine existante avec une expression cron.",
    {
        "type": "object",
        "properties": {
            "routine_name": {"type": "string"},
            "cron_expr": {"type": "string"},
        },
        "required": ["routine_name", "cron_expr"],
    },
)
def schedule(routine_name: str, cron_expr: str) -> dict[str, Any]:
    _validate_name(routine_name)
    if not _routine_path(routine_name).exists():
        raise FileNotFoundError(f"Routine introuvable: {routine_name}")
    _set_cron(routine_name, cron_expr)
    return {"name": routine_name, "cron": cron_expr, "scheduled": True}


@tool(
    "reschedule",
    "Modifie la planification cron d'une routine.",
    {
        "type": "object",
        "properties": {
            "routine_name": {"type": "string"},
            "cron_expr": {"type": "string"},
        },
        "required": ["routine_name", "cron_expr"],
    },
)
def reschedule(routine_name: str, cron_expr: str) -> dict[str, Any]:
    _validate_name(routine_name)
    if not _routine_path(routine_name).exists():
        raise FileNotFoundError(f"Routine introuvable: {routine_name}")
    _set_cron(routine_name, cron_expr)
    return {"name": routine_name, "cron": cron_expr, "scheduled": True}


@tool(
    "unschedule",
    "Retire une routine du cron sans supprimer son fichier .md.",
    {
        "type": "object",
        "properties": {"routine_name": {"type": "string"}},
        "required": ["routine_name"],
    },
)
def unschedule(routine_name: str) -> dict[str, Any]:
    _validate_name(routine_name)
    _set_cron(routine_name, None)
    return {"name": routine_name, "scheduled": False}


@tool(
    "run_now",
    "Lance immédiatement une routine en subprocess détaché.",
    {
        "type": "object",
        "properties": {"routine_name": {"type": "string"}},
        "required": ["routine_name"],
    },
)
def run_now(routine_name: str) -> dict[str, Any]:
    _validate_name(routine_name)
    path = _routine_path(routine_name)
    if not path.exists():
        raise FileNotFoundError(f"Routine introuvable: {routine_name}")
    log = open(_log_path(routine_name), "a", encoding="utf-8")
    subprocess.Popen(
        [str(config.PYTHON_BIN), str(_RUNNER), str(path)],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {"name": routine_name, "status": "lancée", "log": _log_path(routine_name)}
