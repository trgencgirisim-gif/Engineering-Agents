"""
agents/_loader.py
Loads agent configurations from SKILL.md files.
Replaces config/agents_config.py — returns identical dict format.
All code and comments in English.
"""
from __future__ import annotations

import pathlib
import yaml
from typing import Dict, Any, Tuple

BASE = pathlib.Path(__file__).parent


def _parse_skill_md(path: pathlib.Path) -> Dict[str, Any]:
    """
    Parse a SKILL.md file.
    Returns metadata dict with 'sistem_promptu' key added
    (keeps Turkish key name for backward compatibility with core.py).
    """
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid SKILL.md format (missing front matter): {path}")

    meta = yaml.safe_load(parts[1])
    body = parts[2].strip()

    # Strip the "## System Prompt" heading if present
    if body.startswith("## System Prompt"):
        body = body[len("## System Prompt"):].strip()

    # Keep 'sistem_promptu' key for backward compatibility with core.py
    meta["sistem_promptu"] = body

    # Map English field names to internal keys used by the rest of the codebase
    if "name" in meta and "isim" not in meta:
        meta["isim"] = meta["name"]

    # Remove thinking_budget if zero (API does not want it)
    if not meta.get("thinking_budget"):
        meta.pop("thinking_budget", None)

    if "tools" not in meta:
        meta["tools"] = []

    return meta


def _load_tools_yaml(skill_dir: pathlib.Path) -> dict:
    """Load tools.yaml if present, return empty dict otherwise."""
    tools_path = skill_dir / "tools.yaml"
    if tools_path.exists():
        with open(tools_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_all_agents() -> Tuple[dict, dict]:
    """
    Load all SKILL.md files and return (AGENTS, DESTEK_AJANLARI).
    Return format is fully compatible with the original agents_config.py.
    """
    agents: dict = {}
    support: dict = {}

    # Domain agents
    domain_base = BASE / "domain"
    if domain_base.exists():
        for skill_file in sorted(domain_base.rglob("SKILL.md")):
            agent_key = skill_file.parent.name  # e.g. "yanma_a"
            try:
                agent_data = _parse_skill_md(skill_file)
                tools_data = _load_tools_yaml(skill_file.parent)
                agent_data["_tools_config"] = tools_data
                agents[agent_key] = agent_data
            except Exception as exc:
                print(f"WARNING: Could not load SKILL.md: {skill_file} — {exc}")

    # Support agents
    support_base = BASE / "support"
    if support_base.exists():
        for skill_file in sorted(support_base.rglob("SKILL.md")):
            agent_key = skill_file.parent.name  # e.g. "gozlemci"
            try:
                agent_data = _parse_skill_md(skill_file)
                support[agent_key] = agent_data
            except Exception as exc:
                print(f"WARNING: Could not load SKILL.md: {skill_file} — {exc}")

    return agents, support


# Module-level cache — loaded once per application lifetime
_AGENTS_CACHE: dict | None = None
_SUPPORT_CACHE: dict | None = None


def get_agents() -> Tuple[dict, dict]:
    """Return cached agents (loaded once at startup)."""
    global _AGENTS_CACHE, _SUPPORT_CACHE
    if _AGENTS_CACHE is None:
        _AGENTS_CACHE, _SUPPORT_CACHE = load_all_agents()
    return _AGENTS_CACHE, _SUPPORT_CACHE


def reload_agents() -> Tuple[dict, dict]:
    """Clear cache and reload from disk (for hot reload / development)."""
    global _AGENTS_CACHE, _SUPPORT_CACHE
    _AGENTS_CACHE = None
    _SUPPORT_CACHE = None
    return get_agents()
