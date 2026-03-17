"""
Blackboard — Structured Analysis State for Multi-Agent Engineering System.

Central state object that agents write findings to and read relevant data from.
Provides selective context injection: each agent type receives only the
blackboard sections relevant to its task, reducing token usage and improving focus.

Sections:
    parameters      — Extracted numerical values with source, confidence, unit
    conflicts       — Agent A vs B disagreements (open/resolved)
    assumptions     — Labeled assumptions from all agents
    cross_domain_flags — Issues flagged for other domains, indexed by target
    risk_register   — FMEA items with severity/occurrence/detection/RPN
    open_questions  — Unanswered critical questions
    observer_directives — Per-agent directives from observer
    round_history   — Per-round summary (score, key changes)
"""

import time
import threading
from typing import Any, Callable, Optional
from config.domains import DOMAINS


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

class BlackboardEntry:
    """A single entry on the blackboard."""
    __slots__ = ("value", "source_agent", "round_num", "timestamp", "confidence")

    def __init__(self, value: Any, source_agent: str, round_num: int,
                 confidence: str = "MEDIUM"):
        self.value = value
        self.source_agent = source_agent
        self.round_num = round_num
        self.timestamp = time.time()
        self.confidence = confidence  # HIGH / MEDIUM / LOW


# Domain key → English name mapping (for flag routing)
_DOMAIN_KEY_TO_NAME = {}
_DOMAIN_NAME_TO_KEY = {}
for _k, (_slug, _name) in DOMAINS.items():
    _DOMAIN_KEY_TO_NAME[_slug] = _name
    _DOMAIN_NAME_TO_KEY[_name.lower()] = _slug
    # Also map slug itself
    _DOMAIN_NAME_TO_KEY[_slug] = _slug


def _normalize_domain(raw: str) -> str:
    """Normalize a domain reference to its key (slug)."""
    raw_lower = raw.strip().lower()
    if raw_lower in _DOMAIN_NAME_TO_KEY:
        return _DOMAIN_NAME_TO_KEY[raw_lower]
    # Fuzzy: check if raw_lower is substring of any known name
    for name, key in _DOMAIN_NAME_TO_KEY.items():
        if raw_lower in name or name in raw_lower:
            return key
    return raw_lower


# ═══════════════════════════════════════════════════════════════
# BLACKBOARD CLASS
# ═══════════════════════════════════════════════════════════════

class Blackboard:
    """
    Thread-safe structured analysis state.

    All mutations go through write() which acquires a lock.
    Read operations are lock-free (Python GIL protects dict reads).
    """

    def __init__(self):
        self._lock = threading.Lock()

        # ── Sections ────────────────────────────────────────────
        # parameters: {param_name: [BlackboardEntry, ...]}
        # Multiple entries per param track changes across rounds/agents
        self.parameters: dict[str, list[BlackboardEntry]] = {}

        # conflicts: [{"id", "agent_a", "claim_a", "agent_b", "claim_b",
        #              "domain", "round", "status": "open"|"resolved",
        #              "resolution": str}]
        self.conflicts: list[dict] = []

        # assumptions: [{"id", "agent", "type", "text"/"detail",
        #                "impact", "explicit", "validated", "round"}]
        self.assumptions: list[dict] = []

        # cross_domain_flags: {target_domain_key: [{"from", "issue", "round"}]}
        self.cross_domain_flags: dict[str, list[dict]] = {}

        # risk_register: [{"component", "severity", "occurrence",
        #                   "detection", "rpn", "agent", "round"}]
        self.risk_register: list[dict] = []

        # open_questions: [{"question", "source", "priority", "round"}]
        self.open_questions: list[dict] = []

        # observer_directives: {agent_key: {"action", "detail", "round", "addressed"}}
        # Only latest directive per agent is kept
        self.observer_directives: dict[str, dict] = {}

        # round_history: [{"round", "score", "key_changes", "fixed_items", "new_issues"}]
        self.round_history: list[dict] = []

    # ─────────────────────────────────────────────────────────
    # WRITE — thread-safe mutation
    # ─────────────────────────────────────────────────────────

    def write(self, section: str, data: Any, source_agent: str, round_num: int):
        """Write data to a blackboard section. Thread-safe."""
        with self._lock:
            if section == "parameters":
                self._write_parameter(data, source_agent, round_num)
            elif section == "conflicts":
                self._write_conflict(data, source_agent, round_num)
            elif section == "assumptions":
                self._write_assumption(data, source_agent, round_num)
            elif section == "cross_domain_flags":
                self._write_flag(data, source_agent, round_num)
            elif section == "risk_register":
                self._write_risk(data, source_agent, round_num)
            elif section == "open_questions":
                self._write_question(data, source_agent, round_num)
            elif section == "observer_directives":
                self._write_directive(data, source_agent, round_num)
            elif section == "round_history":
                self._write_round(data, source_agent, round_num)

    def _write_parameter(self, data: dict, source: str, rnd: int):
        name = data.get("name", "").lower().strip()
        if not name:
            return
        entry = BlackboardEntry(
            value=f"{data.get('value', '')} {data.get('unit', '')}".strip(),
            source_agent=source,
            round_num=rnd,
            confidence=data.get("confidence", "MEDIUM"),
        )
        entry.value = {"raw": entry.value, "context": data.get("context", "")}
        self.parameters.setdefault(name, []).append(entry)

    def _write_conflict(self, data: dict, source: str, rnd: int):
        conflict = {
            "id": len(self.conflicts) + 1,
            "agent_a": data.get("agent", source),
            "claim_a": data.get("claimed", ""),
            "agent_b": "",
            "claim_b": data.get("expected", ""),
            "domain": data.get("domain", ""),
            "round": rnd,
            "status": "open",
            "resolution": "",
            "impact": data.get("impact", "MEDIUM"),
            "source": source,
        }
        self.conflicts.append(conflict)

    def _write_assumption(self, data: dict, source: str, rnd: int):
        assumption = {
            "id": len(self.assumptions) + 1,
            "agent": data.get("agent", source),
            "type": data.get("type", "b"),
            "text": data.get("text", data.get("detail", "")),
            "impact": data.get("impact", "MEDIUM"),
            "explicit": data.get("explicit", True),
            "validated": data.get("validated", False),
            "needs_validation": data.get("needs_validation", False),
            "round": rnd,
        }
        self.assumptions.append(assumption)

    def _write_flag(self, data: dict, source: str, rnd: int):
        target = _normalize_domain(data.get("target_domain", ""))
        if not target:
            return
        flag = {
            "from": source,
            "issue": data.get("issue", ""),
            "round": rnd,
        }
        self.cross_domain_flags.setdefault(target, []).append(flag)

    def _write_risk(self, data: dict, source: str, rnd: int):
        risk = {
            "component": data.get("component", "Unknown"),
            "severity": data.get("severity", 0),
            "occurrence": data.get("occurrence", 0),
            "detection": data.get("detection", 0),
            "rpn": data.get("rpn", 0),
            "agent": source,
            "round": rnd,
        }
        self.risk_register.append(risk)

    def _write_question(self, data: dict, source: str, rnd: int):
        q = {
            "question": data.get("question", str(data)),
            "source": source,
            "priority": data.get("priority", "MEDIUM"),
            "round": rnd,
        }
        self.open_questions.append(q)

    def _write_directive(self, data: dict, source: str, rnd: int):
        agent = data.get("agent", "")
        if not agent:
            return
        self.observer_directives[agent] = {
            "action": data.get("action", ""),
            "detail": data.get("detail", ""),
            "round": rnd,
            "addressed": False,
        }

    def _write_round(self, data: dict, source: str, rnd: int):
        # Check if round already exists
        for entry in self.round_history:
            if entry["round"] == rnd:
                entry.update({
                    "score": data.get("score", entry.get("score", 0)),
                })
                return
        self.round_history.append({
            "round": rnd,
            "score": data.get("score", 0),
            "key_changes": [],
            "fixed_items": [],
            "new_issues": [],
        })

    # ─────────────────────────────────────────────────────────
    # RESOLVE CONFLICTS
    # ─────────────────────────────────────────────────────────

    def resolve_conflicts(self, resolutions: list[dict]):
        """Mark conflicts as resolved based on conflict resolution agent output."""
        with self._lock:
            for res in resolutions:
                # Try to match by index or content
                idx = res.get("conflict_id", 0) - 1
                if 0 <= idx < len(self.conflicts):
                    self.conflicts[idx]["status"] = "resolved"
                    self.conflicts[idx]["resolution"] = res.get("resolution", "")

    def mark_directive_addressed(self, agent_key: str):
        """Mark an observer directive as addressed after round 2+ output."""
        with self._lock:
            if agent_key in self.observer_directives:
                self.observer_directives[agent_key]["addressed"] = True

    # ─────────────────────────────────────────────────────────
    # READ — filtered access
    # ─────────────────────────────────────────────────────────

    def read(self, section: str, filter_fn: Optional[Callable] = None) -> list:
        """Read entries from a section, optionally filtered."""
        data = getattr(self, section, [])
        if isinstance(data, dict):
            # Flatten dict sections
            if section == "parameters":
                items = []
                for name, entries in data.items():
                    for e in entries:
                        items.append({"name": name, "entry": e})
                data = items
            elif section == "cross_domain_flags":
                items = []
                for target, flags in data.items():
                    for f in flags:
                        items.append({"target": target, **f})
                data = items
            elif section == "observer_directives":
                data = [{"agent": k, **v} for k, v in data.items()]
        if filter_fn:
            data = [d for d in data if filter_fn(d)]
        return data

    # ─────────────────────────────────────────────────────────
    # CONTEXT INJECTION — per agent type
    # ─────────────────────────────────────────────────────────

    def get_context_for(self, agent_key: str, round_num: int) -> str:
        """
        Return ONLY relevant blackboard sections as formatted text.

        Agent type → relevant sections:
        - Domain agents (_a/_b): cross_domain_flags for their domain +
          observer_directives for them + round diff
        - capraz_dogrulama: parameters table + open conflicts
        - varsayim_belirsizlik: assumptions list + conflict assumptions
        - gozlemci: full summary (all sections)
        - sentez / final_rapor: to_summary()
        - risk_guvenilirlik: parameters + existing risks
        - celisiki_cozum: open conflicts + observer conflicts
        """
        parts = []

        if agent_key.endswith("_a") or agent_key.endswith("_b"):
            parts.append(self._context_for_domain(agent_key, round_num))
        elif agent_key == "capraz_dogrulama":
            parts.append(self._context_for_crossval(round_num))
        elif agent_key == "varsayim_belirsizlik":
            parts.append(self._context_for_assumption(round_num))
        elif agent_key == "gozlemci":
            parts.append(self._context_for_observer(round_num))
        elif agent_key in ("sentez", "final_rapor"):
            parts.append(self.to_summary())
        elif agent_key == "risk_guvenilirlik":
            parts.append(self._context_for_risk(round_num))
        elif agent_key == "celisiki_cozum":
            parts.append(self._context_for_conflict_resolution(round_num))
        else:
            # Generic: just round history
            parts.append(self._format_round_history())

        text = "\n".join(p for p in parts if p)
        return f"BLACKBOARD STATE (Round {round_num}):\n{text}" if text else ""

    def _context_for_domain(self, agent_key: str, round_num: int) -> str:
        """Domain agents get: flags targeting them + observer directives + diff."""
        parts = []

        # Extract domain key from agent key (e.g., "yanma_a" → "yanma")
        domain_key = agent_key.rsplit("_", 1)[0]

        # Cross-domain flags targeting this domain
        flags = self.cross_domain_flags.get(domain_key, [])
        if flags:
            parts.append("CROSS-DOMAIN FLAGS FOR YOUR DOMAIN:")
            for f in flags:
                parts.append(f"  - From {f['from']} (Round {f['round']}): \"{f['issue']}\"")
            parts.append("  → Address each flag explicitly in your analysis.")

        # Observer directives for this agent
        directive = self.observer_directives.get(agent_key)
        if directive and not directive["addressed"]:
            parts.append(f"\nOBSERVER DIRECTIVE FOR YOU ({directive['action']}):")
            parts.append(f"  {directive['detail']}")
            parts.append("  → You MUST address this correction and confirm the fix.")

        # Parameter diff from last round
        if round_num > 1:
            diff_text = self.diff(round_num - 1, round_num)
            if diff_text:
                parts.append(f"\n{diff_text}")

        # Convergence info
        if len(self.round_history) >= 2:
            scores = [r["score"] for r in self.round_history if r["score"]]
            if len(scores) >= 2:
                trend = "improving" if scores[-1] > scores[-2] else "declining"
                parts.append(f"\nQuality trend: {trend} ({scores[-2]} → {scores[-1]})")

        return "\n".join(parts)

    def _context_for_crossval(self, round_num: int) -> str:
        """Cross-validator gets: parameter table + open conflicts."""
        parts = ["PARAMETER TABLE FOR VALIDATION:"]

        if self.parameters:
            for name, entries in self.parameters.items():
                # Show latest entry per agent
                latest = {}
                for e in entries:
                    latest[e.source_agent] = e
                for agent, entry in latest.items():
                    val = entry.value
                    raw = val["raw"] if isinstance(val, dict) else str(val)
                    parts.append(f"  {name}: {raw} (from {agent}, R{entry.round_num})")
        else:
            parts.append("  (no parameters extracted yet)")

        # Open conflicts for reference
        open_conflicts = [c for c in self.conflicts if c["status"] == "open"]
        if open_conflicts:
            parts.append("\nOPEN CONFLICTS:")
            for c in open_conflicts[:10]:
                parts.append(f"  #{c['id']}: {c['claim_a']} vs {c['claim_b']} [{c['impact']}]")

        return "\n".join(parts)

    def _context_for_assumption(self, round_num: int) -> str:
        """Assumption inspector gets: assumptions list + conflicts."""
        parts = ["KNOWN ASSUMPTIONS:"]

        if self.assumptions:
            for a in self.assumptions:
                status = "VALIDATED" if a["validated"] else "UNVALIDATED"
                parts.append(
                    f"  [{a['impact']}] {a['text'][:100]} "
                    f"(from {a['agent']}, type={a['type']}, {status})"
                )
        else:
            parts.append("  (no assumptions extracted yet)")

        # Conflict assumptions from previous assessments
        conflicts = [c for c in self.conflicts if c["status"] == "open"]
        if conflicts:
            parts.append("\nUNRESOLVED PARAMETER CONFLICTS:")
            for c in conflicts[:5]:
                parts.append(f"  {c['claim_a']} vs {c['claim_b']}")

        return "\n".join(parts)

    def _context_for_observer(self, round_num: int) -> str:
        """Observer gets: full summary of all sections."""
        parts = [self.to_summary()]

        # Add directive tracking
        if self.observer_directives:
            parts.append("\nDIRECTIVE STATUS:")
            for agent, d in self.observer_directives.items():
                status = "ADDRESSED" if d["addressed"] else "PENDING"
                parts.append(f"  {agent}: {d['action']} — {status}")

        return "\n".join(parts)

    def _context_for_risk(self, round_num: int) -> str:
        """Risk agent gets: parameters + existing risks."""
        parts = []

        # Key parameters (critical for FMEA)
        if self.parameters:
            parts.append("KEY PARAMETERS:")
            for name, entries in list(self.parameters.items())[:20]:
                latest = entries[-1]
                val = latest.value
                raw = val["raw"] if isinstance(val, dict) else str(val)
                parts.append(f"  {name}: {raw}")

        # Existing risk items (to avoid duplication)
        if self.risk_register:
            parts.append("\nPREVIOUS RISK ITEMS (avoid duplication):")
            for r in self.risk_register:
                parts.append(f"  {r['component']}: RPN={r['rpn']} (R{r['round']})")

        return "\n".join(parts)

    def _context_for_conflict_resolution(self, round_num: int) -> str:
        """Conflict resolution gets: open conflicts + observer conflicts."""
        parts = []

        open_conflicts = [c for c in self.conflicts if c["status"] == "open"]
        if open_conflicts:
            parts.append("OPEN CONFLICTS TO RESOLVE:")
            for c in open_conflicts:
                parts.append(
                    f"  #{c['id']}: {c['agent_a']} claims \"{c['claim_a']}\" "
                    f"vs \"{c['claim_b']}\" [{c['impact']}]"
                )

        return "\n".join(parts)

    # ─────────────────────────────────────────────────────────
    # DIFF — round-over-round changes
    # ─────────────────────────────────────────────────────────

    def diff(self, round_a: int, round_b: int) -> str:
        """What changed between two rounds."""
        parts = []

        # Parameter changes
        param_changes = []
        for name, entries in self.parameters.items():
            vals_a = [e for e in entries if e.round_num == round_a]
            vals_b = [e for e in entries if e.round_num == round_b]
            if vals_b and vals_a:
                old_raw = vals_a[-1].value
                new_raw = vals_b[-1].value
                old_val = old_raw["raw"] if isinstance(old_raw, dict) else str(old_raw)
                new_val = new_raw["raw"] if isinstance(new_raw, dict) else str(new_raw)
                if old_val != new_val:
                    param_changes.append(f"  {name}: {old_val} → {new_val}")
            elif vals_b and not vals_a:
                new_raw = vals_b[-1].value
                new_val = new_raw["raw"] if isinstance(new_raw, dict) else str(new_raw)
                param_changes.append(f"  {name}: NEW = {new_val}")

        if param_changes:
            parts.append("PARAMETER CHANGES:")
            parts.extend(param_changes[:15])

        # Resolved conflicts
        newly_resolved = [
            c for c in self.conflicts
            if c["status"] == "resolved" and c.get("round", 0) <= round_a
        ]
        if newly_resolved:
            parts.append("NEWLY RESOLVED CONFLICTS:")
            for c in newly_resolved[:5]:
                parts.append(f"  #{c['id']}: {c['resolution'][:80]}")

        # Score progression
        scores_a = [r["score"] for r in self.round_history if r["round"] == round_a]
        scores_b = [r["score"] for r in self.round_history if r["round"] == round_b]
        if scores_a and scores_b:
            delta = scores_b[0] - scores_a[0]
            trend = f"+{delta}" if delta >= 0 else str(delta)
            parts.append(f"SCORE: {scores_a[0]} → {scores_b[0]} ({trend})")

        return "\n".join(parts) if parts else ""

    # ─────────────────────────────────────────────────────────
    # CONVERGENCE CHECK
    # ─────────────────────────────────────────────────────────

    def check_convergence(self) -> dict:
        """
        Analyze parameter convergence across rounds.

        Returns:
            {
                "converging": [param_names],
                "oscillating": [param_names],
                "stable": [param_names],
                "score_trend": "improving" | "declining" | "stable"
            }
        """
        result = {"converging": [], "oscillating": [], "stable": [], "score_trend": "stable"}

        for name, entries in self.parameters.items():
            if len(entries) < 2:
                continue
            # Get values per round
            rounds = sorted(set(e.round_num for e in entries))
            if len(rounds) < 2:
                continue

            # Check if numeric values are converging
            round_vals = {}
            for e in entries:
                raw = e.value["raw"] if isinstance(e.value, dict) else str(e.value)
                # Extract first number
                import re as _re
                num_match = _re.search(r'(\d+\.?\d*)', raw)
                if num_match:
                    round_vals.setdefault(e.round_num, []).append(float(num_match.group(1)))

            if len(round_vals) >= 2:
                sorted_rounds = sorted(round_vals.keys())
                deltas = []
                for i in range(1, len(sorted_rounds)):
                    prev_avg = sum(round_vals[sorted_rounds[i-1]]) / len(round_vals[sorted_rounds[i-1]])
                    curr_avg = sum(round_vals[sorted_rounds[i]]) / len(round_vals[sorted_rounds[i]])
                    if prev_avg != 0:
                        deltas.append(abs(curr_avg - prev_avg) / abs(prev_avg))

                if deltas:
                    if all(d < 0.05 for d in deltas):
                        result["stable"].append(name)
                    elif len(deltas) >= 2 and deltas[-1] < deltas[-2]:
                        result["converging"].append(name)
                    elif len(deltas) >= 2 and deltas[-1] > deltas[-2] * 1.5:
                        result["oscillating"].append(name)

        # Score trend
        scores = [r["score"] for r in self.round_history if r["score"]]
        if len(scores) >= 2:
            if scores[-1] > scores[-2]:
                result["score_trend"] = "improving"
            elif scores[-1] < scores[-2]:
                result["score_trend"] = "declining"

        return result

    # ─────────────────────────────────────────────────────────
    # ASSUMPTION CONSISTENCY CHECK
    # ─────────────────────────────────────────────────────────

    def find_conflicting_assumptions(self) -> list[dict]:
        """
        Cross-reference assumptions between agents.
        Returns list of potential conflicts.
        """
        conflicts = []
        # Group assumptions by approximate topic (simple word overlap)
        from collections import defaultdict
        by_keyword = defaultdict(list)

        for a in self.assumptions:
            text = a.get("text", "").lower()
            # Extract key terms (words > 3 chars)
            words = set(w for w in text.split() if len(w) > 3)
            for w in words:
                by_keyword[w].append(a)

        # Find assumptions from different agents sharing keywords
        checked = set()
        for keyword, group in by_keyword.items():
            if len(group) < 2:
                continue
            agents = set(a["agent"] for a in group)
            if len(agents) < 2:
                continue

            pair_key = tuple(sorted(agents))
            if pair_key in checked:
                continue
            checked.add(pair_key)

            # Check if they have different impact or contradictory text
            for i, a1 in enumerate(group):
                for a2 in group[i+1:]:
                    if a1["agent"] != a2["agent"]:
                        conflicts.append({
                            "agent_a": a1["agent"],
                            "assumption_a": a1["text"][:100],
                            "agent_b": a2["agent"],
                            "assumption_b": a2["text"][:100],
                            "shared_topic": keyword,
                        })
                        break  # One conflict per pair is enough

        return conflicts[:10]  # Cap at 10

    # ─────────────────────────────────────────────────────────
    # SUMMARY — compact text representation
    # ─────────────────────────────────────────────────────────

    def to_summary(self) -> str:
        """Compact text summary for synthesis and final report."""
        parts = []

        # ── Parameters ──────────────────────────────────────
        if self.parameters:
            parts.append("EXTRACTED PARAMETERS:")
            for name, entries in sorted(self.parameters.items()):
                latest = entries[-1]
                val = latest.value
                raw = val["raw"] if isinstance(val, dict) else str(val)
                parts.append(
                    f"  {name}: {raw} "
                    f"[{latest.source_agent}, R{latest.round_num}, {latest.confidence}]"
                )
        parts.append(f"  Total: {sum(len(v) for v in self.parameters.values())} entries, "
                     f"{len(self.parameters)} unique parameters")

        # ── Conflicts ───────────────────────────────────────
        open_c = sum(1 for c in self.conflicts if c["status"] == "open")
        resolved_c = sum(1 for c in self.conflicts if c["status"] == "resolved")
        parts.append(f"\nCONFLICTS: {open_c} open, {resolved_c} resolved")
        for c in self.conflicts[:5]:
            status = "OPEN" if c["status"] == "open" else "RESOLVED"
            parts.append(f"  [{status}] #{c['id']}: {c['claim_a'][:60]} vs {c['claim_b'][:60]}")

        # ── Assumptions ─────────────────────────────────────
        high_impact = [a for a in self.assumptions if a["impact"] in ("HIGH", "CRITICAL")]
        parts.append(f"\nASSUMPTIONS: {len(self.assumptions)} total, {len(high_impact)} high-impact")
        for a in high_impact[:5]:
            parts.append(f"  [{a['impact']}] {a['text'][:80]} ({a['agent']})")

        # ── Cross-domain flags ──────────────────────────────
        total_flags = sum(len(v) for v in self.cross_domain_flags.values())
        if total_flags:
            parts.append(f"\nCROSS-DOMAIN FLAGS: {total_flags} total")
            for target, flags in self.cross_domain_flags.items():
                for f in flags:
                    parts.append(f"  → {target}: \"{f['issue'][:60]}\" (from {f['from']})")

        # ── Risk register ───────────────────────────────────
        if self.risk_register:
            critical = [r for r in self.risk_register if r["rpn"] >= 200 or r.get("severity", 0) >= 9]
            parts.append(f"\nRISK REGISTER: {len(self.risk_register)} items, "
                         f"{len(critical)} critical (RPN≥200)")
            for r in sorted(self.risk_register, key=lambda x: x["rpn"], reverse=True)[:5]:
                parts.append(f"  RPN={r['rpn']}: {r['component'][:50]}")

        # ── Quality progression ─────────────────────────────
        if self.round_history:
            scores = [(r["round"], r["score"]) for r in self.round_history if r["score"]]
            if scores:
                score_str = " → ".join(f"R{rnd}:{score}" for rnd, score in scores)
                parts.append(f"\nQUALITY PROGRESSION: {score_str}")
                convergence = self.check_convergence()
                if convergence["oscillating"]:
                    parts.append(f"  ⚠ OSCILLATING: {', '.join(convergence['oscillating'][:5])}")
                if convergence["converging"]:
                    parts.append(f"  ✓ CONVERGING: {', '.join(convergence['converging'][:5])}")

        # ── Unaddressed directives ──────────────────────────
        unaddressed = [
            (a, d) for a, d in self.observer_directives.items()
            if not d["addressed"] and d["action"] in ("FIX", "ADD")
        ]
        if unaddressed:
            parts.append(f"\nUNADDRESSED DIRECTIVES: {len(unaddressed)}")
            for agent, d in unaddressed:
                parts.append(f"  {agent}: {d['action']} — {d['detail'][:60]}")

        return "\n".join(parts)

    # ─────────────────────────────────────────────────────────
    # RAG METADATA
    # ─────────────────────────────────────────────────────────

    def to_rag_metadata(self) -> dict:
        """Structured data for RAG storage."""
        return {
            "parameter_count": len(self.parameters),
            "conflict_count": len(self.conflicts),
            "open_conflict_count": sum(1 for c in self.conflicts if c["status"] == "open"),
            "assumption_count": len(self.assumptions),
            "risk_count": len(self.risk_register),
            "max_rpn": max((r["rpn"] for r in self.risk_register), default=0),
            "flag_count": sum(len(v) for v in self.cross_domain_flags.values()),
            "final_score": self.round_history[-1]["score"] if self.round_history else 0,
            "rounds_completed": len(self.round_history),
            "convergence": self.check_convergence().get("score_trend", "unknown"),
        }

    def get_parameter_table(self) -> str:
        """Structured parameter data for RAG."""
        if not self.parameters:
            return ""
        lines = ["PARAMETER TABLE:"]
        for name, entries in sorted(self.parameters.items()):
            latest = entries[-1]
            val = latest.value
            raw = val["raw"] if isinstance(val, dict) else str(val)
            lines.append(f"  {name}: {raw} [{latest.source_agent}]")
        return "\n".join(lines)
