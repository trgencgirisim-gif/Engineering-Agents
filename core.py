"""
core.py — Shared tool-integration layer for all entry points.

Provides:
- _ajan_api_with_tools(): Agent API call with Anthropic native tool_use
- _ajan_api_routed(): Router that selects tool-enabled or standard path
- get_domain_from_key(): Extract domain key from agent key

This module is imported by orchestrator.py, main.py, and app.py.
It does NOT replace the existing _api_call / ajan_calistir functions —
it adds tool-aware alternatives that the entry points can opt into.
"""
from __future__ import annotations

import os
import time
from typing import Optional

import anthropic

from config.agents_config import AGENTS, DESTEK_AJANLARI
from config.pricing import compute_cost

# Lazy-imported to avoid circular imports and startup penalty
_solver_tools = None
_extractors = None


def _ensure_tools():
    """Lazy-load tools module on first use."""
    global _solver_tools
    if _solver_tools is None:
        import tools as t
        _solver_tools = t


def _ensure_extractors():
    """Lazy-load extractors on first use."""
    global _extractors
    if _extractors is None:
        from tools.extractors.cantera_extractor import CanteraExtractor
        from tools.extractors.fenics_extractor import FenicsExtractor
        from tools.extractors.coolprop_extractor import CoolPropExtractor
        from tools.extractors.python_control_extractor import PythonControlExtractor
        from tools.extractors.materials_project_extractor import MaterialsProjectExtractor
        _extractors = {
            "cantera":           CanteraExtractor(),
            "fenics":            FenicsExtractor(),
            "coolprop":          CoolPropExtractor(),
            "python_control":    PythonControlExtractor(),
            "materials_project": MaterialsProjectExtractor(),
        }


MAX_TOOL_ROUNDS = 3


def get_domain_from_key(agent_key: str) -> str:
    """Extract domain from agent key. 'yanma_a' -> 'yanma'."""
    ajan = AGENTS.get(agent_key)
    if ajan and ajan.get("domain"):
        return ajan["domain"]
    return agent_key.rsplit("_", 1)[0] if "_" in agent_key else ""


def has_tools_for_agent(agent_key: str) -> bool:
    """Check if the given agent has any available solver tools."""
    _ensure_tools()
    domain = get_domain_from_key(agent_key)
    return bool(_solver_tools.get_available_tools_for_domain(domain))


def run_tool_loop(
    client_instance: anthropic.Anthropic,
    agent_key: str,
    system_blocks: list,
    messages: list,
    model: str,
    max_tokens: int,
    brief: str = "",
    thinking_budget: int = 0,
) -> dict:
    """
    Run the LLM with tool definitions and handle tool_use responses.

    Returns dict with:
        cevap: str       — final text response
        dusunce: str     — thinking text (if any)
        cost: float      — total USD cost
        inp: int         — total input tokens
        out: int         — total output tokens
        c_cre: int       — cache creation tokens
        c_rd: int        — cache read tokens
        saved: float     — cache savings USD
    """
    _ensure_tools()
    _ensure_extractors()

    domain = get_domain_from_key(agent_key)
    anthropic_tools = _solver_tools.get_anthropic_tools_for_domain(domain)

    totals = {"cost": 0.0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0.0}
    final_text = ""
    final_thinking = ""

    for round_num in range(MAX_TOOL_ROUNDS):
        # Offer tools on the first round only
        call_tools = anthropic_tools if round_num == 0 else []

        extra_kwargs = {}
        if thinking_budget and round_num == 0:
            extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

        try:
            response = client_instance.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_blocks,
                messages=messages,
                tools=call_tools if call_tools else None,
                **extra_kwargs,
            )
        except Exception as e:
            err = str(e)
            if "thinking" in err.lower() and thinking_budget:
                extra_kwargs = {}
                response = client_instance.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=messages,
                    tools=call_tools if call_tools else None,
                )
            elif "rate_limit" in err.lower() or "429" in err:
                time.sleep(60 * (round_num + 1))
                continue
            else:
                raise

        # Accumulate token costs
        u = response.usage
        inp  = u.input_tokens
        out  = u.output_tokens
        ccre = getattr(u, "cache_creation_input_tokens", 0) or 0
        crd  = getattr(u, "cache_read_input_tokens", 0) or 0
        actual, saved = compute_cost(model, inp, out, ccre, crd)

        totals["cost"]  += actual
        totals["inp"]   += inp
        totals["out"]   += out
        totals["c_cre"] += ccre
        totals["c_rd"]  += crd
        totals["saved"] += saved

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name   = block.name
                tool_inputs = dict(block.input)

                # Enrich inputs from brief via extractor if available
                if _extractors and brief:
                    extractor = _extractors.get(tool_name)
                    if extractor:
                        extracted = extractor.extract("", brief)
                        if extracted:
                            for k, v in extracted.items():
                                tool_inputs.setdefault(k, v)

                # Run the solver
                solver = _solver_tools.get_tool(tool_name)
                if solver and solver.is_available():
                    result      = solver.execute(tool_inputs)
                    result_text = result.to_agent_text()
                else:
                    result_text = (
                        f"[SOLVER_RESULT — {tool_name.upper()}]\n"
                        f"STATUS: UNAVAILABLE\n"
                        f"INSTRUCTION: Solver not installed. "
                        f"Use engineering estimate and mark with [ASSUMPTION].\n"
                        f"[/SOLVER_RESULT]"
                    )

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     result_text,
                })

            # Extend conversation with assistant turn + tool results
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user",      "content": tool_results},
            ]
            continue  # LLM will now interpret the solver output

        else:  # stop_reason == "end_turn"
            text_blocks = [b.text for b in response.content if b.type == "text"]
            thinking_blocks = [b.thinking for b in response.content
                               if hasattr(b, "thinking") and b.type == "thinking"]
            final_text     = "\n".join(text_blocks).strip()
            final_thinking = "\n".join(thinking_blocks).strip() if thinking_blocks else ""
            break

    return {
        "cevap":   final_text,
        "dusunce": final_thinking,
        **totals,
    }
