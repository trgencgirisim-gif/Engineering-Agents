#!/usr/bin/env python3
"""
Append solver tool usage instructions to SKILL.md system prompts.

For each domain agent SKILL.md, reads the agent's domain, looks up available tools
from the registry, and appends a '## Available Solver Tools' section with
tool names, descriptions, and input schemas.

Idempotent: removes any existing '## Available Solver Tools' section before appending.

Usage:
    python scripts/update_skill_prompts.py
"""

import os
import sys
import re
import json
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.registry import DOMAIN_TOOLS, _REGISTRY


# Tool descriptions (short) — fallback if wrapper not loaded
TOOL_DESCRIPTIONS = {
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


def build_tool_section(domain: str) -> str:
    """Build the tool usage section for a given domain."""
    tool_names = DOMAIN_TOOLS.get(domain, [])
    if not tool_names:
        return ""

    lines = [SOLVER_USAGE_HEADER, SOLVER_USAGE_PREAMBLE]

    for name in tool_names:
        desc = TOOL_DESCRIPTIONS.get(name, "Solver tool")

        # Try to get INPUT_SCHEMA from registered wrapper
        wrapper = _REGISTRY.get(name)
        schema_text = ""
        if wrapper and hasattr(wrapper, "INPUT_SCHEMA") and wrapper.INPUT_SCHEMA:
            props = wrapper.INPUT_SCHEMA.get("properties", {})
            required = wrapper.INPUT_SCHEMA.get("required", [])
            if props:
                schema_lines = []
                for prop_name, prop_def in list(props.items())[:8]:
                    prop_type = prop_def.get("type", "any")
                    prop_desc = prop_def.get("description", "")
                    req_mark = " (required)" if prop_name in required else ""
                    schema_lines.append(f"    - `{prop_name}`: {prop_type}{req_mark} — {prop_desc}")
                schema_text = "\n".join(schema_lines)

        lines.append(f"### `{name}`")
        lines.append(f"{desc}")
        if schema_text:
            lines.append(f"**Input parameters:**")
            lines.append(schema_text)
        lines.append("")

    return "\n".join(lines)


def update_skill_md(filepath: str) -> bool:
    """Update a single SKILL.md with tool instructions. Returns True if modified."""
    with open(filepath, "r") as f:
        content = f.read()

    # Extract domain from frontmatter
    domain_match = re.search(r'^domain:\s*"?(\w+)"?', content, re.MULTILINE)
    if not domain_match:
        return False
    domain = domain_match.group(1)

    # Check if domain has tools
    tool_names = DOMAIN_TOOLS.get(domain, [])
    if not tool_names:
        return False

    # Remove existing tool section (idempotent)
    pattern = rf'\n*{re.escape(SOLVER_USAGE_HEADER)}.*'
    content = re.sub(pattern, '', content, flags=re.DOTALL).rstrip()

    # Build and append new section
    tool_section = build_tool_section(domain)
    if tool_section:
        content = content + "\n\n" + tool_section + "\n"

    with open(filepath, "w") as f:
        f.write(content)
    return True


def main():
    pattern = os.path.join(ROOT, "agents", "domain", "**", "SKILL.md")
    files = glob.glob(pattern, recursive=True)

    updated = 0
    skipped = 0
    for filepath in sorted(files):
        rel = os.path.relpath(filepath, ROOT)
        if update_skill_md(filepath):
            print(f"  UPDATED: {rel}")
            updated += 1
        else:
            print(f"  SKIPPED: {rel} (no tools for domain)")
            skipped += 1

    print(f"\nTotal: {updated} updated, {skipped} skipped out of {len(files)}")


if __name__ == "__main__":
    main()
