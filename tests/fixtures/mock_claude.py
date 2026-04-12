"""tests/fixtures/mock_claude.py — Mocked Anthropic API client for testing.

Provides deterministic responses without hitting the real API.
Each fixture response maps an agent key pattern to a canned output.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock


# ── Canned agent responses ───────────────────────────────────

_DEFAULT_RESPONSES: Dict[str, str] = {
    # Domain expert A — provides parameters and assumptions
    "_a": (
        "## Analysis\n\n"
        "Based on the problem description:\n\n"
        "PARAMETER_1: pressure = 150 bar [source: design spec]\n"
        "PARAMETER_2: temperature = 450 K [source: operating conditions]\n"
        "PARAMETER_3: flow_rate = 2.5 kg/s [source: mass balance]\n\n"
        "ASSUMPTION_1: Ideal gas behaviour assumed for preliminary calculations\n"
        "ASSUMPTION_2: Steady-state operation\n\n"
        "The analysis indicates nominal operating conditions within acceptable limits.\n"
        "CROSS_DOMAIN_FLAG: termal — Verify heat exchanger effectiveness at 450 K\n"
    ),
    # Domain expert B — practical perspective
    "_b": (
        "## Practical Assessment\n\n"
        "Field experience indicates:\n\n"
        "PARAMETER_1: pressure = 145 bar [source: field measurement]\n"
        "PARAMETER_2: temperature = 460 K [source: thermocouple data]\n\n"
        "ASSUMPTION_3: 10% safety margin applied to all pressure values\n\n"
        "No critical anomalies detected in practical operating range.\n"
    ),
    # Cross-validator
    "capraz_dogrulama": (
        "## Cross-Validation Report\n\n"
        "ERROR_1: Pressure discrepancy of 5 bar between Agent A (150) and Agent B (145)\n"
        "ERROR_2: Temperature discrepancy of 10 K between agents\n\n"
        "DATA_GAP_1: No fatigue analysis provided\n\n"
        "Overall validation: CONDITIONAL PASS — resolve pressure discrepancy.\n"
    ),
    # Observer / quality scorer
    "gozlemci": (
        "## Quality Assessment\n\n"
        "KALİTE PUANI: 72/100\n\n"
        "DIRECTIVE_yanma_a: FIX — Reconcile pressure value with Agent B measurement\n"
        "DIRECTIVE_termal_a: ADD — Include heat exchanger effectiveness calculation\n\n"
        "Analysis is technically sound but requires parameter alignment.\n"
    ),
    # Final report
    "final_rapor": (
        "## Executive Summary\n\n"
        "This multi-agent engineering analysis evaluated the system under nominal conditions.\n\n"
        "## Abstract\n"
        "The analysis covered combustion and thermal domains. Key findings include a pressure "
        "operating point of 147.5 bar (consensus) and temperature of 455 K.\n\n"
        "## Key Findings\n"
        "1. System operates within design envelope\n"
        "2. Pressure values aligned to within 3.5% between theoretical and field measurements\n"
        "3. No critical failure modes identified at current operating point\n\n"
        "## Recommendations\n"
        "1. Verify heat exchanger effectiveness in next maintenance window\n"
        "2. Establish pressure monitoring protocol\n"
    ),
    # Prompt engineer
    "prompt_muhendisi": (
        "Enhanced brief: Detailed engineering analysis of the combustion system "
        "operating at design pressure (150 bar) and temperature (450 K). "
        "Focus on parameter consistency and cross-domain validation."
    ),
    # Domain selector
    "alan_secici": json.dumps({
        "domains": [
            {"key": "yanma", "name": "Combustion"},
            {"key": "termal", "name": "Thermal"},
        ]
    }),
}


def _get_response_for_agent(agent_key: str) -> str:
    """Return a deterministic canned response based on agent key."""
    # Exact match first
    if agent_key in _DEFAULT_RESPONSES:
        return _DEFAULT_RESPONSES[agent_key]
    # Suffix match (_a or _b domain agents)
    for suffix in ("_a", "_b"):
        if agent_key.endswith(suffix):
            return _DEFAULT_RESPONSES[suffix]
    return f"Mock response for agent: {agent_key}\n\nAnalysis complete."


# ── Mock response objects ────────────────────────────────────

def _make_usage(input_tokens: int = 500, output_tokens: int = 300,
                cache_creation_input_tokens: int = 100,
                cache_read_input_tokens: int = 50):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_creation_input_tokens = cache_creation_input_tokens
    usage.cache_read_input_tokens = cache_read_input_tokens
    return usage


def _make_content_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_mock_response(agent_key: str = "", text: Optional[str] = None) -> MagicMock:
    """Create a mock Anthropic API response for the given agent."""
    response_text = text or _get_response_for_agent(agent_key)
    resp = MagicMock()
    resp.content = [_make_content_block(response_text)]
    resp.usage = _make_usage()
    resp.stop_reason = "end_turn"
    return resp


def make_mock_client(agent_key_override: str = "") -> MagicMock:
    """Create a fully-mocked Anthropic client whose .messages.create() returns canned data."""
    client = MagicMock()

    def _create(*args, **kwargs):
        # Infer agent key from system prompt if possible
        system = kwargs.get("system", [])
        key = agent_key_override
        if not key and isinstance(system, list) and len(system) >= 2:
            # Agent key is not directly available but we can check messages
            pass
        return make_mock_response(key)

    client.messages.create.side_effect = _create
    return client
