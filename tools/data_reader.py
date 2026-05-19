"""Core tool : lecture des données (CSV et fichiers texte) de DATA_DIR/data/."""
from __future__ import annotations

import csv
from typing import Any

import config

from ._base import sanitize_cell, tool, validate_name


def _read_rows(filename: str) -> list[dict[str, str]]:
    validate_name(filename)
    path = config.DATA_FILES_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {filename}")
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@tool(
    "read_csv",
    "Lit un fichier CSV de DATA_DIR/data/ et retourne ses lignes. "
    "Un filtre optionnel sélectionne les lignes par valeurs de colonnes.",
    {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Nom du fichier CSV"},
            "filters": {
                "type": "object",
                "description": "Couples colonne:valeur pour filtrer les lignes",
            },
        },
        "required": ["filename"],
    },
)
def read_csv(filename: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = _read_rows(filename)
    if filters:
        rows = [
            r
            for r in rows
            if all(str(r.get(k, "")) == str(v) for k, v in filters.items())
        ]
    rows = [{k: sanitize_cell(v) for k, v in r.items()} for r in rows]
    return {"filename": filename, "count": len(rows), "rows": rows}


@tool(
    "list_data_files",
    "Liste les fichiers disponibles dans DATA_DIR/data/.",
    {"type": "object", "properties": {}},
)
def list_data_files() -> dict[str, Any]:
    if not config.DATA_FILES_DIR.is_dir():
        return {"files": []}
    files = sorted(p.name for p in config.DATA_FILES_DIR.iterdir() if p.is_file())
    return {"files": files}


@tool(
    "read_file",
    "Lit un fichier texte ou Markdown de DATA_DIR/data/.",
    {
        "type": "object",
        "properties": {
            "filename": {"type": "string", "description": "Nom du fichier"},
        },
        "required": ["filename"],
    },
)
def read_file(filename: str) -> dict[str, Any]:
    validate_name(filename)
    path = config.DATA_FILES_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Fichier introuvable: {filename}")
    return {"filename": filename, "content": path.read_text(encoding="utf-8")}
