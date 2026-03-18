"""
tools/registry.py
Central registry mapping domain keys to available solver tools.
"""
from __future__ import annotations

from typing import Optional

from tools.base import BaseToolWrapper

# Domain key -> ordered list of tool names (first is highest priority)
DOMAIN_TOOLS: dict[str, list[str]] = {
    "yanma":           ["cantera"],
    "termodinamik":    ["cantera", "coolprop"],
    "termal":          ["fenics", "coolprop"],
    "yapisal":         ["fenics", "opensees"],
    "dinamik":         ["fenics", "opensees"],
    "aerodinamik":     ["su2", "openfoam"],
    "akiskan":         ["openfoam", "fenics"],
    "kontrol":         ["python_control"],
    "malzeme":         ["materials_project", "matminer"],
    "elektrik":        ["pyspice"],
    "robotik":         ["pybullet"],
    "enerji":          ["pypsa"],
    "cevre":           ["brightway2"],
    "denizcilik":      ["capytaine"],
    "kimya":           ["dwsim", "cantera"],
    "optik":           ["rayoptics", "meep"],
    "nukleer":         ["openmc"],
    "biyomedikal":     ["opensim", "febio"],
    "uzay":            ["openrocket", "su2"],
    "insaat":          ["opensees", "fenics"],
    "guvenilirlik":    ["reliability"],
    "otomotiv":        ["sumo"],
    "mekanik_tasarim": ["fenics"],
    "hidrolik":        ["openmodelica"],
    "sistem":          ["openmodelica"],
    "uretim":          ["freecad"],
    "savunma":         ["python_control", "openrocket"],
    "yazilim":         [],
}

_REGISTRY: dict[str, BaseToolWrapper] = {}
_AVAILABILITY_CACHE: dict[str, bool]  = {}


def register(tool: BaseToolWrapper) -> None:
    """Register a solver tool in the global registry."""
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> Optional[BaseToolWrapper]:
    """Return a registered tool by name, or None."""
    return _REGISTRY.get(name)


def get_available_tools_for_domain(domain: str) -> list[BaseToolWrapper]:
    """
    Return all installed and functional tools for the given domain.
    Silently skips tools that are not installed.
    Availability is checked once and cached for the application lifetime.
    """
    available = []
    for name in DOMAIN_TOOLS.get(domain, []):
        tool = _REGISTRY.get(name)
        if tool is None:
            continue
        if name not in _AVAILABILITY_CACHE:
            _AVAILABILITY_CACHE[name] = tool.is_available()
        if _AVAILABILITY_CACHE[name]:
            available.append(tool)
    return available


def get_anthropic_tools_for_domain(domain: str) -> list[dict]:
    """Return Anthropic tool definitions for all available tools in a domain."""
    return [t.get_anthropic_tool_definition()
            for t in get_available_tools_for_domain(domain)]


def availability_report() -> dict:
    """Return installation status for all registered tools."""
    return {
        name: {
            "available": tool.is_available(),
            "tier":      tool.tier,
            "domains":   tool.domains,
        }
        for name, tool in _REGISTRY.items()
    }
