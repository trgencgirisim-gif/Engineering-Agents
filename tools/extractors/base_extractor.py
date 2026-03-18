"""tools/extractors/base_extractor.py — Base class for input extractors."""
from __future__ import annotations

from abc import ABC, abstractmethod
import re


class BaseInputExtractor(ABC):
    """
    Parses a natural-language brief and/or LLM response to extract
    structured numeric inputs for a specific solver.
    """

    solver_name: str

    @abstractmethod
    def extract(self, text: str, brief: str = "") -> dict | None:
        """
        text:  LLM intermediate response text (may contain inferred values)
        brief: original problem brief
        Returns: dict ready for solver.execute(inputs), or None if extraction fails.
        """
        ...

    def _find_number(self, text: str, patterns: list[str],
                     default: float | None = None) -> float | None:
        """Search text for numeric values matching any of the given regex patterns."""
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except (ValueError, IndexError):
                    continue
        return default

    def _find_string(self, text: str, patterns: list[str],
                     default: str | None = None) -> str | None:
        """Search text for string values matching any of the given regex patterns."""
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return default
