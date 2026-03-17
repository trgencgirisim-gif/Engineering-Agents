"""
scripts/test_loader.py
Verifies that the SKILL.md migration is correct.
Checks key presence, prompt content, model, and max_tokens for every agent.

Usage:
    python scripts/test_loader.py
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from agents._loader import load_all_agents

# Load original values from backup or current agents_config.py
try:
    import importlib.util
    backup = pathlib.Path(__file__).parent.parent / "config" / "_agents_config_backup.py"
    if backup.exists():
        spec = importlib.util.spec_from_file_location("_backup", backup)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        OLD_AGENTS  = mod.AGENTS
        OLD_SUPPORT = mod.DESTEK_AJANLARI
    else:
        from config.agents_config import AGENTS as OLD_AGENTS, DESTEK_AJANLARI as OLD_SUPPORT
except Exception:
    from config.agents_config import AGENTS as OLD_AGENTS, DESTEK_AJANLARI as OLD_SUPPORT

new_agents, new_support = load_all_agents()

errors: list[str] = []

# 1. Key presence
for key in OLD_AGENTS:
    if key not in new_agents:
        errors.append(f"MISSING domain agent: {key}")
for key in OLD_SUPPORT:
    if key not in new_support:
        errors.append(f"MISSING support agent: {key}")

# 2. System prompt content (whitespace-normalized)
def _normalize(text: str) -> str:
    return " ".join(text.split())

for key in OLD_AGENTS:
    if key in new_agents:
        old_p = _normalize(OLD_AGENTS[key]["sistem_promptu"])
        new_p = _normalize(new_agents[key]["sistem_promptu"])
        if old_p != new_p:
            errors.append(f"PROMPT MISMATCH: {key}")

for key in OLD_SUPPORT:
    if key in new_support:
        old_p = _normalize(OLD_SUPPORT[key]["sistem_promptu"])
        new_p = _normalize(new_support[key]["sistem_promptu"])
        if old_p != new_p:
            errors.append(f"PROMPT MISMATCH: {key}")

# 3. Model and max_tokens
for key in OLD_AGENTS:
    if key in new_agents:
        if OLD_AGENTS[key]["model"] != new_agents[key]["model"]:
            errors.append(f"MODEL MISMATCH: {key} "
                          f"(expected {OLD_AGENTS[key]['model']}, "
                          f"got {new_agents[key]['model']})")
        if OLD_AGENTS[key].get("max_tokens") != new_agents[key].get("max_tokens"):
            errors.append(f"MAX_TOKENS MISMATCH: {key}")

for key in OLD_SUPPORT:
    if key in new_support:
        if OLD_SUPPORT[key]["model"] != new_support[key]["model"]:
            errors.append(f"MODEL MISMATCH (support): {key} "
                          f"(expected {OLD_SUPPORT[key]['model']}, "
                          f"got {new_support[key]['model']})")
        if OLD_SUPPORT[key].get("max_tokens") != new_support[key].get("max_tokens"):
            errors.append(f"MAX_TOKENS MISMATCH (support): {key}")

# 4. Verify tools.yaml stubs exist for domain agents
domain_base = pathlib.Path(__file__).parent.parent / "agents" / "domain"
missing_tools = 0
for key in new_agents:
    domain = key.rsplit("_", 1)[0]
    tools_path = domain_base / domain / key / "tools.yaml"
    if not tools_path.exists():
        missing_tools += 1

# Report
if errors:
    print("FAILURES:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("All tests passed.")
    print(f"  Domain agents : {len(new_agents)}/{len(OLD_AGENTS)}")
    print(f"  Support agents: {len(new_support)}/{len(OLD_SUPPORT)}")
    print("  System prompts: match")
    print("  Model/tokens  : match")
    if missing_tools:
        print(f"  tools.yaml    : {missing_tools} missing (non-critical)")
    else:
        print(f"  tools.yaml    : all present")
