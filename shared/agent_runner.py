"""
Shared agent execution core — single source of truth for API calls.

Used by orchestrator.py, main.py, and app.py to eliminate duplicated
agent execution logic (2-block cache, retry, thinking fallback, cost calc).

Each consumer provides its own:
  - Anthropic client instance
  - CACHE_PREAMBLE text
  - Agent config lookup
  - I/O callbacks (print, SSE emit, st.session_state update)
"""
import time
from typing import Optional
from config.agents_config import AGENTS, DESTEK_AJANLARI
from config.pricing import compute_cost


def resolve_agent(ajan_key: str, domain_model: str = None):
    """
    Look up agent config by key. Optionally override domain model.
    Returns a copy of the agent dict (safe to mutate).
    """
    ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
    if not ajan:
        return None
    ajan = dict(ajan)
    # Domain model override (not for protected agents)
    if domain_model and ajan_key in AGENTS and ajan_key not in ("final_rapor", "sentez"):
        ajan["model"] = f"claude-{domain_model}-4-6"
    return ajan


def build_system_blocks(ajan: dict, cache_preamble: str = ""):
    """
    Build 2-block system prompt array for Anthropic API.
    Block 1: CACHE_PREAMBLE (shared across all agents, cached 1hr)
    Block 2: Agent-specific sistem_promptu (per-agent, cached 5min)
    """
    if cache_preamble:
        return [
            {"type": "text", "text": cache_preamble,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": ajan["sistem_promptu"],
             "cache_control": {"type": "ephemeral"}},
        ]
    return [
        {"type": "text", "text": ajan["sistem_promptu"],
         "cache_control": {"type": "ephemeral"}},
    ]


def build_messages(mesaj: str, gecmis: list = None, cache_context: str = None):
    """
    Build messages array with optional cache_context as a separate cached block.
    """
    if gecmis is None:
        gecmis = []

    if cache_context and len(cache_context) > 800:
        user_content = [
            {"type": "text", "text": cache_context,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": mesaj},
        ]
    else:
        user_content = mesaj

    return gecmis + [{"role": "user", "content": user_content}]


def api_call(client, ajan: dict, system_blocks: list, mesajlar: list,
             max_retries: int = 5, on_retry=None):
    """
    Core API call with retry + thinking fallback.

    Returns (response, error_str). One of them is always None.
    on_retry: optional callback(deneme, bekleme) for logging retry events.
    """
    thinking_budget = ajan.get("thinking_budget", 0)
    max_tokens = ajan.get("max_tokens", 2000)

    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    for deneme in range(max_retries):
        try:
            yanit = client.messages.create(
                model=ajan["model"],
                max_tokens=max_tokens,
                system=system_blocks,
                messages=mesajlar,
                **extra_kwargs,
            )
            return yanit, None
        except Exception as e:
            err = str(e)
            if "thinking" in err.lower() and thinking_budget:
                extra_kwargs = {}
                continue
            elif "rate_limit" in err.lower() or "429" in err:
                bekleme = 60 * (deneme + 1)
                if on_retry:
                    on_retry(deneme, bekleme)
                time.sleep(bekleme)
            else:
                return None, str(e)
    return None, "Rate limit aşıldı, maksimum deneme sayısına ulaşıldı."


def extract_response(yanit):
    """
    Extract text, thinking, and usage from API response.
    Returns dict with: cevap, dusunce, inp, out, c_cre, c_rd
    """
    text_blocks = [b.text for b in yanit.content if b.type == "text"]
    thinking_blocks = [b.thinking for b in yanit.content if b.type == "thinking"]

    cevap = "\n".join(text_blocks).strip()
    dusunce = "\n".join(thinking_blocks).strip() if thinking_blocks else ""

    usage = yanit.usage
    inp = usage.input_tokens
    out = usage.output_tokens
    c_cre = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c_rd = getattr(usage, "cache_read_input_tokens", 0) or 0

    return {
        "cevap": cevap,
        "dusunce": dusunce,
        "inp": inp,
        "out": out,
        "c_cre": c_cre,
        "c_rd": c_rd,
    }


def run_agent(client, ajan_key: str, mesaj: str,
              gecmis: list = None, cache_context: str = None,
              cache_preamble: str = "", domain_model: str = None,
              on_retry=None):
    """
    Complete agent execution: resolve → build → call → extract → cost.

    Returns dict with:
      key, name, model, cevap, dusunce, cost, saved, inp, out, c_cre, c_rd
      error (None on success)
    """
    ajan = resolve_agent(ajan_key, domain_model)
    if not ajan:
        return {
            "key": ajan_key, "name": ajan_key, "model": "?",
            "cevap": f"ERROR: Agent '{ajan_key}' not found.",
            "dusunce": "", "cost": 0, "saved": 0,
            "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0,
            "error": "not_found",
        }

    system_blocks = build_system_blocks(ajan, cache_preamble)
    mesajlar = build_messages(mesaj, gecmis, cache_context)

    yanit, err = api_call(client, ajan, system_blocks, mesajlar, on_retry=on_retry)
    if err:
        return {
            "key": ajan_key, "name": ajan.get("isim", ajan_key), "model": ajan["model"],
            "cevap": f"ERROR: {err}", "dusunce": "",
            "cost": 0, "saved": 0,
            "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0,
            "error": err,
        }

    result = extract_response(yanit)
    actual_cost, saved = compute_cost(ajan["model"], result["inp"], result["out"],
                                       result["c_cre"], result["c_rd"])

    return {
        "key": ajan_key,
        "name": ajan.get("isim", ajan_key),
        "model": ajan["model"],
        "cevap": result["cevap"],
        "dusunce": result["dusunce"],
        "cost": actual_cost,
        "saved": saved,
        "inp": result["inp"],
        "out": result["out"],
        "c_cre": result["c_cre"],
        "c_rd": result["c_rd"],
        "error": None,
    }


def run_agents_parallel(client, gorevler: list, max_workers: int = 6,
                        cache_preamble: str = "", domain_model: str = None,
                        on_agent_done=None):
    """
    Run multiple agents in parallel using ThreadPoolExecutor.

    gorevler: list of tuples (ajan_key, mesaj[, gecmis[, cache_context]])
    on_agent_done: optional callback(idx, result_dict) called after each agent

    Returns list of result dicts in original order.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    n = len(gorevler)
    if n == 0:
        return []

    if n == 1:
        g = gorevler[0]
        r = run_agent(client, g[0], g[1],
                      g[2] if len(g) > 2 else None,
                      g[3] if len(g) > 3 else None,
                      cache_preamble, domain_model)
        if on_agent_done:
            on_agent_done(0, r)
        return [r]

    sonuclar = [None] * n

    def _worker(idx_gorev):
        idx, g = idx_gorev
        return idx, run_agent(
            client, g[0], g[1],
            g[2] if len(g) > 2 else None,
            g[3] if len(g) > 3 else None,
            cache_preamble, domain_model,
        )

    with ThreadPoolExecutor(max_workers=min(n, max_workers)) as ex:
        futures = {ex.submit(_worker, (i, g)): i for i, g in enumerate(gorevler)}
        for fut in as_completed(futures):
            try:
                idx, r = fut.result()
                sonuclar[idx] = r
                if on_agent_done:
                    on_agent_done(idx, r)
            except Exception as e:
                idx = futures[fut]
                sonuclar[idx] = {
                    "key": gorevler[idx][0], "name": gorevler[idx][0], "model": "?",
                    "cevap": f"ERROR: {e}", "dusunce": "",
                    "cost": 0, "saved": 0,
                    "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0,
                    "error": str(e),
                }

    return sonuclar
