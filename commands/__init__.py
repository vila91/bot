"""Slash commands Discord — enregistrement centralisé."""
from __future__ import annotations

from discord import app_commands

from . import config_cmds, memory_cmds, routine_cmds, tool_cmds


def register_all(tree: app_commands.CommandTree) -> None:
    config_cmds.register(tree)
    memory_cmds.register(tree)
    routine_cmds.register(tree)
    tool_cmds.register(tree)


__all__ = ["register_all"]
