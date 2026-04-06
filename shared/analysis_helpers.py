"""shared/analysis_helpers.py — Extracted helpers used by all 3 entry points.

Functions previously duplicated in main.py, app.py, and orchestrator.py.
"""

import re
from parser import parse_agent_output
from config.agents_config import DESTEK_AJANLARI


def build_context_history(brief_msg: str, tum_ciktilar: str) -> list:
    """Convert accumulated outputs to conversation history format for cache HIT."""
    return [
        {"role": "user", "content": f"Domain analysis request:\n{brief_msg}"},
        {"role": "assistant", "content": tum_ciktilar},
    ]


def update_blackboard(bb, agent_key: str, output: str, round_num: int):
    """Parse agent output and write structured data to blackboard."""
    if not output or output.startswith("ERROR") or output.startswith("STOPPED"):
        return

    try:
        parsed = parse_agent_output(output, agent_key, client=None)
    except Exception:
        return

    if not parsed:
        return

    # Domain agents -> parameters, flags, assumptions
    if agent_key.endswith("_a") or agent_key.endswith("_b"):
        if agent_key not in DESTEK_AJANLARI:
            for p in parsed.get("parameters", []):
                bb.write("parameters", p, agent_key, round_num)
            for f in parsed.get("cross_domain_flags", []):
                bb.write("cross_domain_flags", f, agent_key, round_num)
            for a in parsed.get("assumptions", []):
                bb.write("assumptions", a, agent_key, round_num)
    elif agent_key == "capraz_dogrulama":
        for e in parsed.get("errors", []):
            bb.write("conflicts", e, agent_key, round_num)
    elif agent_key == "varsayim_belirsizlik":
        for a in parsed.get("assumptions", []):
            bb.write("assumptions", a, agent_key, round_num)
    elif agent_key == "gozlemci":
        for d in parsed.get("directives", []):
            bb.write("observer_directives", d, agent_key, round_num)
        score = parsed.get("score", 0)
        bb.write("round_history", {"round": round_num, "score": score}, agent_key, round_num)
    elif agent_key == "risk_guvenilirlik":
        for r in parsed.get("risks", []):
            bb.write("risk_register", r, agent_key, round_num)
    elif agent_key == "celisiki_cozum":
        resolutions = parsed.get("resolutions", [])
        if resolutions:
            bb.resolve_conflicts([
                {"conflict_id": i + 1, "resolution": r.get("resolution", "")}
                for i, r in enumerate(resolutions)
            ])


def extract_quality_score(text: str) -> int:
    """Extract quality score (N/100) from observer output. Default: 70."""
    match = re.search(r'(\d{1,3})\s*/\s*100', text)
    if match:
        score = int(match.group(1))
        if 0 <= score <= 100:
            return score
    return 70
