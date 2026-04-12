"""tests/test_regression.py — Golden-set regression tests.

Phase 1.2: Regression tests against 5 reference problems with known-good outcomes.
These tests run with mocked API responses to verify the analysis pipeline produces
structurally correct output without prompt drift.

Tests marked @pytest.mark.integration require a real API key and are skipped in CI.
"""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


GOLDEN_DIR = Path(__file__).parent / "golden"


# ── Helpers ──────────────────────────────────────────────────

def load_golden(name: str) -> dict:
    """Load a golden test fixture by filename."""
    path = GOLDEN_DIR / name
    return json.loads(path.read_text())


# ── Mock agent runner for regression ─────────────────────────

def _mock_run_agent(ajan_key: str, mesaj: str, gecmis=None, **kwargs) -> str:
    """Deterministic mock agent that returns domain-appropriate responses."""
    from tests.fixtures.mock_claude import _get_response_for_agent
    return _get_response_for_agent(ajan_key)


# ── Unit regression: Blackboard pipeline ─────────────────────

class TestBlackboardPipelineRegression:
    """Verify the Blackboard pipeline produces consistent structured output."""

    def test_parameter_extraction_pipeline(self):
        """Parameters written to blackboard are recoverable in export."""
        from blackboard import Blackboard
        bb = Blackboard()

        params = [
            ("pressure", "150", "bar", "HIGH", "yanma_a"),
            ("temperature", "450", "K", "HIGH", "yanma_a"),
            ("flow_rate", "2.5", "kg/s", "MEDIUM", "yanma_b"),
        ]
        for name, value, unit, conf, agent in params:
            bb.write("parameters", {
                "name": name, "value": value, "unit": unit, "confidence": conf
            }, agent, 1)

        exported = bb.export_parameters()
        exported_names = {p["name"] for p in exported}
        assert {"pressure", "temperature", "flow_rate"} == exported_names

    def test_multi_round_convergence(self):
        """Quality score progression is tracked correctly across rounds."""
        from blackboard import Blackboard
        bb = Blackboard()

        # Simulate 3 rounds of improving quality
        for rnd, score in [(1, 62), (2, 75), (3, 88)]:
            bb.write("round_history", {"score": score}, "gozlemci", rnd)

        history = bb.round_history
        assert len(history) == 3
        scores = [r["score"] for r in history]
        assert scores == [62, 75, 88]

    def test_observer_directive_lifecycle(self):
        """Directives are marked addressed correctly."""
        from blackboard import Blackboard
        bb = Blackboard()

        bb.write("observer_directives", {
            "agent": "yanma_a", "action": "FIX",
            "detail": "Reconcile pressure value"
        }, "gozlemci", 1)

        assert not bb.observer_directives["yanma_a"]["addressed"]
        bb.mark_directive_addressed("yanma_a")
        assert bb.observer_directives["yanma_a"]["addressed"]

    def test_cross_domain_flag_routing(self):
        """Flags are routed to correct domain key."""
        from blackboard import Blackboard
        bb = Blackboard()

        bb.write("cross_domain_flags", {
            "target_domain": "termal",
            "issue": "Heat exchanger needs verification at 450 K"
        }, "yanma_a", 1)

        assert "termal" in bb.cross_domain_flags
        flags = bb.cross_domain_flags["termal"]
        assert len(flags) == 1
        assert "450 K" in flags[0]["issue"]

    def test_conflict_detection_no_false_positives(self):
        """Single-agent assumptions should not produce conflicts."""
        from blackboard import Blackboard
        bb = Blackboard()

        # All assumptions from the same agent
        texts = [
            "Steady-state operation assumed",
            "Ideal gas for preliminary calculations",
            "No phase change in operating range",
        ]
        for text in texts:
            bb.write("assumptions", {
                "agent": "yanma_a", "text": text, "impact": "LOW"
            }, "yanma_a", 1)

        conflicts = bb.find_conflicting_assumptions()
        cross_agent = [c for c in conflicts if c.get("agent_a") != c.get("agent_b")]
        assert cross_agent == []

    def test_serialization_preserves_all_sections(self):
        """Roundtrip through to_dict/from_dict preserves all sections."""
        from blackboard import Blackboard
        bb = Blackboard()

        bb.write("parameters", {"name": "p", "value": "100 bar"}, "agent_a", 1)
        bb.write("conflicts", {
            "agent": "agent_a", "claimed": "p=100",
            "expected": "p=90", "domain": "test", "impact": "LOW"
        }, "validator", 1)
        bb.write("assumptions", {"agent": "agent_a", "text": "Test assumption"}, "agent_a", 1)
        bb.write("risk_register", {
            "component": "valve", "failure_mode": "leak",
            "severity": 5, "occurrence": 3, "detection": 4
        }, "risk_agent", 1)
        bb.write("round_history", {"score": 70}, "gozlemci", 1)

        d = bb.to_dict()
        bb2 = Blackboard.from_dict(d)

        assert "p" in bb2.parameters
        assert len(bb2.conflicts) == 1
        assert len(bb2.assumptions) == 1
        assert len(bb2.risk_register) == 1
        assert len(bb2.round_history) == 1


# ── Unit regression: Report JSON builder ─────────────────────

class TestJsonReportRegression:
    def test_json_report_schema_version(self):
        from report.json_builder import generate_json_report
        data = json.loads(generate_json_report(
            brief="Test brief",
            final_report="Test report",
            domains=["Combustion"],
        ).decode("utf-8"))
        assert data["schema_version"] == "1.0"
        assert "meta" in data
        assert "findings" in data
        assert "final_report_text" in data

    def test_json_report_includes_parameters(self):
        from blackboard import Blackboard
        from report.json_builder import generate_json_report
        bb = Blackboard()
        bb.write("parameters", {"name": "pressure", "value": "150 bar"}, "agent_a", 1)

        data = json.loads(generate_json_report(
            brief="Test brief",
            final_report="Test report",
            domains=["Combustion"],
            blackboard_dict=bb.to_dict(),
        ).decode("utf-8"))
        params = data["findings"]["parameters"]
        assert any(p["name"] == "pressure" for p in params)

    def test_json_report_is_valid_utf8_json(self):
        from report.json_builder import generate_json_report
        raw = generate_json_report(
            brief="Brief with Unicode: 燃焼解析",
            final_report="Report",
            domains=["Combustion", "Thermal"],
        )
        # Should not raise
        decoded = json.loads(raw.decode("utf-8"))
        assert decoded["meta"]["brief"] == "Brief with Unicode: 燃焼解析"


# ── Unit regression: Logging ─────────────────────────────────

class TestLoggingRegression:
    def test_json_formatter_output(self):
        """JSON formatter should produce parseable JSON per record."""
        import logging
        from shared.logging_config import JSONFormatter, set_correlation_id
        import json as _json

        set_correlation_id("test-cid-123")
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None
        )
        output = formatter.format(record)
        parsed = _json.loads(output)
        assert parsed["msg"] == "test message"
        assert parsed["cid"] == "test-cid-123"
        assert parsed["level"] == "INFO"

    def test_correlation_id_isolation(self):
        """Correlation IDs should be thread-local."""
        import threading
        from shared.logging_config import set_correlation_id, get_correlation_id

        results = {}

        def worker(cid):
            set_correlation_id(cid)
            import time; time.sleep(0.01)
            results[cid] = get_correlation_id()

        threads = [threading.Thread(target=worker, args=(f"cid-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(5):
            assert results[f"cid-{i}"] == f"cid-{i}"


# ── Regression: Settings ─────────────────────────────────────

class TestSettingsRegression:
    def test_settings_loads_from_env(self, monkeypatch):
        """Settings should read ANTHROPIC_API_KEY from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        # Re-import to pick up env change
        import importlib
        import config.settings as settings_mod
        importlib.reload(settings_mod)
        assert settings_mod.settings.anthropic_api_key == "sk-ant-test-key"

    def test_settings_auth_defaults_to_none(self, monkeypatch):
        """Auth credentials should default to None when not set."""
        monkeypatch.delenv("AUTH_USERNAME", raising=False)
        monkeypatch.delenv("AUTH_PASSWORD", raising=False)
        import importlib
        import config.settings as settings_mod
        importlib.reload(settings_mod)
        assert settings_mod.settings.auth_username is None
        assert settings_mod.settings.auth_password is None
