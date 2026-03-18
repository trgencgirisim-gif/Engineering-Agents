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
relevant to your domain, you MUST call it to obtain verified numerical results.

**Rules for using solver results:**
- Tag solver-computed values as `[VERIFIED — <solver_name>]` in your output
- Do NOT produce your own estimates for quantities already computed by a solver
- If a solver returns `STATUS: FAILED` or `STATUS: UNAVAILABLE`, proceed with
  your own engineering estimate and mark it with `[ASSUMPTION]`
- Solver assumptions are listed in the result — incorporate them into your analysis

**Your available tools:**
"""

# ---------------------------------------------------------------------------
# Layer 2: Solver obligation block (appended to all domain SKILL.md files)
# ---------------------------------------------------------------------------
SOLVER_OBLIGATION_BLOCK = """
## Solver Usage Policy

If a solver tool is available for this domain and the problem contains
quantifiable parameters, you MUST attempt a tool call before writing
any numerical values in your analysis.

Writing an estimated value (e.g. "approximately 1800 C" or "roughly 250 MPa")
when a solver could have computed it is a quality failure.
The Observer agent will flag this and reduce the quality score.

Required sequence when solver tools are available:
1. Identify which numerical outputs the problem requires
2. Determine if those outputs map to an available tool
3. Extract input parameters from the brief (use defaults if not stated)
4. Call the tool
5. Write analysis using [VERIFIED — tool_name] for solver values
6. Use [ASSUMPTION] only for values the solver cannot compute

If the tool call fails (solver not installed, insufficient inputs):
- State [SOLVER UNAVAILABLE] or [INSUFFICIENT INPUTS FOR SOLVER]
- Continue with engineering estimate
- Label every estimated numerical value with [ASSUMPTION]
"""

# Domain-specific critical rules for high-impact domains
CRITICAL_SOLVER_DOMAINS: dict[str, str] = {
    "yapisal": """
CRITICAL RULE for structural analysis:
If geometry (length, width, height) and material (E, nu, sigma_yield)
and loads (distributed or point) are all present in the brief,
you MUST call fenics_tool. No exceptions.
A safety factor computed without FEM when FEM was possible
is scored as a quality failure by the Observer.
""",
    "yanma": """
CRITICAL RULE for combustion analysis:
If fuel type and any two of (phi, T_initial, P_initial) can be
extracted from the brief, you MUST call cantera_tool.
An estimated flame temperature when Cantera was available
is scored as a quality failure by the Observer.
""",
    "kontrol": """
CRITICAL RULE for control analysis:
If a transfer function (numerator and denominator coefficients)
can be derived from the brief, you MUST call python_control_tool.
A stability assessment without computed margins is a quality failure.
""",
}

# ---------------------------------------------------------------------------
# Layer 3: Few-shot examples for high-impact domains
# ---------------------------------------------------------------------------
FEW_SHOT_EXAMPLES: dict[str, str] = {

    "yanma": """
## Tool Usage Examples

### CORRECT - Tool called, verified values used
Brief: "Natural gas burner, equivalence ratio 0.85, inlet temperature 400K,
atmospheric pressure. Compute adiabatic flame temperature and NOx."

Agent behavior:
1. Extracts: fuel=CH4, phi=0.85, T_initial=400, P_initial=101325
2. Calls cantera tool
3. Receives: T_adiabatic_flame_K=1923.4, NOx_ppm=12.4, CO_mole_fraction=0.000031
4. Writes in analysis:
   "Adiabatic flame temperature: 1923.4 K [VERIFIED - cantera]
   NOx emissions: 12.4 ppm [VERIFIED - cantera]
   The lean mixture (phi=0.85) suppresses NOx formation relative to
   stoichiometric conditions..."

### INCORRECT - Do not do this
Same brief.

Agent writes:
"Adiabatic flame temperature is approximately 1800-2000 C for natural gas..."
WRONG. Cantera was available. This is a quality failure.
""",

    "yapisal": """
## Tool Usage Examples

### CORRECT - FEM called, safety factor verified
Brief: "Steel cantilever beam, length 2m, width 100mm, height 80mm,
E=210GPa, yield strength 250MPa, distributed load 5000 N/m."

Agent behavior:
1. Extracts: L=2.0, b=0.1, h=0.08, E=210e9, sigma_yield=250e6, q=5000
2. Calls fenics tool with problem_type=beam_bending
3. Receives: max_bending_stress_MPa=35.2, safety_factor=7.1, max_deflection_m=0.00286
4. Writes:
   "Maximum bending stress: 35.2 MPa [VERIFIED - fenics]
   Safety factor: 7.1 vs yield (target >= 2.0) [VERIFIED - fenics]
   Maximum deflection: 2.86 mm [VERIFIED - fenics]
   The section is significantly over-designed..."

### INCORRECT - Do not do this
Same brief.

Agent writes:
"Estimated bending stress is approximately 30-40 MPa..."
WRONG. FEM was available with complete inputs. This is a quality failure.
""",

    "kontrol": """
## Tool Usage Examples

### CORRECT - Stability margins computed
Brief: "Second-order system with transfer function G(s) = 10/(s^2 + 3s + 2).
Assess stability and step response."

Agent behavior:
1. Extracts: numerator=[10], denominator=[1, 3, 2]
2. Calls python_control tool with analysis_type=stability_margins
3. Receives: gain_margin_dB=inf, phase_margin_deg=61.3,
             step_overshoot_pct=8.1, settling_time_2pct_s=2.7, is_stable=True
4. Writes:
   "Phase margin: 61.3 deg [VERIFIED - python_control] - adequate (target >= 45 deg)
   Step overshoot: 8.1% [VERIFIED - python_control] - within spec
   Settling time (2%): 2.7 s [VERIFIED - python_control]
   The system is stable with comfortable margins..."

### INCORRECT - Do not do this
Same brief.

Agent writes:
"The system appears stable based on the denominator roots..."
WRONG. Transfer function was available. Margins must be computed. Quality failure.
""",

    "malzeme": """
## Tool Usage Examples

### CORRECT - Database properties retrieved
Brief: "Evaluate titanium dioxide (TiO2) for thermal barrier coating.
Need density and elastic modulus."

Agent behavior:
1. Identifies: query_type=by_formula, formula=TiO2
2. Calls materials_project tool
3. Receives: density=3.89 g/cm^3, bulk_modulus_vrh_GPa=186.2, band_gap=3.05 eV
4. Writes:
   "TiO2 density: 3.89 g/cm^3 [VERIFIED - materials_project, DFT 0K]
   Bulk modulus: 186.2 GPa [VERIFIED - materials_project]
   Note: DFT values are for pure rutile phase at 0K.
   Real coating properties depend on deposition method and porosity..."

### INCORRECT - Do not do this
Same brief.

Agent writes:
"TiO2 typically has a density around 3.5-4.2 g/cm^3..."
WRONG. materials_project was available. Use the database. Quality failure.
""",

    "termodinamik": """
## Tool Usage Examples

### CORRECT - Real fluid properties retrieved
Brief: "Steam Rankine cycle: boiler at 10 MPa and 550 C, condenser at 10 kPa.
Compute turbine inlet enthalpy and condenser outlet state."

Agent behavior:
1. Calls coolprop for turbine inlet: fluid=Water, P=10e6 Pa, T=823.15 K -> output=H
2. Receives: H_Water=3500.9 kJ/kg
3. Calls coolprop for condenser outlet: fluid=Water, P=10000 Pa, Q=0 -> output=T
4. Receives: T_Water=318.8 K (saturation temperature at 10 kPa)
5. Writes:
   "Turbine inlet enthalpy: 3500.9 kJ/kg [VERIFIED - coolprop]
   Condenser saturation temperature: 318.8 K (45.6 C) [VERIFIED - coolprop]
   Cycle thermal efficiency calculation proceeds from these verified state points..."

### INCORRECT - Do not do this
Same brief.

Agent writes:
"Steam enthalpy at 10 MPa and 550 C is approximately 3500 kJ/kg from steam tables..."
WRONG. CoolProp was available for exact values. Quality failure.
""",
}


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

    # Append solver obligation block
    lines.append(SOLVER_OBLIGATION_BLOCK)

    # Append critical solver domain rule if applicable
    if domain in CRITICAL_SOLVER_DOMAINS:
        lines.append(CRITICAL_SOLVER_DOMAINS[domain])

    # Append few-shot examples if applicable
    if domain in FEW_SHOT_EXAMPLES:
        lines.append(FEW_SHOT_EXAMPLES[domain])

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
