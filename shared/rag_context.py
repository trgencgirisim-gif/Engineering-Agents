"""shared/rag_context.py — Unified RAG context injection for all entry points.

Provides shared functions for building RAG-enriched messages for:
- Domain agents (Round 1): past findings + structured parameters
- Final report writer: knowledge base context + analysis template
- Prompt engineer: past analyses for brief strengthening

All 3 entry points (main.py, app.py, orchestrator.py) call these
instead of duplicating RAG injection logic.
"""


def build_domain_message(brief: str, domain_key: str, domain_name: str,
                         rag_store, base_message: str = None,
                         max_tokens: int = 250) -> str:
    """Build domain agent message with RAG context injection.

    Injects two types of context for Round 1 domain agents:
    1. General domain-specific past analysis context (text excerpt)
    2. Structured parameters from similar past analyses (reference table)

    Args:
        brief: The analysis brief / enhanced brief
        domain_key: Domain slug (e.g. 'termal', 'yapisal')
        domain_name: Domain display name (e.g. 'Thermal', 'Structural')
        rag_store: RAGStore instance
        base_message: Override message (if None, uses brief)
        max_tokens: Token budget for domain context

    Returns:
        Enriched message string for the domain agent.
    """
    msg = base_message or brief

    try:
        # 1. General domain RAG context (text excerpt from similar analyses)
        domain_ctx = rag_store.get_similar_for_domain(
            brief, domain_name, max_tokens=min(max_tokens, 200)
        )
        # 2. Structured parameters from past analyses
        param_ctx = rag_store.get_parameters_for_domain(
            brief, domain_name, max_params=8
        )
    except Exception:
        # RAG failure should never block analysis
        return msg

    parts = []
    if domain_ctx:
        parts.append(f"PAST {domain_name.upper()} ANALYSIS CONTEXT:\n{domain_ctx}")
    if param_ctx:
        parts.append(param_ctx)

    if parts:
        msg = (
            f"{msg}\n\n"
            + "\n\n".join(parts)
            + "\n\nBuild on confirmed past findings. "
            "Verify parameters apply to this problem. "
            "Flag deviations from reference values."
        )

    return msg


def build_final_report_context(brief: str, rag_store,
                                max_tokens: int = 400) -> str:
    """Get RAG context for the final report writer.

    Combines two sources:
    1. General knowledge base context (text excerpts from similar analyses)
    2. Analysis template from high-quality similar analysis (section structure)

    Args:
        brief: The analysis brief
        rag_store: RAGStore instance
        max_tokens: Token budget for general RAG context

    Returns:
        Combined context string, or empty string if nothing relevant found.
    """
    parts = []

    try:
        # 1. General RAG context
        rag_ctx = rag_store.get_similar(brief, n=2, max_tokens=max_tokens)
        if rag_ctx:
            parts.append(f"KNOWLEDGE BASE CONTEXT:\n{rag_ctx}")

        # 2. Template from high-quality similar analysis
        template = rag_store.get_analysis_template(
            brief, min_score=85, max_distance=0.30
        )
        if template:
            parts.append(template)
    except Exception:
        # RAG failure should never block report generation
        pass

    return "\n\n".join(parts)


def build_prompt_engineer_message(brief: str, rag_store,
                                   max_tokens: int = 600) -> str:
    """Build prompt engineer message with RAG context.

    Enriches the brief with past analysis context so the prompt engineer
    can strengthen the brief by referencing known findings and gaps.

    Args:
        brief: Original user brief
        rag_store: RAGStore instance
        max_tokens: Token budget for RAG context

    Returns:
        Enriched brief string for prompt engineer, or original brief if
        no relevant past context found.
    """
    try:
        rag_context = rag_store.get_similar(brief, n=2, max_tokens=max_tokens)
    except Exception:
        return brief

    if rag_context:
        return (
            f"{brief}\n\n"
            f"{rag_context}\n\n"
            f"Using the past analyses above as reference, strengthen the brief. "
            f"Pay special attention to previously unresolved questions — "
            f"address them explicitly in the strengthened brief if applicable."
        )
    return brief
