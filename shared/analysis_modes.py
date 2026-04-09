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
    on_model_promote: Optional[Callable] = None   # (promoted_keys: set) -> restore_fn


@dataclass
class FullLoopHooks:
    """Optional hooks for entry-point-specific features (app.py quality gate, etc.)."""
    quality_gate: Optional[Callable] = None        # (key, output) -> dict
    quality_gate_retry: Optional[Callable] = None   # (key, msg, hist, output) -> str
    on_round_start: Optional[Callable] = None       # (round_num) -> None
    on_round_score: Optional[Callable] = None        # (round_num, score) -> None


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


# ─────────────────────────────────────────────────────────────
# MODE 3/4: Full Loop Analysis
# ─────────────────────────────────────────────────────────────

_CTX_WORD_LIMIT = 8000  # A3: Context compression threshold


def run_full_loop_analysis(brief, domains, bb, io, max_rounds=3, hooks=None):
    """Mode 3/4: Full multi-round analysis with quality loop.

    Args:
        brief: Enhanced brief text
        domains: [(key, name), ...] active domains
        bb: Blackboard instance
        io: AnalysisIO adapter
        max_rounds: Maximum iteration rounds
        hooks: Optional FullLoopHooks for entry-point-specific features

    Returns:
        (final_report, round_scores) tuple
    """
    hooks = hooks or FullLoopHooks()
    alan_isimleri = [name for _, name in domains]
    alan_keyleri = [key for key, _ in domains]

    gecmis = {f"{key}_{ab}": [] for key in alan_keyleri for ab in ("a", "b")}
    tur_ozeti = []
    gozlemci_notu = ""
    gozlemci_cevabi = ""
    shared_ctx = []

    # C1: Adaptive model — enabled if on_model_promote callback provided
    _adaptive_model_enabled = io.on_model_promote is not None
    _promoted_agents = set()

    # C2: Incremental execution — skip agents without directives
    _skip_agents = set()

    # ═══════════════════════════════════════════════════════════
    # ROUND LOOP
    # ═══════════════════════════════════════════════════════════
    for tur in range(1, max_rounds + 1):
        io.on_event("round_start", {"tur": tur})
        if hooks.on_round_start:
            hooks.on_round_start(tur)

        mesaj = brief if tur == 1 else f"{brief}\n\nOBSERVER NOTES FROM ROUND {tur-1}:\n{gozlemci_notu}"
        son_tur = {}

        # C2: Build skip list for round 2+
        if tur > 1:
            _skip_agents.clear()
            _agents_with_directives = set()
            for agent_key, directive in bb.observer_directives.items():
                if isinstance(directive, dict) and directive.get("status") != "addressed":
                    _agents_with_directives.add(agent_key)
                elif isinstance(directive, list):
                    for d in directive:
                        if isinstance(d, dict) and d.get("status") != "addressed":
                            _agents_with_directives.add(agent_key)
            for key in alan_keyleri:
                for ab in ("a", "b"):
                    ak = f"{key}_{ab}"
                    if ak not in _agents_with_directives:
                        _skip_agents.add(ak)

            # C1: Adaptive — low score -> promote directive agents to Opus
            if _adaptive_model_enabled and tur_ozeti:
                last_score = tur_ozeti[-1].get("puan", 70)
                if last_score and last_score < 70:
                    _promoted_agents.update(_agents_with_directives)

        # -- GRUP A: Domain agents parallel --
        gorev_a = []
        _gorev_keys = []
        _skipped = set()
        for key, name in domains:
            for ab in ("a", "b"):
                ak = f"{key}_{ab}"
                if ak in _skip_agents:
                    _skipped.add(ak)
                    continue
                if tur > 1:
                    bb_ctx = bb.get_context_for(ak, tur)
                    _msg = f"{mesaj}\n\n{bb_ctx}" if bb_ctx else mesaj
                else:
                    _msg = build_domain_message(brief, key, name, io.rag_store, base_message=mesaj) if io.rag_store else mesaj
                gorev_a.append((ak, _msg, gecmis[ak], None))
                _gorev_keys.append(ak)

        # C1: Adaptive model promotion
        restore_fn = None
        if _promoted_agents and _adaptive_model_enabled and gorev_a:
            if io.on_model_promote:
                restore_fn = io.on_model_promote(_promoted_agents)

        io.on_event("grup_a", {"count": len(gorev_a), "skipped": len(_skipped)})
        sonuc_a = io.run_parallel(gorev_a, max_workers=6) if gorev_a else []
        _sonuc_map = {k: sonuc_a[i] for i, k in enumerate(_gorev_keys) if i < len(sonuc_a)}

        # C1: Restore original models
        if restore_fn:
            restore_fn()

        # C5: Quality gate (round 1 only, app.py hook)
        if tur == 1 and hooks.quality_gate:
            for ak in _gorev_keys:
                output = _sonuc_map.get(ak, "")
                if output:
                    qg_result = hooks.quality_gate(ak, output)
                    if not qg_result.get("pass", True) and hooks.quality_gate_retry:
                        retry = hooks.quality_gate_retry(ak, mesaj, gecmis[ak], output)
                        if retry and not retry.startswith("ERROR"):
                            _sonuc_map[ak] = retry

        for key, name in domains:
            for ab in ("a", "b"):
                ak = f"{key}_{ab}"
                if ak in _skipped:
                    son_tur[ak] = gecmis[ak][-1]["content"] if gecmis[ak] else ""
                else:
                    son_tur[ak] = _sonuc_map.get(ak, "")
                    gecmis[ak] += [{"role": "user", "content": mesaj},
                                   {"role": "assistant", "content": son_tur[ak]}]

        # Blackboard: parse domain outputs (only non-skipped)
        for key, name in domains:
            for ab in ("a", "b"):
                ak = f"{key}_{ab}"
                if ak not in _skipped:
                    update_blackboard(bb, ak, son_tur[ak], tur)
                    if tur > 1:
                        bb.mark_directive_addressed(ak)

        tum_ciktilar = "\n\n".join(
            f"{n.upper()} EXPERT A:\n{son_tur[f'{k}_a']}\n\n{n.upper()} EXPERT B:\n{son_tur[f'{k}_b']}"
            for k, n in domains
        )

        # A3: Context compression
        if tur == 1:
            shared_ctx = build_context_history(brief, tum_ciktilar)
        else:
            _ctx_words = sum(len(m.get("content", "").split()) for m in shared_ctx)
            if _ctx_words > _CTX_WORD_LIMIT:
                _bb_summary = bb.to_summary()
                shared_ctx = [
                    {"role": "user", "content": f"Domain analysis request:\n{brief}\n\n[Context compressed]\n\n{_bb_summary}"},
                    {"role": "assistant", "content": tum_ciktilar},
                ]
            else:
                shared_ctx = shared_ctx + [
                    {"role": "user", "content": f"Round {tur} domain analysis:"},
                    {"role": "assistant", "content": tum_ciktilar},
                ]

        # -- GRUP B: Validation agents parallel --
        io.on_event("grup_b", {"round": tur})
        _bb_cv = bb.get_context_for("capraz_dogrulama", tur)
        _bb_as = bb.get_context_for("varsayim_belirsizlik", tur)
        val_sonuc = io.run_parallel([
            ("capraz_dogrulama", f"ROUND {tur}: Check numerical consistency.\n\n{_bb_cv}", shared_ctx, None),
            ("varsayim_belirsizlik", f"ROUND {tur}: Identify hidden assumptions.\n\n{_bb_as}", shared_ctx, None),
            ("varsayim_belirsizlik", f"ROUND {tur}: List missing/ambiguous/conflicting points.\n\n{_bb_as}", shared_ctx, None),
            ("literatur_patent", f"ROUND {tur}: Check standards and references.", shared_ctx, None),
        ], max_workers=4)
        capraz, varsayim, belirsiz, literatur = val_sonuc
        update_blackboard(bb, "capraz_dogrulama", capraz, tur)
        update_blackboard(bb, "varsayim_belirsizlik", varsayim, tur)

        # A5: Assumption consistency check
        _conflicting = bb.find_conflicting_assumptions()
        _conflict_note = ""
        if _conflicting:
            _lines = ["CONFLICTING ASSUMPTIONS:"]
            for ca in _conflicting[:5]:
                _lines.append(f"  {ca['agent_a']}: \"{ca['assumption_a']}\" vs {ca['agent_b']}: \"{ca['assumption_b']}\"")
            _conflict_note = "\n".join(_lines)

        # -- Observer --
        io.on_event("observer", {"round": tur})
        _bb_obs = bb.get_context_for("gozlemci", tur)
        gozlemci_cevabi = io.run_agent("gozlemci",
            f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\nROUND {tur}\n"
            f"CROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\nUNCERTAINTY: {belirsiz}\nLITERATURE: {literatur}\n"
            f"{_conflict_note}\n{_bb_obs}\n"
            f"Evaluate. KALİTE PUANI: XX/100. Specify corrections for next round.",
            gecmis=shared_ctx)
        update_blackboard(bb, "gozlemci", gozlemci_cevabi, tur)

        puan = extract_quality_score(gozlemci_cevabi)
        gozlemci_notu = gozlemci_cevabi
        tur_ozeti.append({"tur": tur, "puan": puan})

        io.on_event("round_score", {"tur": tur, "puan": puan})
        if hooks.on_round_score:
            hooks.on_round_score(tur, puan)
        io.checkpoint()

        # A4: Smart Group C skip — score >= 90
        if puan < 90:
            io.on_event("grup_c", {"round": tur})
            _bb_risk = bb.get_context_for("risk_guvenilirlik", tur)
            _bb_conf = bb.get_context_for("celisiki_cozum", tur)
            c_sonuc = io.run_parallel([
                ("risk_guvenilirlik", f"ROUND {tur}: FMEA on all designs.\n\n{_bb_risk}", shared_ctx, None),
                ("celisiki_cozum", f"OBSERVER:\n{gozlemci_cevabi}\n\n{_bb_conf}\nResolve conflicts.", shared_ctx, None),
            ], max_workers=2)
            update_blackboard(bb, "risk_guvenilirlik", c_sonuc[0], tur)
            update_blackboard(bb, "celisiki_cozum", c_sonuc[1], tur)

        if puan >= 85:
            io.on_event("early_stop", {"tur": tur, "puan": puan})
            break

    # ═══════════════════════════════════════════════════════════
    # POST-LOOP: Support agents + synthesis + final report
    # ═══════════════════════════════════════════════════════════
    io.on_event("post_loop", {})

    # -- GRUP D: 8 support agents parallel --
    _bb_summary_post = bb.to_summary()
    d_sonuc = io.run_parallel([
        ("soru_uretici", f"Problem: {brief}\nList critical unanswered questions.\n\n{_bb_summary_post}", shared_ctx, None),
        ("alternatif_senaryo", f"Problem: {brief}\nEvaluate 3 alternatives.\n\n{_bb_summary_post}", shared_ctx, None),
        ("kalibrasyon", f"Problem: {brief}\nBenchmark comparison.\n\n{_bb_summary_post}", shared_ctx, None),
        ("dogrulama_standartlar", f"Problem: {brief}\nStandards compliance.", shared_ctx, None),
        ("entegrasyon_arayuz", f"Problem: {brief}\nInterface risks.", shared_ctx, None),
        ("simulasyon_koordinator", f"Problem: {brief}\nSimulation strategy.", shared_ctx, None),
        ("maliyet_pazar", f"Problem: {brief}\nCost estimation.", shared_ctx, None),
        ("capraz_dogrulama", f"Problem: {brief}\nData quality.\n\n{_bb_summary_post}", shared_ctx, None),
    ], max_workers=6)
    soru, alt, kalib, std, enteg, sim, mal, veri = d_sonuc

    # -- Synthesis (2 passes) --
    io.on_event("synthesis", {})
    _bb_final = bb.to_summary()
    baglam = io.run_agent("sentez",
        f"Problem: {brief}\nSummarize confirmed parameters.\n\n{_bb_final}",
        gecmis=shared_ctx)

    sentez = io.run_agent("sentez",
        f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\n"
        f"OBSERVER: {gozlemci_cevabi}\nQUESTIONS: {soru}\nALTERNATIVES: {alt}\n"
        f"CALIBRATION: {kalib}\nSTANDARDS: {std}\nINTEGRATION: {enteg}\n"
        f"SIMULATION: {sim}\nCOST: {mal}\nDATA: {veri}\nCONTEXT: {baglam}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_final}\n\n"
        f"Synthesize all. Summary for Final Report Writer.",
        gecmis=shared_ctx)

    # -- Convergence check --
    _convergence = bb.check_convergence()
    _conv_note = ""
    if _convergence.get("oscillating"):
        _conv_note = f"\nWARNING: Oscillating parameters: {', '.join(_convergence['oscillating'][:5])}"

    # -- Final report --
    io.on_event("final_report", {})
    _rag_final = build_final_report_context(brief, io.rag_store) if io.rag_store else ""
    _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
    final = io.run_agent("final_rapor",
        f"Analysis in {len(tur_ozeti)} round(s). Domains: {', '.join(alan_isimleri)}\n"
        f"PROBLEM: {brief}\nOBSERVER: {gozlemci_cevabi}\n"
        f"QUESTIONS: {soru}\nALTERNATIVES: {alt}\nSYNTHESIS: {sentez}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_final}{_conv_note}{_rag_final_note}\n\n"
        f"Report: full technical findings per domain, conflicts, observer, recommendations. English only.",
        gecmis=shared_ctx)

    # -- GRUP E: Documentation + Summary --
    io.run_parallel([
        ("ozet_ve_sunum",
         f"Final engineering report:\n{final}\n"
         f"Produce an executive summary for non-technical stakeholders.",
         None, None),
        ("dokumantasyon_hafiza",
         f"Problem: {brief}\nFinal report:\n{final}\n"
         f"Identify required documentation tree and traceability requirements. "
         f"Capture key decisions, lessons learned, and reusable insights.",
         None, None),
    ], max_workers=2)

    return final, tur_ozeti
