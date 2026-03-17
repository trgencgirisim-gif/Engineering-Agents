"""
tools/ — Solver tool integration package.

Exposes registry functions used by core.py:
  - get_tool(name)
  - get_available_tools_for_domain(domain)
  - get_anthropic_tools_for_domain(domain)
  - register(tool)

Auto-registers all tier1 tools on import.
"""
from tools.registry import (
    register,
    get_tool,
    get_available_tools_for_domain,
    get_anthropic_tools_for_domain,
    availability_report,
)

# ── Auto-register tier1 tools ─────────────────────────────────
from tools.tier1.cantera_tool import CanteraTool
from tools.tier1.coolprop_tool import CoolPropTool
from tools.tier1.fenics_tool import FenicsTool
from tools.tier1.materials_project_tool import MaterialsProjectTool
from tools.tier1.matminer_tool import MatminerTool
from tools.tier1.opensees_tool import OpenSeesTool
from tools.tier1.pybullet_tool import PyBulletTool
from tools.tier1.pyspice_tool import PySpiceTool
from tools.tier1.python_control_tool import PythonControlTool
from tools.tier1.reliability_tool import ReliabilityTool
from tools.tier1.su2_tool import SU2Tool

for _cls in [
    CanteraTool, CoolPropTool, FenicsTool, MaterialsProjectTool,
    MatminerTool, OpenSeesTool, PyBulletTool, PySpiceTool,
    PythonControlTool, ReliabilityTool, SU2Tool,
]:
    try:
        register(_cls())
    except Exception:
        pass  # Skip tools that fail to instantiate

__all__ = [
    "register",
    "get_tool",
    "get_available_tools_for_domain",
    "get_anthropic_tools_for_domain",
    "availability_report",
]
