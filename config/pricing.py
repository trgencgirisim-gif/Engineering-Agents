# Shared Anthropic model pricing — single source of truth
# Rates are per-token (divide $/M by 1_000_000)


def get_rates(model: str):
    """
    Returns (r_in, r_out, r_cre, r_rd) pricing rates for the given model.

    r_in  — normal input token rate
    r_out — output token rate
    r_cre — cache creation rate (+25% of input)
    r_rd  — cache read rate (-90% of input)
    """
    if "opus" in model:
        return 15 / 1_000_000, 75 / 1_000_000, 18.75 / 1_000_000, 1.5 / 1_000_000
    elif "sonnet" in model:
        return 3 / 1_000_000, 15 / 1_000_000, 3.75 / 1_000_000, 0.3 / 1_000_000
    else:  # haiku / fallback
        return 0.8 / 1_000_000, 4 / 1_000_000, 1.0 / 1_000_000, 0.08 / 1_000_000


def compute_cost(model: str, inp: int, out: int, c_cre: int = 0, c_rd: int = 0):
    """
    Compute actual cost and cache savings for an API call.

    Returns (actual_cost, saved) in USD.
    """
    r_in, r_out, r_cre, r_rd = get_rates(model)
    actual_cost = (inp * r_in) + (out * r_out) + (c_cre * r_cre) + (c_rd * r_rd)
    full_cost = ((inp + c_cre + c_rd) * r_in) + (out * r_out)
    saved = max(0.0, full_cost - actual_cost)
    return actual_cost, saved


# ── Average token profiles per agent type (from production data) ──
# Used by estimate_analysis_cost() for pre-analysis cost predictions.
# Format: (avg_input_tokens, avg_output_tokens)
_TOKEN_PROFILES = {
    "domain_a":       (2800, 1800),   # domain expert A
    "domain_b":       (2800, 1800),   # domain expert B
    "capraz_dogrulama": (6000, 1200),
    "varsayim_belirsizlik": (6000, 1000),
    "literatur_patent": (6000, 800),
    "gozlemci":       (8000, 1500),
    "risk_guvenilirlik": (6000, 1200),
    "celisiki_cozum": (6000, 1000),
    "soru_uretici":   (5000, 800),
    "alternatif_senaryo": (5000, 1200),
    "kalibrasyon":    (5000, 800),
    "dogrulama_standartlar": (5000, 800),
    "entegrasyon_arayuz": (5000, 800),
    "simulasyon_koordinator": (5000, 800),
    "maliyet_pazar":  (5000, 800),
    "sentez":         (10000, 2000),
    "final_rapor":    (12000, 3000),
    "ozet_ve_sunum":  (4000, 1000),
    "dokumantasyon_hafiza": (4000, 1000),
    "prompt_muhendisi": (1500, 800),
    "domain_selector": (1200, 400),
}


def estimate_analysis_cost(
    n_domains: int,
    mode: int,
    domain_model: str = "sonnet",
    max_rounds: int = 1,
    cache_hit_ratio: float = 0.6,
) -> dict:
    """
    Estimate total analysis cost before running.

    Returns dict with:
      estimated_usd: float — total estimated cost
      agent_count: int — total agent calls
      breakdown: dict — per-group cost estimates
    """
    # Resolve model names
    dm = "sonnet" if "sonnet" in domain_model or domain_model == "sonnet" else "opus"
    dm_model = f"claude-{dm}-4-6"
    opus_model = "claude-opus-4-6"

    def _agent_cost(profile_key, model, is_cached=False):
        inp, out = _TOKEN_PROFILES.get(profile_key, (3000, 1000))
        r_in, r_out, r_cre, r_rd = get_rates(model)
        if is_cached:
            # Cache hit: input at read rate
            input_cost = inp * r_rd
        else:
            # First call: cache creation cost
            input_cost = inp * r_cre
        return input_cost + (out * r_out)

    rounds = max_rounds if mode >= 3 else 1
    breakdown = {}
    agent_count = 0

    # Prep agents (prompt engineer + domain selector)
    prep_cost = _agent_cost("prompt_muhendisi", "claude-haiku-4-5-20251001") + \
                _agent_cost("domain_selector", "claude-haiku-4-5-20251001")
    agent_count += 2
    breakdown["prep"] = prep_cost

    # Domain agents per round
    agents_per_domain = 1 if mode == 1 else 2
    domain_cost_total = 0
    for r in range(rounds):
        cached = r > 0  # Round 2+ benefits from cache
        for _ in range(n_domains):
            for _ in range(agents_per_domain):
                domain_cost_total += _agent_cost("domain_a", dm_model, cached)
                agent_count += 1
    breakdown["domain_agents"] = domain_cost_total

    # Validation agents per round
    val_agents = {
        1: ["capraz_dogrulama", "soru_uretici"],
        2: ["capraz_dogrulama", "varsayim_belirsizlik"],
        3: ["capraz_dogrulama", "varsayim_belirsizlik", "varsayim_belirsizlik", "literatur_patent"],
        4: ["capraz_dogrulama", "varsayim_belirsizlik", "varsayim_belirsizlik", "literatur_patent"],
    }
    val_cost_total = 0
    for r in range(rounds):
        cached = r > 0
        for vk in val_agents.get(mode, []):
            val_cost_total += _agent_cost(vk, dm_model, cached)
            agent_count += 1
    breakdown["validation"] = val_cost_total

    # Observer per round
    obs_cost = 0
    for r in range(rounds):
        obs_cost += _agent_cost("gozlemci", opus_model, r > 0)
        agent_count += 1
    breakdown["observer"] = obs_cost

    # Group C (risk + conflict) — per round, mode 2+
    gc_cost = 0
    if mode >= 2:
        for r in range(rounds):
            gc_cost += _agent_cost("risk_guvenilirlik", dm_model, r > 0)
            gc_cost += _agent_cost("celisiki_cozum", dm_model, r > 0)
            agent_count += 2
    breakdown["risk_conflict"] = gc_cost

    # Post-loop support (mode 3/4 only)
    post_cost = 0
    if mode >= 3:
        post_agents = ["soru_uretici", "alternatif_senaryo", "kalibrasyon",
                       "dogrulama_standartlar", "entegrasyon_arayuz",
                       "simulasyon_koordinator", "maliyet_pazar", "capraz_dogrulama"]
        for pk in post_agents:
            post_cost += _agent_cost(pk, dm_model, True)
            agent_count += 1
    breakdown["post_loop"] = post_cost

    # Synthesis + Final report
    synth_cost = _agent_cost("sentez", opus_model, True) * 2  # called twice
    synth_cost += _agent_cost("final_rapor", opus_model, True)
    agent_count += 3
    breakdown["synthesis_final"] = synth_cost

    # Group E (summary + docs)
    ge_cost = _agent_cost("ozet_ve_sunum", "claude-haiku-4-5-20251001", True)
    agent_count += 1
    if mode >= 3:
        ge_cost += _agent_cost("dokumantasyon_hafiza", "claude-haiku-4-5-20251001", True)
        agent_count += 1
    breakdown["documentation"] = ge_cost

    # Apply cache hit ratio discount
    raw_total = sum(breakdown.values())
    estimated = raw_total * (1 - cache_hit_ratio * 0.3)  # ~18% savings at 60% hit ratio

    return {
        "estimated_usd": round(estimated, 4),
        "agent_count": agent_count,
        "breakdown": {k: round(v, 4) for k, v in breakdown.items()},
        "raw_total": round(raw_total, 4),
    }
