"""
config/agents_config.py
Backward-compatibility shim.
All agent definitions have been migrated to agents/domain/ and agents/support/.
This file exists solely to preserve import compatibility.
Do not add agent definitions here -- edit the corresponding SKILL.md instead.
"""
from agents._loader import get_agents as _get_agents

AGENTS, DESTEK_AJANLARI = _get_agents()

__all__ = ["AGENTS", "DESTEK_AJANLARI"]
