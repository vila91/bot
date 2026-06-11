"""Configuration centrale d'AutoBot.

Résout DATA_DIR, charge le .env de l'instance et expose toutes les
variables dérivées. Aucun chemin n'est hardcodé : tout dépend de
l'emplacement du repo et de la variable d'environnement DATA_DIR.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parent


def _resolve_data_dir() -> Path:
    env = os.getenv("DATA_DIR")
    if env and env != "__DATA_DIR__":
        return Path(env).expanduser().resolve()
    return (Path.home() / ".autobot").resolve()


DATA_DIR = _resolve_data_dir()

ENV_FILE = DATA_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)

# Le .env peut redéfinir DATA_DIR — on re-résout après chargement.
_data_dir_from_env = os.getenv("DATA_DIR")
if _data_dir_from_env and _data_dir_from_env != "__DATA_DIR__":
    DATA_DIR = Path(_data_dir_from_env).expanduser().resolve()
    ENV_FILE = DATA_DIR / ".env"

# === Chemins dérivés ===
ROUTINES_DIR = DATA_DIR / "routines"
MEMORY_DIR = DATA_DIR / "memory"
TOOLS_MD_DIR = REPO_DIR / "tools_md"
SCRAPERS_DIR = DATA_DIR / "scrapers"
DATA_FILES_DIR = DATA_DIR / "data"
RULES_FILE = DATA_DIR / "RULES.md"
PYTHON_BIN = REPO_DIR / "venv" / "bin" / "python3"


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


# === LLM ===
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
MAX_TOOL_ROUNDS = _int("MAX_TOOL_ROUNDS", 15)

# === Recherche web ===
TAVILY_KEY = os.getenv("TAVILY_KEY", "")

# === Discord ===
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = _int("DISCORD_CHANNEL_ID", 0)

# === Mémoire ===
MEMORY_WINDOW_HOURS = _int("MEMORY_WINDOW_HOURS", 24)

# === Divers ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
INSTANCE = os.getenv("INSTANCE", "autobot")


def update_env(updates: dict[str, str]) -> None:
    """Met à jour le fichier .env de l'instance (clés ajoutées ou remplacées).

    Modifie aussi os.environ pour que la valeur soit visible immédiatement.
    """
    lines: list[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}")
                continue
        out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")

    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


def ensure_dirs() -> None:
    for d in (DATA_DIR, ROUTINES_DIR, MEMORY_DIR, SCRAPERS_DIR, DATA_FILES_DIR):
        d.mkdir(parents=True, exist_ok=True)
