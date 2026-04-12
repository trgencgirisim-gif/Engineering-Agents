"""report/json_builder.py — Structured JSON sibling export for engineering analyses.

Phase 3.2: Generate a machine-readable findings.json alongside the DOCX report.
The JSON contains all parameters, conflicts, assumptions, risks, and the final
report text in a structured, versioned schema.

Usage:
    from report.json_builder import generate_json_report
    json_bytes = generate_json_report(brief, final_report, domains, ...)
"""

import json
import datetime
from typing import List, Dict, Optional, Any


# Schema version — bump when structure changes
_SCHEMA_VERSION = "1.0"


def generate_json_report(
    brief: str,
    final_report: str,
    domains: List[str],
    round_scores: List[Dict] = None,
    agent_log: List[Dict] = None,
    total_cost: float = 0.0,
    kur: float = 44.0,
    mode: int = 4,
    max_rounds: int = 3,
    blackboard_dict: Optional[Dict] = None,
) -> bytes:
    """
    Produce a JSON-serialised analysis report.

    Args:
        brief: Original problem statement.
        final_report: Full final report text from the final_rapor agent.
        domains: List of domain names (strings) involved.
        round_scores: Per-round quality scores from round_history.
        agent_log: Per-agent cost/token/score log entries.
        total_cost: Total USD cost.
        kur: USD→TRY exchange rate.
        mode: Analysis mode (1-4).
        max_rounds: Maximum rounds configured.
        blackboard_dict: Optional Blackboard.to_dict() output for structured data.

    Returns:
        UTF-8 encoded JSON bytes.
    """
    round_scores = round_scores or []
    agent_log = agent_log or []
    blackboard_dict = blackboard_dict or {}

    doc_id = f"EAI-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-M{mode}"
    mode_labels = {1: "Single Agent", 2: "Dual Agent",
                   3: "Semi-Automatic", 4: "Full Automatic"}

    # ── Extract quality score ────────────────────────────────
    final_score = 0
    if round_scores:
        scores = [r.get("score", 0) for r in round_scores if r.get("score")]
        if scores:
            final_score = scores[-1]

    # ── Build parameters section ─────────────────────────────
    parameters = []
    for name, entries in blackboard_dict.get("parameters", {}).items():
        if not entries:
            continue
        latest = entries[-1]
        val = latest.get("value", "")
        raw = val.get("raw", str(val)) if isinstance(val, dict) else str(val)
        parameters.append({
            "name": name,
            "value": raw,
            "source_agent": latest.get("source_agent", ""),
            "round": latest.get("round_num", 0),
            "confidence": latest.get("confidence", "MEDIUM"),
            "model_used": latest.get("model_used", ""),
            "prompt_version": latest.get("prompt_version", ""),
        })

    # ── Build conflicts section ──────────────────────────────
    conflicts = []
    for c in blackboard_dict.get("conflicts", []):
        conflicts.append({
            "id": c.get("id"),
            "agent_a": c.get("agent_a", ""),
            "claim_a": c.get("claim_a", ""),
            "agent_b": c.get("agent_b", ""),
            "claim_b": c.get("claim_b", ""),
            "domain": c.get("domain", ""),
            "round": c.get("round", 0),
            "status": c.get("status", "open"),
            "resolution": c.get("resolution", ""),
            "impact": c.get("impact", "MEDIUM"),
        })

    # ── Build assumptions section ────────────────────────────
    assumptions = []
    for a in blackboard_dict.get("assumptions", []):
        assumptions.append({
            "id": a.get("id"),
            "agent": a.get("agent", ""),
            "text": a.get("text", ""),
            "impact": a.get("impact", "MEDIUM"),
            "explicit": a.get("explicit", True),
            "validated": a.get("validated", False),
            "round": a.get("round", 0),
        })

    # ── Build risk register section ──────────────────────────
    risks = []
    for r in blackboard_dict.get("risk_register", []):
        risks.append({
            "component": r.get("component", ""),
            "failure_mode": r.get("failure_mode", ""),
            "severity": r.get("severity", 0),
            "occurrence": r.get("occurrence", 0),
            "detection": r.get("detection", 0),
            "rpn": r.get("rpn", 0),
            "agent": r.get("agent", ""),
            "round": r.get("round", 0),
        })

    # ── Build agent summary ──────────────────────────────────
    agents_summary = []
    for entry in agent_log:
        agents_summary.append({
            "agent": entry.get("ajan", entry.get("agent", "")),
            "cost_usd": round(entry.get("maliyet", entry.get("cost", 0.0)), 6),
            "input_tokens": entry.get("giris", entry.get("input_tokens", 0)),
            "output_tokens": entry.get("cikis", entry.get("output_tokens", 0)),
            "score": entry.get("puan", entry.get("score")),
            "model": entry.get("model", ""),
        })

    # ── Assemble document ────────────────────────────────────
    doc: Dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "document_id": doc_id,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "meta": {
            "brief": brief,
            "mode": mode,
            "mode_label": mode_labels.get(mode, "Custom"),
            "max_rounds": max_rounds,
            "domains": domains,
            "domain_count": len(domains),
            "final_quality_score": final_score,
            "total_cost_usd": round(total_cost, 6),
            "total_cost_try": round(total_cost * kur, 2),
            "usd_try_rate": kur,
            "rounds_completed": len(round_scores),
            "agents_run": len(agent_log),
        },
        "quality_progression": [
            {"round": r.get("round", i + 1), "score": r.get("score", 0)}
            for i, r in enumerate(round_scores)
        ],
        "findings": {
            "parameters": parameters,
            "conflicts": conflicts,
            "assumptions": assumptions,
            "risks": risks,
            "open_questions": [
                {"question": q.get("question", ""), "priority": q.get("priority", ""),
                 "source": q.get("source", "")}
                for q in blackboard_dict.get("open_questions", [])
            ],
        },
        "agents": agents_summary,
        "final_report_text": final_report,
    }

    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")
