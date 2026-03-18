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

# ── Auto-register tier1 tools (resilient — missing files are skipped) ──
_TIER1_TOOLS = [
    ("tools.tier1.cantera_tool",           "CanteraTool"),
    ("tools.tier1.coolprop_tool",          "CoolPropTool"),
    ("tools.tier1.fenics_tool",            "FenicsTool"),
    ("tools.tier1.materials_project_tool", "MaterialsProjectTool"),
    ("tools.tier1.matminer_tool",          "MatminerTool"),
    ("tools.tier1.opensees_tool",          "OpenSeesTool"),
    ("tools.tier1.pybullet_tool",          "PyBulletTool"),
    ("tools.tier1.pyspice_tool",           "PySpiceTool"),
    ("tools.tier1.python_control_tool",    "PythonControlTool"),
    ("tools.tier1.reliability_tool",       "ReliabilityTool"),
    ("tools.tier1.su2_tool",               "SU2Tool"),
    ("tools.tier1.pypsa_tool",             "PyPSATool"),
    ("tools.tier1.brightway2_tool",        "Brightway2Tool"),
    ("tools.tier1.capytaine_tool",         "CapytaineTool"),
    ("tools.tier1.rayoptics_tool",         "RayOpticsTool"),
    ("tools.tier1.meep_tool",              "MeepTool"),
    ("tools.tier1.openmc_tool",            "OpenMCTool"),
    ("tools.tier1.openrocket_tool",        "OpenRocketTool"),
    ("tools.tier1.openfoam_tool",          "OpenFOAMTool"),
    ("tools.tier1.opensim_tool",           "OpenSimTool"),
    ("tools.tier1.febio_tool",             "FEBioTool"),
    ("tools.tier1.openmodelica_tool",      "OpenModelicaTool"),
    ("tools.tier1.freecad_tool",           "FreeCADTool"),
    ("tools.tier1.dwsim_tool",             "DWSIMTool"),
    ("tools.tier1.sumo_tool",              "SUMOTool"),
]

import importlib

for _module_path, _class_name in _TIER1_TOOLS:
    try:
        _mod = importlib.import_module(_module_path)
        _cls = getattr(_mod, _class_name)
        register(_cls())
    except Exception:
        pass  # Skip tools whose files don't exist yet or fail to instantiate

__all__ = [
    "register",
    "get_tool",
    "get_available_tools_for_domain",
    "get_anthropic_tools_for_domain",
    "availability_report",
]
