#!/usr/bin/env python3
"""
scripts/update_skill_prompts.py
Reads all domain-agent SKILL.md files, looks up available tools from the
registry's DOMAIN_TOOLS mapping, and appends (or replaces) an
"## Available Solver Tools" section listing each tool's name, description,
and full input schema.

Idempotent: any existing "## Available Solver Tools" section is stripped
before the new one is appended.

Usage:
    python scripts/update_skill_prompts.py
"""
from __future__ import annotations

import glob
import importlib
import inspect
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.base import BaseToolWrapper  # noqa: E402
from tools.registry import DOMAIN_TOOLS  # noqa: E402

# ---------------------------------------------------------------------------
# Lazy tool-wrapper instantiation (does not require libraries to be installed)
# ---------------------------------------------------------------------------
_TOOL_INSTANCES: dict[str, BaseToolWrapper] = {}
_SCAN_DONE = False


def _scan_all_tools() -> None:
    """Import all *_tool.py modules under tools/ to discover wrapper classes."""
    global _SCAN_DONE
    if _SCAN_DONE:
        return

    tools_dir = os.path.join(ROOT, "tools")
    for tier_name in sorted(os.listdir(tools_dir)):
        tier_path = os.path.join(tools_dir, tier_name)
        if not os.path.isdir(tier_path) or tier_name.startswith("__"):
            continue
        for fname in sorted(os.listdir(tier_path)):
            if not fname.endswith("_tool.py"):
                continue
            module_name = f"tools.{tier_name}.{fname[:-3]}"
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                continue
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, BaseToolWrapper)
                    and obj is not BaseToolWrapper
                    and hasattr(obj, "name")
                    and isinstance(getattr(obj, "name", None), str)
                ):
                    try:
                        instance = obj()
                        _TOOL_INSTANCES[instance.name] = instance
                    except Exception:
                        pass
    _SCAN_DONE = True


def _get_tool(name: str) -> BaseToolWrapper | None:
    _scan_all_tools()
    return _TOOL_INSTANCES.get(name)


# ---------------------------------------------------------------------------
# Fallback descriptions for tools whose wrappers haven't been written yet
# ---------------------------------------------------------------------------
FALLBACK_DESCRIPTIONS: dict[str, str] = {
    "cantera":           "Combustion kinetics solver: adiabatic flame temperature, species equilibrium, emissions",
    "coolprop":          "Thermodynamic property calculator: saturation, phase states, transport properties",
    "fenics":            "Finite Element Method (FEM) solver: structural, thermal, fluid problems",
    "materials_project": "Materials database: crystal structures, band gaps, formation energies",
    "matminer":          "Materials ML: composition-based property estimation and featurization",
    "opensees":          "Structural/earthquake FEM solver: frame analysis, pushover, modal",
    "pybullet":          "Robotics dynamics: forward/inverse kinematics, multi-body simulation",
    "pyspice":           "Circuit analysis: DC operating point, AC frequency response, transient",
    "python_control":    "Control systems: transfer function analysis, stability margins, Bode/Nyquist",
    "reliability":       "Reliability/FMEA: MTBF, failure rate, Weibull, RPN calculations",
    "su2":               "Computational Fluid Dynamics (CFD): airfoil analysis, external aerodynamics",
    "pypsa":             "Energy system optimization: dispatch, capacity expansion, power flow",
    "brightway2":        "Life Cycle Assessment (LCA): carbon footprint, environmental impact",
    "capytaine":         "Marine hydrodynamics: wave loads, ship motion, wave resistance",
    "rayoptics":         "Optical ray tracing: lens analysis, mirror systems, aberrations",
    "meep":              "FDTD electromagnetic simulation: waveguides, photonic crystals, antennas",
    "openmc":            "Monte Carlo nuclear transport: criticality, shielding, dose rate",
    "openrocket":        "Rocket trajectory simulation: motor performance, stability analysis",
    "openfoam":          "CFD solver: pipe flow, external flow, heat transfer",
    "opensim":           "Musculoskeletal biomechanics: joint forces, gait analysis, muscle modeling",
    "febio":             "Nonlinear FEM for biological tissues: hyperelastic, implant stress",
    "openmodelica":      "Multi-domain physical modeling (Modelica): hydraulic, thermal, dynamic systems",
    "freecad":           "CAD/CAM analysis: machining time, tolerance stack, material removal rate",
    "dwsim":             "Chemical process simulation: VLE flash, reactor design, heat exchanger sizing",
    "sumo":              "Traffic simulation: traffic flow, vehicle dynamics, intersection analysis",
}


# ---------------------------------------------------------------------------
# Section builder
# ---------------------------------------------------------------------------
SOLVER_USAGE_HEADER = "## Available Solver Tools"

SOLVER_USAGE_PREAMBLE = """
When solver tools are available, the system will automatically provide them as
Anthropic tool_use functions during your analysis. If a solver is installed and
relevant to your domain, you SHOULD call it to obtain verified numerical results.

**Rules for using solver results:**
- Tag solver-computed values as `[VERIFIED — <solver_name>]` in your output
- Do NOT produce your own estimates for quantities already computed by a solver
- If a solver returns `STATUS: FAILED` or `STATUS: UNAVAILABLE`, proceed with
  your own engineering estimate and mark it with `[ASSUMPTION]`
- Solver assumptions are listed in the result — incorporate them into your analysis

**Your available tools:**
"""


def _build_tool_section(domain: str) -> str:
    """Build the '## Available Solver Tools' section for *domain*."""
    tool_names = DOMAIN_TOOLS.get(domain, [])
    if not tool_names:
        return ""

    lines = [SOLVER_USAGE_HEADER, SOLVER_USAGE_PREAMBLE]

    for name in tool_names:
        wrapper = _get_tool(name)

        # Description: prefer wrapper._description(), fall back to dict
        if wrapper and hasattr(wrapper, "_description"):
            try:
                desc = wrapper._description()
            except Exception:
                desc = FALLBACK_DESCRIPTIONS.get(name, "Solver tool")
        else:
            desc = FALLBACK_DESCRIPTIONS.get(name, "Solver tool")

        # Schema: prefer wrapper.INPUT_SCHEMA, else show nothing
        schema = {}
        if wrapper and hasattr(wrapper, "INPUT_SCHEMA"):
            schema = getattr(wrapper, "INPUT_SCHEMA", {})

        lines.append(f"### `{name}`")
        lines.append(desc)
        if schema:
            lines.append("")
            lines.append("**Input Schema:**")
            lines.append("```json")
            lines.append(json.dumps(schema, indent=2))
            lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SKILL.md mutation
# ---------------------------------------------------------------------------
def _update_skill_md(filepath: str) -> bool:
    """Update a single SKILL.md. Returns True if file was modified."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract domain from YAML frontmatter
    m = re.search(r'^domain:\s*"?(\w+)"?', content, re.MULTILINE)
    if not m:
        return False
    domain = m.group(1)

    tool_names = DOMAIN_TOOLS.get(domain, [])
    if not tool_names:
        # No tools — strip old section if present, leave file otherwise
        cleaned = re.sub(
            rf"\n*{re.escape(SOLVER_USAGE_HEADER)}.*", "", content, flags=re.DOTALL
        ).rstrip()
        if cleaned != content.rstrip():
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(cleaned + "\n")
            return True
        return False

    # Strip existing section (idempotent)
    cleaned = re.sub(
        rf"\n*{re.escape(SOLVER_USAGE_HEADER)}.*", "", content, flags=re.DOTALL
    ).rstrip()

    section = _build_tool_section(domain)
    new_content = cleaned + "\n\n" + section + "\n"

    if new_content.rstrip() == content.rstrip():
        return False

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    pattern = os.path.join(ROOT, "agents", "domain", "**", "SKILL.md")
    files = sorted(glob.glob(pattern, recursive=True))

    if not files:
        print("No SKILL.md files found under agents/domain/.")
        sys.exit(1)

    updated = 0
    skipped = 0
    for filepath in files:
        rel = os.path.relpath(filepath, ROOT)
        if _update_skill_md(filepath):
            print(f"  UPDATED  {rel}")
            updated += 1
        else:
            print(f"  SKIPPED  {rel}")
            skipped += 1

    print(f"\nDone. Updated: {updated}, Skipped: {skipped}, Total: {len(files)}")


if __name__ == "__main__":
    main()
