"""
tools/base.py
Base classes for all solver wrappers.
Every wrapper inherits from BaseToolWrapper and returns ToolResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    """Standardised container for solver output."""

    success:     bool
    solver:      str
    confidence:  str                    # "HIGH" | "MEDIUM" | "LOW"
    data:        dict                   # {"sigma_max_MPa": 47.3, ...}
    units:       dict                   # {"sigma_max_MPa": "MPa", ...}
    raw_output:  str                    # Raw solver stdout / log (for debugging)
    error:       Optional[str] = None
    warnings:    list[str]   = field(default_factory=list)
    assumptions: list[str]   = field(default_factory=list)

    def to_agent_text(self) -> str:
        """
        Format solver output for injection into the LLM conversation.
        The agent reads this block and incorporates verified numbers into its report.
        """
        if not self.success:
            return (
                f"[SOLVER_RESULT — {self.solver.upper()}]\n"
                f"STATUS: FAILED\n"
                f"ERROR: {self.error}\n"
                f"INSTRUCTION: Solver unavailable. Continue with engineering estimate "
                f"and mark all estimated values with [ASSUMPTION].\n"
                f"[/SOLVER_RESULT]"
            )

        lines = [
            f"[SOLVER_RESULT — {self.solver.upper()}]",
            f"STATUS: SUCCESS",
            f"CONFIDENCE: {self.confidence}",
            "COMPUTED VALUES:",
        ]
        for key, value in self.data.items():
            unit = self.units.get(key, "")
            formatted = f"{value:.6g}" if isinstance(value, float) else str(value)
            lines.append(f"  {key} = {formatted} {unit}".rstrip())

        if self.warnings:
            lines.append("WARNINGS:")
            for w in self.warnings:
                lines.append(f"  - {w}")

        if self.assumptions:
            lines.append("SOLVER ASSUMPTIONS:")
            for a in self.assumptions:
                lines.append(f"  [ASSUMPTION] {a}")

        lines += [
            "INSTRUCTION: Use the values above as verified data. "
            f"Tag them as [VERIFIED — {self.solver}] in your report. "
            "Do not produce your own estimates for quantities already computed by the solver.",
            "[/SOLVER_RESULT]",
        ]
        return "\n".join(lines)


class BaseToolWrapper(ABC):
    """Abstract base for all solver wrappers."""

    name:    str        # matches tools.yaml and registry key
    tier:    int        # 1 = open-source, 2 = ANSYS, 3 = MATLAB
    domains: list[str]  # domain keys that can use this tool

    # Anthropic tool_use input schema — every wrapper must define this
    INPUT_SCHEMA: dict = {}

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True only if the solver is installed and functional.
        Must not raise — use try/except internally.
        """
        ...

    @abstractmethod
    def execute(self, inputs: dict) -> ToolResult:
        """
        Run the computation and return a ToolResult.
        Must never raise — catch all exceptions and return success=False.
        inputs: the dict from the Anthropic tool_use block.
        """
        ...

    def get_anthropic_tool_definition(self) -> dict:
        """Return the tool definition for Anthropic messages.create(tools=[...])."""
        return {
            "name":         self.name,
            "description":  self._description(),
            "input_schema": self.INPUT_SCHEMA,
        }

    @abstractmethod
    def _description(self) -> str:
        """
        One-paragraph description used by the LLM to decide when to call this tool.
        State: what it computes, what inputs it needs, and which problem types it suits.
        """
        ...
