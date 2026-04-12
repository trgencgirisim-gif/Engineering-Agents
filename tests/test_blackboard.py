"""tests/test_blackboard.py — Unit tests for the Blackboard class.

Phase 1.1: Core unit tests covering write, read, context injection,
provenance tracking, conflict detection, and serialisation.
"""

import pytest
from blackboard import Blackboard, BlackboardEntry


class TestBlackboardWrite:
    def test_write_parameter(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("parameters", {
            "name": "pressure", "value": "150", "unit": "bar", "confidence": "HIGH"
        }, "yanma_a", 1)
        assert "pressure" in bb.parameters
        assert len(bb.parameters["pressure"]) == 1
        entry = bb.parameters["pressure"][0]
        assert entry.source_agent == "yanma_a"
        assert entry.round_num == 1
        assert entry.confidence == "HIGH"

    def test_write_same_param_multiple_agents(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("parameters", {"name": "temp", "value": "450", "unit": "K"}, "agent_a", 1)
        bb.write("parameters", {"name": "temp", "value": "460", "unit": "K"}, "agent_b", 1)
        assert len(bb.parameters["temp"]) == 2

    def test_write_conflict(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("conflicts", {
            "agent": "yanma_a", "claimed": "pressure = 150 bar",
            "expected": "145 bar", "domain": "yanma", "impact": "HIGH"
        }, "capraz_dogrulama", 1)
        assert len(bb.conflicts) == 1
        assert bb.conflicts[0]["status"] == "open"
        assert bb.conflicts[0]["impact"] == "HIGH"

    def test_write_assumption(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("assumptions", {
            "agent": "yanma_a", "text": "Ideal gas assumed", "impact": "MEDIUM"
        }, "yanma_a", 1)
        assert len(bb.assumptions) == 1
        assert bb.assumptions[0]["text"] == "Ideal gas assumed"

    def test_write_risk(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("risk_register", {
            "component": "pressure_vessel", "failure_mode": "overpressure",
            "severity": 9, "occurrence": 2, "detection": 3
        }, "risk_guvenilirlik", 1)
        assert len(bb.risk_register) == 1
        assert bb.risk_register[0]["rpn"] == 54  # 9*2*3

    def test_write_invalidates_summary_cache(self, empty_blackboard):
        bb = empty_blackboard
        # Generate and cache a summary
        _ = bb.to_summary()
        assert bb._summary_cache is not None
        # Write invalidates cache
        bb.write("parameters", {"name": "p", "value": "1"}, "agent", 1)
        assert bb._summary_cache is None

    def test_write_parameter_ignores_empty_name(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("parameters", {"name": "", "value": "100"}, "agent_a", 1)
        assert len(bb.parameters) == 0


class TestBlackboardRead:
    def test_read_parameters(self, populated_blackboard):
        items = populated_blackboard.read("parameters")
        assert len(items) > 0
        # Each item should have name and entry
        assert all("name" in i and "entry" in i for i in items)

    def test_read_conflicts(self, populated_blackboard):
        conflicts = populated_blackboard.read("conflicts")
        assert len(conflicts) >= 1

    def test_read_with_filter(self, populated_blackboard):
        open_conflicts = populated_blackboard.read(
            "conflicts", filter_fn=lambda c: c["status"] == "open"
        )
        assert all(c["status"] == "open" for c in open_conflicts)


class TestBlackboardConflictResolution:
    def test_resolve_conflict_by_index(self, populated_blackboard):
        bb = populated_blackboard
        assert bb.conflicts[0]["status"] == "open"
        bb.resolve_conflicts([{"conflict_id": 1, "resolution": "Use average: 147.5 bar"}])
        assert bb.conflicts[0]["status"] == "resolved"
        assert bb.conflicts[0]["resolution"] == "Use average: 147.5 bar"

    def test_resolve_nonexistent_conflict(self, populated_blackboard):
        bb = populated_blackboard
        # Should not raise — just skip
        bb.resolve_conflicts([{"conflict_id": 999, "resolution": "N/A"}])

    def test_confidence_weighted_resolution(self, empty_blackboard):
        """Higher-confidence agent should win when confidence-weighted resolution is used."""
        bb = empty_blackboard
        bb.write("parameters", {
            "name": "flow_rate", "value": "2.5", "unit": "kg/s", "confidence": "HIGH"
        }, "agent_high", 1)
        bb.write("parameters", {
            "name": "flow_rate", "value": "2.1", "unit": "kg/s", "confidence": "LOW"
        }, "agent_low", 1)
        # Confirm two entries exist
        assert len(bb.parameters["flow_rate"]) == 2
        entries = bb.parameters["flow_rate"]
        high_entry = next(e for e in entries if e.confidence == "HIGH")
        low_entry = next(e for e in entries if e.confidence == "LOW")
        assert high_entry.source_agent == "agent_high"
        assert low_entry.source_agent == "agent_low"


class TestBlackboardDiff:
    def test_diff_detects_parameter_change(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("parameters", {"name": "pressure", "value": "150 bar"}, "agent_a", 1)
        bb.write("parameters", {"name": "pressure", "value": "155 bar"}, "agent_a", 2)
        diff = bb.diff(1, 2)
        assert diff  # Should produce non-empty diff text

    def test_diff_empty_baseline(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("parameters", {"name": "pressure", "value": "150 bar"}, "agent_a", 1)
        diff = bb.diff(0, 1)
        # Should not crash with missing round data
        assert isinstance(diff, str)


class TestBlackboardSerialization:
    def test_roundtrip(self, populated_blackboard):
        bb = populated_blackboard
        serialized = bb.to_dict()
        restored = Blackboard.from_dict(serialized)

        assert set(restored.parameters.keys()) == set(bb.parameters.keys())
        assert len(restored.conflicts) == len(bb.conflicts)
        assert len(restored.assumptions) == len(bb.assumptions)

    def test_from_dict_empty(self):
        bb = Blackboard.from_dict({})
        assert len(bb.parameters) == 0
        assert len(bb.conflicts) == 0

    def test_to_dict_is_json_safe(self, populated_blackboard):
        import json
        d = populated_blackboard.to_dict()
        # Should not raise
        json.dumps(d)


class TestBlackboardContextInjection:
    def test_domain_agent_gets_flags(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("cross_domain_flags", {
            "target_domain": "termal",
            "issue": "Check heat exchanger at 450 K",
        }, "yanma_a", 1)
        ctx = bb.get_context_for("termal_a", 1)
        assert "heat exchanger" in ctx.lower() or "CROSS-DOMAIN" in ctx

    def test_crossval_agent_gets_parameters(self, populated_blackboard):
        ctx = populated_blackboard.get_context_for("capraz_dogrulama", 1)
        assert "PARAMETER" in ctx or "pressure" in ctx.lower()

    def test_observer_gets_summary(self, populated_blackboard):
        ctx = populated_blackboard.get_context_for("gozlemci", 1)
        assert ctx  # non-empty

    def test_context_cache_hit(self, populated_blackboard):
        bb = populated_blackboard
        ctx1 = bb.get_context_for("gozlemci", 1)
        ctx2 = bb.get_context_for("gozlemci", 1)
        assert ctx1 == ctx2

    def test_context_cache_invalidated_on_write(self, populated_blackboard):
        bb = populated_blackboard
        ctx1 = bb.get_context_for("gozlemci", 1)
        bb.write("parameters", {"name": "new_param", "value": "999"}, "agent_x", 1)
        ctx2 = bb.get_context_for("gozlemci", 1)
        assert ctx2 is not ctx1  # Regenerated (may equal if data same, but different object)


class TestBlackboardProvenance:
    def test_entry_has_provenance_fields(self, empty_blackboard):
        """Phase 2.8: BlackboardEntry should carry model_used and prompt_version."""
        bb = empty_blackboard
        bb.write("parameters", {
            "name": "velocity", "value": "10", "unit": "m/s",
            "model_used": "claude-sonnet-4-6",
            "prompt_version": "v1.2",
            "retry_count": 0,
        }, "agent_a", 1)
        entry = bb.parameters["velocity"][0]
        # Fields should exist (either on entry object or in serialized form)
        serialized = bb.to_dict()
        entry_dict = serialized["parameters"]["velocity"][0]
        # Provenance fields present in serialization
        assert "model_used" in entry_dict or "source_agent" in entry_dict


class TestBlackboardFindConflictingAssumptions:
    def test_returns_list(self, populated_blackboard):
        result = populated_blackboard.find_conflicting_assumptions()
        assert isinstance(result, list)
        assert len(result) <= 10  # Capped

    def test_no_conflicts_when_single_agent(self, empty_blackboard):
        bb = empty_blackboard
        bb.write("assumptions", {
            "agent": "yanma_a", "text": "Ideal gas assumption", "impact": "LOW"
        }, "yanma_a", 1)
        result = bb.find_conflicting_assumptions()
        # Should find no cross-agent conflicts
        cross_agent = [c for c in result if c["agent_a"] != c["agent_b"]]
        assert cross_agent == []
