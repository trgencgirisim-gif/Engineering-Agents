"""tests/conftest.py — Shared pytest fixtures and configuration.

Phase 1.1: Pytest harness with mocked Anthropic client.
"""

import os
import sys
import pytest

# Ensure repo root is on sys.path so imports work without install
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set a dummy API key so modules that import it at load time don't error
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy-key-for-tests")


# ── Blackboard fixture ───────────────────────────────────────

@pytest.fixture
def empty_blackboard():
    """Fresh Blackboard with no data."""
    from blackboard import Blackboard
    return Blackboard()


@pytest.fixture
def populated_blackboard():
    """Blackboard pre-loaded with representative engineering data."""
    from blackboard import Blackboard
    bb = Blackboard()

    # Parameters from two agents
    bb.write("parameters", {
        "name": "pressure", "value": "150", "unit": "bar", "confidence": "HIGH",
        "context": "design spec"
    }, "yanma_a", 1)
    bb.write("parameters", {
        "name": "pressure", "value": "145", "unit": "bar", "confidence": "MEDIUM",
        "context": "field measurement"
    }, "yanma_b", 1)
    bb.write("parameters", {
        "name": "temperature", "value": "450", "unit": "K", "confidence": "HIGH",
        "context": "operating conditions"
    }, "yanma_a", 1)

    # Conflict
    bb.write("conflicts", {
        "agent": "yanma_a", "claimed": "pressure = 150 bar",
        "expected": "145 bar", "domain": "yanma", "impact": "MEDIUM"
    }, "capraz_dogrulama", 1)

    # Assumptions
    bb.write("assumptions", {
        "agent": "yanma_a", "type": "b",
        "text": "Ideal gas behaviour assumed for preliminary calculations",
        "impact": "MEDIUM", "explicit": True
    }, "yanma_a", 1)
    bb.write("assumptions", {
        "agent": "yanma_b", "type": "b",
        "text": "10% safety margin applied to all pressure calculations",
        "impact": "HIGH", "explicit": True
    }, "yanma_b", 1)

    # Round history
    bb.write("round_history", {"score": 72}, "gozlemci", 1)

    return bb


@pytest.fixture
def mock_anthropic_client():
    """Mocked Anthropic client — no network calls."""
    from tests.fixtures.mock_claude import make_mock_client
    return make_mock_client()


@pytest.fixture
def mock_response_factory():
    """Factory for creating mock API responses with custom text."""
    from tests.fixtures.mock_claude import make_mock_response
    return make_mock_response


# ── Markers ──────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow (skipped in CI fast mode)")
    config.addinivalue_line("markers", "integration: mark test as requiring real API access")
