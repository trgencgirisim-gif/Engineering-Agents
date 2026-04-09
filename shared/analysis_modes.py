"""shared/analysis_modes.py — Shared analysis mode implementations.

Eliminates near-identical run_tekli/run_cift/run_full_loop logic
from main.py, app.py, and orchestrator.py. Each entry point provides
an AnalysisIO adapter to handle I/O differences.
"""

from dataclasses import dataclass, field
from typing import Callable, Any, Optional

from shared.analysis_helpers import (
    build_context_history,
    update_blackboard,
    extract_quality_score,
)
from shared.rag_context import (
    build_domain_message,
    build_final_report_context,
)


@dataclass
class AnalysisIO:
    """I/O adapter — each entry point provides its own implementations."""
    run_agent: Callable       # (key, msg, gecmis=None, cache_context=None) -> str
    run_parallel: Callable    # (tasks, max_workers=6) -> [str]
    on_event: Callable        # (event_type: str, data: dict) -> None
    rag_store: Any            # RAGStore instance or None
    checkpoint: Callable      # () -> None

    # For adaptive model (full_loop only)
    get_domain_model: Optional[Callable] = None   # () -> str
    set_domain_model: Optional[Callable] = None   # (model: str) -> None


def run_single_analysis(brief, domains, bb, io):
    """Mode 1: Single-agent analysis.

    Args:
        brief: Enhanced brief text
        domains: [(key, name), ...] active domains
        bb: Blackboard instance
        io: AnalysisIO adapter

    Returns:
        (final_report, round_scores) tuple
    """
    alan_isimleri = [name for _, name in domains]

    # -- GRUP A: Domain agents parallel --
    gorev_a = []
    for key, name in domains:
        _msg = build_domain_message(brief, key, name, io.rag_store) if io.rag_store else brief
        gorev_a.append((f"{key}_a", _msg, None, None))

    io.on_event("grup_a", {"count": len(domains)})
    sonuc_a = io.run_parallel(gorev_a, max_workers=6)

    parts = [f"{name.upper()} EXPERT:\n{sonuc_a[i]}" for i, (_, name) in enumerate(domains)]
    tum_ciktilar = "\n\n".join(parts)

    for i, (key, _) in enumerate(domains):
        update_blackboard(bb, f"{key}_a", sonuc_a[i], 1)

    shared_ctx = build_context_history(brief, tum_ciktilar)

    # -- GRUP B: Cross-validation + Questions parallel --
    io.on_event("grup_b", {})
    _bb_cv = bb.get_context_for("capraz_dogrulama", 1)
    b_sonuc = io.run_parallel([
        ("capraz_dogrulama",
         f"Check all numerical values for physical and mathematical consistency.\n\n{_bb_cv}",
         shared_ctx, None),
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions needing further analysis.",
         shared_ctx, None),
    ], max_workers=2)
    capraz, sorular = b_sonuc
    update_blackboard(bb, "capraz_dogrulama", capraz, 1)

    # -- Observer --
    io.on_event("observer", {})
    _bb_obs = bb.get_context_for("gozlemci", 1)
    gozlemci = io.run_agent("gozlemci",
        f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\n"
        f"CROSS-VAL: {capraz}\n{_bb_obs}\n"
        f"Evaluate. KALİTE PUANI: XX/100.",
        gecmis=shared_ctx)
    update_blackboard(bb, "gozlemci", gozlemci, 1)

    # -- Final report --
    io.on_event("final_report", {})
    _bb_summary = bb.to_summary()
    _rag_final = build_final_report_context(brief, io.rag_store) if io.rag_store else ""
    _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
    final = io.run_agent("final_rapor",
        f"Single-agent analysis. Domains: {', '.join(alan_isimleri)}\n"
        f"PROBLEM: {brief}\n"
        f"OBSERVER: {gozlemci}\n"
        f"QUESTIONS: {sorular}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary}{_rag_final_note}\n\n"
        f"Domain agent technical findings are in the conversation history above.\n"
        f"Write a professional engineering report: lead with each domain's technical "
        f"findings (preserve all numbers and calculations), then observer evaluation, "
        f"then recommendations (max 25% of report). "
        f"If knowledge base context is provided, reference relevant past findings "
        f"and explicitly address any previously unresolved questions. "
        f"Always write in English.",
        gecmis=shared_ctx)

    puan = extract_quality_score(gozlemci)
    return final, [{"tur": 1, "puan": puan}]


def run_dual_analysis(brief, domains, bb, io):
    """Mode 2: Dual-agent analysis (A=theoretical, B=practical).

    Args:
        brief: Enhanced brief text
        domains: [(key, name), ...] active domains
        bb: Blackboard instance
        io: AnalysisIO adapter

    Returns:
        (final_report, round_scores) tuple
    """
    alan_isimleri = [name for _, name in domains]

    # -- GRUP A: Domain A+B agents parallel --
    gorev_a = []
    for key, name in domains:
        _msg = build_domain_message(brief, key, name, io.rag_store) if io.rag_store else brief
        gorev_a.append((f"{key}_a", _msg, None, None))
        gorev_a.append((f"{key}_b", _msg, None, None))

    io.on_event("grup_a", {"count": len(domains) * 2})
    sonuc_a = io.run_parallel(gorev_a, max_workers=6)

    tum_ciktilar_parts = []
    for i, (key, name) in enumerate(domains):
        cevap_a = sonuc_a[i * 2]
        cevap_b = sonuc_a[i * 2 + 1]
        tum_ciktilar_parts.append(
            f"{name.upper()} EXPERT A:\n{cevap_a}\n\n"
            f"{name.upper()} EXPERT B:\n{cevap_b}"
        )
        update_blackboard(bb, f"{key}_a", cevap_a, 1)
        update_blackboard(bb, f"{key}_b", cevap_b, 1)

    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)
    shared_ctx = build_context_history(brief, tum_ciktilar)

    # -- GRUP B: Validation parallel --
    io.on_event("grup_b", {})
    _bb_cv = bb.get_context_for("capraz_dogrulama", 1)
    _bb_as = bb.get_context_for("varsayim_belirsizlik", 1)
    b_sonuc = io.run_parallel([
        ("capraz_dogrulama",
         f"Check all numerical values for physical and mathematical consistency.\n\n{_bb_cv}",
         shared_ctx, None),
        ("varsayim_belirsizlik",
         f"Identify all hidden and unstated assumptions across expert outputs.\n\n{_bb_as}",
         shared_ctx, None),
    ], max_workers=2)
    capraz, varsayim = b_sonuc
    update_blackboard(bb, "capraz_dogrulama", capraz, 1)
    update_blackboard(bb, "varsayim_belirsizlik", varsayim, 1)

    # -- Observer --
    io.on_event("observer", {})
    _bb_obs = bb.get_context_for("gozlemci", 1)
    gozlemci = io.run_agent("gozlemci",
        f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\n"
        f"CROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\n\n"
        f"{_bb_obs}\n"
        f"Evaluate all outputs. KALİTE PUANI: XX/100. Identify key A vs B conflicts.",
        gecmis=shared_ctx)
    update_blackboard(bb, "gozlemci", gozlemci, 1)

    # -- GRUP C: Conflict resolution + Questions + Alternatives --
    io.on_event("grup_c", {})
    _bb_conf = bb.get_context_for("celisiki_cozum", 1)
    c_sonuc = io.run_parallel([
        ("celisiki_cozum",
         f"OBSERVER:\n{gozlemci}\n\n{_bb_conf}\nResolve A vs B expert conflicts.",
         shared_ctx, None),
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions.",
         shared_ctx, None),
        ("alternatif_senaryo",
         f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.",
         shared_ctx, None),
    ], max_workers=3)
    celiski, sorular, alternatif = c_sonuc
    update_blackboard(bb, "celisiki_cozum", celiski, 1)

    # -- Final report --
    io.on_event("final_report", {})
    _bb_summary = bb.to_summary()
    _rag_final = build_final_report_context(brief, io.rag_store) if io.rag_store else ""
    _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
    final = io.run_agent("final_rapor",
        f"Dual-agent analysis (A=theoretical, B=practical). Domains: {', '.join(alan_isimleri)}\n"
        f"PROBLEM: {brief}\n"
        f"OBSERVER: {gozlemci}\n"
        f"CONFLICTS RESOLVED: {celiski}\n"
        f"QUESTIONS: {sorular}\n"
        f"ALTERNATIVES: {alternatif}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary}{_rag_final_note}\n\n"
        f"Domain agent technical findings are in the conversation history above.\n"
        f"Write a professional engineering report: lead with each domain's technical "
        f"findings (preserve all numbers), then conflicts, then recommendations "
        f"(max 25% of report). Reference past knowledge base findings where relevant. "
        f"Always write in English.",
        gecmis=shared_ctx)

    puan = extract_quality_score(gozlemci)
    return final, [{"tur": 1, "puan": puan}]
