"""
Hybrid Output Parser — Regex-first extraction with LLM (Haiku) fallback.

Parses structured output from engineering analysis agents into
Blackboard-compatible data structures.

Agent output formats (already enforced via system prompts):
- Domain agents: KEY FINDINGS, CROSS-DOMAIN FLAG, ASSUMPTIONS, RISKS
- Cross-validator: ERROR_[N], DATA_GAP_[N], BLOCKING_ISSUES
- Assumption inspector: ASSUMPTION_[N], UNCERTAINTY_[N], CONFLICT_ASSUMPTION_[N]
- Observer: KALİTE PUANI, AGENT-BY-AGENT DIRECTIVES, CROSS-AGENT CONFLICTS
- Risk agent: FMEA with RPN values
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# REGEX PATTERNS
# ═══════════════════════════════════════════════════════════════

# Numerical parameters with units
_RE_PARAM = re.compile(
    r'(?:^|\s)(\d+\.?\d*)\s*'
    r'(mm|cm|m|km|MPa|GPa|kPa|Pa|bar|atm|psi|'
    r'°C|°F|K|kW|MW|W|hp|'
    r'kg|g|ton|lb|N|kN|MN|'
    r'Hz|kHz|MHz|rpm|rad/s|'
    r'm/s|km/h|ft/s|'
    r'J|kJ|MJ|cal|kcal|BTU|'
    r'kg/m³|g/cm³|lb/ft³|'
    r'm²|cm²|mm²|'
    r'L/min|m³/s|GPM|'
    r'dB|%|ppm)\b',
    re.IGNORECASE
)

# Cross-domain flags: "CROSS-DOMAIN FLAG → Thermal: verify max temp"
# Also matches "CROSS_DOMAIN_FLAG", "Cross-Domain Flag", arrow variants
_RE_CROSS_DOMAIN = re.compile(
    r'CROSS[-_]?DOMAIN\s+FLAG\s*[→:>-]+\s*'
    r'(\w[\w\s&/]*?):\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Assumption tags: "[ASSUMPTION] ...", "ASSUMPTION: ...", numbered
_RE_ASSUMPTION_INLINE = re.compile(
    r'\[ASSUMPTION\]\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Cross-validator errors: ERROR_[N]: Agent=X | Claimed=Y | Expected=Z | Impact=W
_RE_ERROR = re.compile(
    r'ERROR_?\[?(\d+)\]?:\s*'
    r'Agent\s*=\s*(.+?)\s*\|\s*'
    r'Claimed\s*=\s*(.+?)\s*\|\s*'
    r'Expected\s*=\s*(.+?)\s*\|\s*'
    r'Impact\s*=\s*(\w+)'
    r'(?:\s*\|\s*Correction\s*=\s*(.+?))?(?:\n|$)',
    re.IGNORECASE
)

# Data gaps: DATA_GAP_[N]: description
_RE_DATA_GAP = re.compile(
    r'DATA_GAP_?\[?(\d+)\]?:\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Blocking issues line
_RE_BLOCKING = re.compile(
    r'BLOCKING_ISSUES?:\s*(.+?)(?:\n\n|\Z)',
    re.IGNORECASE | re.DOTALL
)

# Assumption inspector: ASSUMPTION_[N]: Agent=X | Type=(a/b/c) | ...
_RE_ASSUMPTION_FORMAL = re.compile(
    r'ASSUMPTION_?\[?(\d+)\]?:\s*'
    r'Agent\s*=\s*(.+?)\s*\|\s*'
    r'Type\s*=\s*\(?([abc])\)?\w*\s*\|\s*'
    r'Explicit\s*=\s*(YES|NO)\s*\|\s*'
    r'Impact\s*=\s*(\w+)'
    r'(?:\s*\|\s*Validation_needed\s*=\s*(YES|NO))?',
    re.IGNORECASE
)

# Uncertainty: UNCERTAINTY_[N]: Source=X | Range=Y | Impact=Z
_RE_UNCERTAINTY = re.compile(
    r'UNCERTAINTY_?\[?(\d+)\]?:\s*'
    r'Source\s*=\s*(.+?)\s*\|\s*'
    r'Range\s*=\s*(.+?)\s*\|\s*'
    r'Impact\s*=\s*(\w+)'
    r'(?:\s*\|\s*Recommended_action\s*=\s*(.+?))?(?:\n|$)',
    re.IGNORECASE
)

# Conflict assumptions: CONFLICT_ASSUMPTION_[N]: Agent A assumes X vs Agent B assumes Y
_RE_CONFLICT_ASSUMPTION = re.compile(
    r'CONFLICT_ASSUMPTION_?\[?(\d+)\]?:\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Observer quality score: KALİTE PUANI: XX/100
_RE_QUALITY_SCORE = re.compile(
    r'KAL[İI]TE\s+PUANI\s*:\s*(\d{1,3})\s*/\s*100',
    re.IGNORECASE
)

# Observer per-agent directives: AGENT_NAME: [ACTION: detail]
# Matches: "malzeme_a: [FIX: wall thickness needs recalculation]"
# Also: "malzeme_a: SATISFACTORY"
_RE_DIRECTIVE = re.compile(
    r'^([a-z_]+(?:_[ab])?):\s*'
    r'(?:\[(CORRECT|FIX|ADD):\s*(.+?)\]|'
    r'(SATISFACTORY))',
    re.IGNORECASE | re.MULTILINE
)

# Observer cross-agent conflicts: CONFLICT_[N]: ...
_RE_OBSERVER_CONFLICT = re.compile(
    r'CONFLICT_?\[?(\d+)\]?:\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Early termination: EARLY_TERMINATION: YES/NO
_RE_EARLY_TERM = re.compile(
    r'EARLY_TERMINATION:\s*(YES|NO)',
    re.IGNORECASE
)

# Risk/FMEA: RPN values
_RE_RPN = re.compile(
    r'(?:RPN|Risk\s+Priority\s+Number)\s*[=:]\s*(\d+)',
    re.IGNORECASE
)

# FMEA component lines — flexible matching
_RE_FMEA_LINE = re.compile(
    r'(?:^|\n)\s*[-•*]?\s*(?:Component|Failure\s+Mode|Item)\s*[=:]\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Severity/Occurrence/Detection ratings
_RE_FMEA_SOD = re.compile(
    r'(?:Severity|S)\s*[=:]\s*(\d+)\s*[,|/;]\s*'
    r'(?:Occurrence|O)\s*[=:]\s*(\d+)\s*[,|/;]\s*'
    r'(?:Detection|D)\s*[=:]\s*(\d+)',
    re.IGNORECASE
)

# Key findings section
_RE_KEY_FINDINGS = re.compile(
    r'(?:KEY\s+FINDINGS|FINDINGS|RESULTS)\s*[:\n](.+?)(?=\n##|\n(?:RISK|RECOMMEND|CROSS-DOMAIN|ASSUMPTION|\Z))',
    re.IGNORECASE | re.DOTALL
)

# Component name in backward search (precompiled for parse_risk_output)
_RE_COMPONENT_BACKWARD = re.compile(r'[-•*]\s*(.+?)(?:\n|$)')

# Conflict resolution patterns (precompiled)
_RE_RESOLUTION_BLOCK = re.compile(
    r'(?:RESOLUTION|CONFLICT)_?\[?(\d+)\]?\s*[:\n]\s*(.+?)(?=(?:RESOLUTION|CONFLICT)_?\[?\d|\Z)',
    re.IGNORECASE | re.DOTALL
)
_RE_WINNER = re.compile(
    r'(?:(?:WINNER|BETTER SUPPORTED|RECOMMENDED)\s*[=:]\s*(.+?)(?:\n|$))',
    re.IGNORECASE
)
_RE_CONSENSUS = re.compile(
    r'(?:CONSENSUS|AGREED|CONFIRMED)\s*[:\n]\s*[-•*]?\s*(.+?)(?:\n|$)',
    re.IGNORECASE
)

# Named parameter pattern: "parameter_name = value unit" or "parameter_name: value unit"
_RE_NAMED_PARAM = re.compile(
    r'([A-Za-z][A-Za-z_ ]{2,30}?)\s*[=:]\s*'
    r'(\d+\.?\d*)\s*'
    r'(mm|cm|m|km|MPa|GPa|kPa|Pa|bar|'
    r'°C|°F|K|kW|MW|W|'
    r'kg|g|N|kN|Hz|rpm|'
    r'm/s|J|kJ|MJ|dB|%)\b',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════
# DOMAIN OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_domain_output(text: str, agent_key: str) -> dict:
    """
    Parse domain agent (_a or _b) output.

    Returns:
        {
            "parameters": [{"name": str, "value": str, "unit": str, "context": str}],
            "cross_domain_flags": [{"target_domain": str, "issue": str}],
            "assumptions": [{"text": str}],
            "key_findings_raw": str
        }
    """
    result = {
        "parameters": [],
        "cross_domain_flags": [],
        "assumptions": [],
        "key_findings_raw": "",
    }

    if not text:
        return result

    # ── Cross-domain flags ──────────────────────────────────
    for m in _RE_CROSS_DOMAIN.finditer(text):
        target = m.group(1).strip().lower()
        issue = m.group(2).strip()
        result["cross_domain_flags"].append({
            "target_domain": target,
            "issue": issue,
        })

    # ── Inline assumptions ──────────────────────────────────
    for m in _RE_ASSUMPTION_INLINE.finditer(text):
        result["assumptions"].append({"text": m.group(1).strip()})

    # ── Key findings section ────────────────────────────────
    kf_match = _RE_KEY_FINDINGS.search(text)
    if kf_match:
        result["key_findings_raw"] = kf_match.group(1).strip()

    # ── Named parameters (from full text) ───────────────────
    seen_params = set()
    for m in _RE_NAMED_PARAM.finditer(text):
        name = m.group(1).strip().lower().replace(" ", "_")
        value = m.group(2)
        unit = m.group(3)
        param_key = f"{name}_{value}_{unit}"
        if param_key not in seen_params:
            seen_params.add(param_key)
            # Get surrounding context (±40 chars)
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            context = text[start:end].replace("\n", " ").strip()
            result["parameters"].append({
                "name": name,
                "value": value,
                "unit": unit,
                "context": context,
            })

    # ── Bare numerical parameters (fallback) ────────────────
    if len(result["parameters"]) < 3:
        for m in _RE_PARAM.finditer(text):
            value = m.group(1)
            unit = m.group(2)
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 20)
            context = text[start:end].replace("\n", " ").strip()
            param_key = f"_{value}_{unit}"
            if param_key not in seen_params:
                seen_params.add(param_key)
                result["parameters"].append({
                    "name": f"value_{value}{unit}",
                    "value": value,
                    "unit": unit,
                    "context": context,
                })

    return result


# ═══════════════════════════════════════════════════════════════
# CROSS-VALIDATION OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_crossval_output(text: str) -> dict:
    """
    Parse Cross-Validation & Data Analyst output.

    Returns:
        {
            "errors": [{"id", "agent", "claimed", "expected", "impact", "correction"}],
            "data_gaps": [{"id", "description"}],
            "blocking_issues": str,
            "error_summary": {"critical": int, "high": int, "medium": int}
        }
    """
    result = {
        "errors": [],
        "data_gaps": [],
        "blocking_issues": "",
        "error_summary": {"critical": 0, "high": 0, "medium": 0},
    }

    if not text:
        return result

    for m in _RE_ERROR.finditer(text):
        impact = m.group(5).upper() if m.group(5) else "MEDIUM"
        error = {
            "id": int(m.group(1)),
            "agent": m.group(2).strip(),
            "claimed": m.group(3).strip(),
            "expected": m.group(4).strip(),
            "impact": impact,
            "correction": m.group(6).strip() if m.group(6) else "",
        }
        result["errors"].append(error)

        if impact == "CRITICAL":
            result["error_summary"]["critical"] += 1
        elif impact == "HIGH":
            result["error_summary"]["high"] += 1
        else:
            result["error_summary"]["medium"] += 1

    for m in _RE_DATA_GAP.finditer(text):
        result["data_gaps"].append({
            "id": int(m.group(1)),
            "description": m.group(2).strip(),
        })

    blocking_m = _RE_BLOCKING.search(text)
    if blocking_m:
        result["blocking_issues"] = blocking_m.group(1).strip()

    return result


# ═══════════════════════════════════════════════════════════════
# ASSUMPTION & UNCERTAINTY OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_assumption_output(text: str) -> dict:
    """
    Parse Assumption & Uncertainty Inspector output.

    Returns:
        {
            "assumptions": [{"id", "agent", "type", "explicit", "impact", "needs_validation"}],
            "uncertainties": [{"id", "source", "range", "impact", "action"}],
            "conflict_assumptions": [{"id", "description"}],
            "summary": {"critical_count": int, "high_uncertainty_count": int}
        }
    """
    result = {
        "assumptions": [],
        "uncertainties": [],
        "conflict_assumptions": [],
        "summary": {"critical_count": 0, "high_uncertainty_count": 0},
    }

    if not text:
        return result

    for m in _RE_ASSUMPTION_FORMAL.finditer(text):
        assumption = {
            "id": int(m.group(1)),
            "agent": m.group(2).strip(),
            "type": m.group(3).lower(),
            "explicit": m.group(4).upper() == "YES",
            "impact": m.group(5).upper(),
            "needs_validation": m.group(6).upper() == "YES" if m.group(6) else False,
        }
        result["assumptions"].append(assumption)
        if assumption["impact"] in ("HIGH", "CRITICAL") and assumption["needs_validation"]:
            result["summary"]["critical_count"] += 1

    for m in _RE_UNCERTAINTY.finditer(text):
        unc = {
            "id": int(m.group(1)),
            "source": m.group(2).strip(),
            "range": m.group(3).strip(),
            "impact": m.group(4).upper(),
            "action": m.group(5).strip() if m.group(5) else "",
        }
        result["uncertainties"].append(unc)
        if unc["impact"] in ("HIGH", "CRITICAL"):
            result["summary"]["high_uncertainty_count"] += 1

    for m in _RE_CONFLICT_ASSUMPTION.finditer(text):
        result["conflict_assumptions"].append({
            "id": int(m.group(1)),
            "description": m.group(2).strip(),
        })

    return result


# ═══════════════════════════════════════════════════════════════
# OBSERVER OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_observer_output(text: str) -> dict:
    """
    Parse Observer / Meta-Agent output.

    Returns:
        {
            "score": int (0-100),
            "directives": [{"agent", "action", "detail"}],
            "conflicts": [{"id", "description"}],
            "early_termination": bool,
            "overall_assessment": str
        }
    """
    result = {
        "score": 0,
        "directives": [],
        "conflicts": [],
        "early_termination": False,
        "overall_assessment": "",
    }

    if not text:
        return result

    # ── Score ────────────────────────────────────────────────
    score_m = _RE_QUALITY_SCORE.search(text)
    if score_m:
        result["score"] = int(score_m.group(1))

    # ── Per-agent directives ────────────────────────────────
    for m in _RE_DIRECTIVE.finditer(text):
        agent_name = m.group(1).strip().lower()
        if m.group(4):  # SATISFACTORY
            result["directives"].append({
                "agent": agent_name,
                "action": "SATISFACTORY",
                "detail": "",
            })
        else:
            result["directives"].append({
                "agent": agent_name,
                "action": m.group(2).upper(),
                "detail": m.group(3).strip(),
            })

    # ── Conflicts ────────────────────────────────────────────
    for m in _RE_OBSERVER_CONFLICT.finditer(text):
        result["conflicts"].append({
            "id": int(m.group(1)),
            "description": m.group(2).strip(),
        })

    # ── Early termination ────────────────────────────────────
    et_m = _RE_EARLY_TERM.search(text)
    if et_m:
        result["early_termination"] = et_m.group(1).upper() == "YES"

    # ── Overall assessment (first paragraph after ## OVERALL ASSESSMENT)
    oa_match = re.search(
        r'##?\s*OVERALL\s+ASSESSMENT\s*\n(.+?)(?=\n##|\Z)',
        text, re.IGNORECASE | re.DOTALL
    )
    if oa_match:
        result["overall_assessment"] = oa_match.group(1).strip()[:500]

    return result


# ═══════════════════════════════════════════════════════════════
# RISK / FMEA OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_risk_output(text: str) -> dict:
    """
    Parse Risk & Reliability (FMEA) agent output.

    Returns:
        {
            "risks": [{"component", "severity", "occurrence", "detection", "rpn"}],
            "max_rpn": int,
            "critical_count": int
        }
    """
    result = {
        "risks": [],
        "max_rpn": 0,
        "critical_count": 0,
    }

    if not text:
        return result

    # Strategy: Find RPN values, then look backward for S/O/D and component
    rpn_positions = list(_RE_RPN.finditer(text))
    sod_positions = list(_RE_FMEA_SOD.finditer(text))

    # If we have S/O/D structured lines, use those
    for m in sod_positions:
        s, o, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        rpn = s * o * d

        # Look backward for component name
        before = text[max(0, m.start() - 200):m.start()]
        comp_match = _RE_COMPONENT_BACKWARD.search(before)
        component = comp_match.group(1).strip()[:80] if comp_match else "Unknown"

        risk = {
            "component": component,
            "severity": s,
            "occurrence": o,
            "detection": d,
            "rpn": rpn,
        }
        result["risks"].append(risk)
        result["max_rpn"] = max(result["max_rpn"], rpn)
        if rpn >= 200 or s >= 9:
            result["critical_count"] += 1

    # Fallback: extract standalone RPN values if no S/O/D found
    if not sod_positions:
        for m in rpn_positions:
            rpn = int(m.group(1))
            before = text[max(0, m.start() - 150):m.start()]
            comp_match = _RE_COMPONENT_BACKWARD.search(before)
            component = comp_match.group(1).strip()[:80] if comp_match else "Unknown"
            result["risks"].append({
                "component": component,
                "severity": 0,
                "occurrence": 0,
                "detection": 0,
                "rpn": rpn,
            })
            result["max_rpn"] = max(result["max_rpn"], rpn)
            if rpn >= 200:
                result["critical_count"] += 1

    return result


# ═══════════════════════════════════════════════════════════════
# CONFLICT RESOLUTION OUTPUT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_conflict_resolution(text: str) -> dict:
    """
    Parse Conflict Resolution agent output.

    Returns:
        {
            "resolutions": [{"conflict", "resolution", "winner"}],
            "consensus_items": [str]
        }
    """
    result = {"resolutions": [], "consensus_items": []}

    if not text:
        return result

    # Pattern: RESOLUTION_[N] or numbered resolution blocks
    for m in _RE_RESOLUTION_BLOCK.finditer(text):
        block = m.group(2).strip()
        winner_m = _RE_WINNER.search(block)
        result["resolutions"].append({
            "conflict": f"Conflict {m.group(1)}",
            "resolution": block[:300],
            "winner": winner_m.group(1).strip() if winner_m else "",
        })

    # Consensus items
    for m in _RE_CONSENSUS.finditer(text):
        result["consensus_items"].append(m.group(1).strip())

    return result


# ═══════════════════════════════════════════════════════════════
# LLM FALLBACK EXTRACTOR
# ═══════════════════════════════════════════════════════════════

_LLM_EXTRACT_PROMPT = """Extract structured data from this engineering agent output.

OUTPUT FORMAT (JSON):
{fields_schema}

AGENT OUTPUT:
{text}

Return ONLY valid JSON. No markdown, no explanation."""


def llm_fallback_extract(
    text: str,
    agent_type: str,
    client: Any = None,
) -> dict:
    """
    LLM-based extraction fallback using claude-haiku-4-5.
    Called when regex extracts < 30% of expected fields.

    Args:
        text: Agent output text
        agent_type: One of "domain", "crossval", "assumption", "observer", "risk"
        client: Anthropic client instance
    """
    if not client or not text:
        return {}

    schemas = {
        "domain": '{"parameters": [{"name": str, "value": str, "unit": str}], '
                  '"cross_domain_flags": [{"target_domain": str, "issue": str}], '
                  '"assumptions": [{"text": str}]}',
        "crossval": '{"errors": [{"agent": str, "claimed": str, "expected": str, "impact": str}], '
                    '"data_gaps": [{"description": str}], '
                    '"blocking_issues": str}',
        "assumption": '{"assumptions": [{"agent": str, "type": "a/b/c", "impact": "HIGH/MEDIUM/LOW"}], '
                      '"uncertainties": [{"source": str, "range": str, "impact": str}]}',
        "observer": '{"score": int, "directives": [{"agent": str, "action": "FIX/ADD/CORRECT/SATISFACTORY", '
                    '"detail": str}], "early_termination": bool}',
        "risk": '{"risks": [{"component": str, "severity": int, "occurrence": int, '
                '"detection": int, "rpn": int}]}',
    }

    schema = schemas.get(agent_type, "{}")
    prompt = _LLM_EXTRACT_PROMPT.format(fields_schema=schema, text=text[:3000])

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning("LLM fallback extraction failed: %s", e)
        return {}


# ═══════════════════════════════════════════════════════════════
# UNIFIED PARSE FUNCTION
# ═══════════════════════════════════════════════════════════════

# Minimum expected field counts for LLM fallback trigger
_MIN_FIELDS = {
    "domain": {"parameters": 2},
    "crossval": {"errors": 1},
    "assumption": {"assumptions": 1},
    "observer": {"score": 1},
    "risk": {"risks": 1},
}


def parse_agent_output(
    text: str,
    agent_key: str,
    client: Any = None,
) -> dict:
    """
    Unified parse function — routes to appropriate parser based on agent_key.
    Falls back to LLM if regex extraction is insufficient.

    Args:
        text: Agent output text
        agent_key: Agent identifier (e.g., "yanma_a", "capraz_dogrulama", "gozlemci")
        client: Anthropic client (for LLM fallback, optional)

    Returns:
        Parsed dict with agent-type-specific fields
    """
    if not text:
        return {}

    # Determine agent type
    if agent_key.endswith("_a") or agent_key.endswith("_b"):
        # Check if it's a domain agent vs support agent ending in _a/_b
        from config.agents_config import DESTEK_AJANLARI
        if agent_key not in DESTEK_AJANLARI:
            agent_type = "domain"
            parsed = parse_domain_output(text, agent_key)
        else:
            return {}
    elif agent_key == "capraz_dogrulama":
        agent_type = "crossval"
        parsed = parse_crossval_output(text)
    elif agent_key == "varsayim_belirsizlik":
        agent_type = "assumption"
        parsed = parse_assumption_output(text)
    elif agent_key == "gozlemci":
        agent_type = "observer"
        parsed = parse_observer_output(text)
    elif agent_key == "risk_guvenilirlik":
        agent_type = "risk"
        parsed = parse_risk_output(text)
    elif agent_key == "celisiki_cozum":
        return parse_conflict_resolution(text)
    else:
        return {}

    # ── LLM fallback check ──────────────────────────────────
    if client and agent_type in _MIN_FIELDS:
        needs_fallback = False
        for field, min_count in _MIN_FIELDS[agent_type].items():
            val = parsed.get(field)
            if isinstance(val, list) and len(val) < min_count:
                needs_fallback = True
            elif isinstance(val, int) and val == 0 and min_count > 0:
                needs_fallback = True

        if needs_fallback and len(text) > 200:
            logger.info("Regex insufficient for %s, trying LLM fallback", agent_key)
            llm_result = llm_fallback_extract(text, agent_type, client)
            if llm_result:
                # Merge: LLM fills gaps, regex results take priority
                for k, v in llm_result.items():
                    if k not in parsed or (isinstance(v, list) and len(v) > len(parsed.get(k, []))):
                        parsed[k] = v
                    elif isinstance(v, int) and parsed.get(k, 0) == 0:
                        parsed[k] = v

    return parsed
