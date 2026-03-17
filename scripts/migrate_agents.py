"""
scripts/migrate_agents.py
Migrates agents_config.py -> SKILL.md architecture.
Run once after Plan 1 setup. Safe to delete afterward.

Usage:
    python scripts/migrate_agents.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from config.agents_config import AGENTS, DESTEK_AJANLARI

BASE = pathlib.Path(__file__).parent.parent / "agents"

# Domain key -> planned solver tools (stubs for Plan 2)
DOMAIN_TOOLS_MAP: dict[str, list[str]] = {
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

TOOL_METADATA: dict[str, dict] = {
    "cantera":            {"type": "open_source", "tier": 1, "install": "pip install cantera",
                           "capability": "Combustion kinetics, adiabatic flame temperature, emissions"},
    "coolprop":           {"type": "open_source", "tier": 1, "install": "pip install coolprop",
                           "capability": "Fluid thermophysical properties for 100+ fluids"},
    "fenics":             {"type": "open_source", "tier": 1,
                           "install": "conda install -c conda-forge fenics-dolfinx",
                           "capability": "Finite element analysis: structural, thermal, fluid"},
    "opensees":           {"type": "open_source", "tier": 1, "install": "pip install openseespy",
                           "capability": "Structural and earthquake engineering FEM"},
    "su2":                {"type": "open_source", "tier": 1, "install": "pip install SU2",
                           "capability": "Aerodynamic CFD and shape optimization"},
    "openfoam":           {"type": "open_source", "tier": 1,
                           "install": "apt-get install openfoam  # or Docker",
                           "capability": "General-purpose CFD: turbulence, combustion, multiphase"},
    "python_control":     {"type": "open_source", "tier": 1, "install": "pip install control",
                           "capability": "Control system analysis: stability, PID, Bode, step response"},
    "materials_project":  {"type": "open_source", "tier": 1, "install": "pip install mp-api",
                           "capability": "DFT material properties database (requires MP_API_KEY)"},
    "matminer":           {"type": "open_source", "tier": 1, "install": "pip install matminer",
                           "capability": "Materials informatics and feature engineering"},
    "pyspice":            {"type": "open_source", "tier": 1, "install": "pip install PySpice",
                           "capability": "SPICE circuit simulation"},
    "pybullet":           {"type": "open_source", "tier": 1, "install": "pip install pybullet",
                           "capability": "Rigid body dynamics and robotics simulation"},
    "pypsa":              {"type": "open_source", "tier": 1, "install": "pip install pypsa",
                           "capability": "Power systems analysis and optimization"},
    "brightway2":         {"type": "open_source", "tier": 1, "install": "pip install brightway2",
                           "capability": "Life cycle assessment (LCA)"},
    "capytaine":          {"type": "open_source", "tier": 1, "install": "pip install capytaine",
                           "capability": "Marine hydrodynamics, wave forces"},
    "dwsim":              {"type": "open_source", "tier": 1, "install": "pip install dwsim",
                           "capability": "Chemical process simulation"},
    "rayoptics":          {"type": "open_source", "tier": 1, "install": "pip install rayoptics",
                           "capability": "Optical system design and ray tracing"},
    "meep":               {"type": "open_source", "tier": 1,
                           "install": "conda install -c conda-forge pymeep",
                           "capability": "FDTD electromagnetic simulation"},
    "openmc":             {"type": "open_source", "tier": 1, "install": "pip install openmc",
                           "capability": "Monte Carlo neutron transport"},
    "opensim":            {"type": "open_source", "tier": 1,
                           "install": "conda install -c opensim-org opensim",
                           "capability": "Musculoskeletal biomechanics simulation"},
    "febio":              {"type": "open_source", "tier": 1, "install": "pip install febio-python",
                           "capability": "Biomedical finite element analysis"},
    "openrocket":         {"type": "open_source", "tier": 1, "install": "pip install openrocketpy",
                           "capability": "Rocket flight simulation"},
    "reliability":        {"type": "open_source", "tier": 1, "install": "pip install reliability",
                           "capability": "Weibull analysis, FMEA, MTBF, reliability prediction"},
    "sumo":               {"type": "open_source", "tier": 1, "install": "pip install eclipse-sumo",
                           "capability": "Traffic and vehicle dynamics simulation"},
    "openmodelica":       {"type": "open_source", "tier": 1,
                           "install": "apt install openmodelica && pip install OMPython",
                           "capability": "Modelica system dynamics simulation"},
    "freecad":            {"type": "open_source", "tier": 1,
                           "install": "conda install -c conda-forge freecad",
                           "capability": "Mechanical CAD and tolerance analysis"},
}


def _domain_from_key(key: str) -> str:
    """'yanma_a' -> 'yanma'"""
    return key.rsplit("_", 1)[0]


def _tier_from_key(key: str) -> str:
    """'yanma_a' -> 'theoretical', 'yanma_b' -> 'applied'"""
    return "theoretical" if key.endswith("_a") else "applied"


def write_skill_md(
    path: pathlib.Path,
    agent: dict,
    category: str,
    domain: str = "",
    tier: str = "support",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    thinking_budget = agent.get("thinking_budget", 0)
    planned_tools   = DOMAIN_TOOLS_MAP.get(domain, []) if domain else []

    lines = ["---"]
    lines.append(f'name: "{agent["isim"]}"')
    lines.append(f'model: "{agent["model"]}"')
    lines.append(f'max_tokens: {agent.get("max_tokens", 2000)}')
    lines.append(f'thinking_budget: {thinking_budget}')
    lines.append(f'domain: "{domain}"')
    lines.append(f'tier: "{tier}"')
    lines.append(f'category: "{category}"')

    if planned_tools:
        lines.append("tools:")
        for t in planned_tools:
            lines.append(f'  - "{t}"')
    else:
        lines.append("tools: []")

    lines.append("---")
    lines.append("")
    lines.append("## System Prompt")
    lines.append("")
    lines.append(agent["sistem_promptu"])

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  OK  {path.relative_to(BASE.parent)}")


def write_tools_yaml(path: pathlib.Path, domain: str, agent_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    planned = DOMAIN_TOOLS_MAP.get(domain, [])

    lines = [
        f"# tools.yaml -- {agent_key}",
        f"domain: {domain}",
        f"agent: {agent_key}",
        "solver_tier: 1",
        "active_tools: []",
        "",
        "planned_tools:",
    ]

    if not planned:
        lines.append("  []")
    else:
        for tool_name in planned:
            meta = TOOL_METADATA.get(tool_name, {})
            lines += [
                f"  - name: {tool_name}",
                f"    type: {meta.get('type', 'open_source')}",
                f"    tier: {meta.get('tier', 1)}",
                f'    install: "{meta.get("install", "")}"',
                f'    capability: "{meta.get("capability", "")}"',
                "    status: planned",
                "    wrapper: null",
                "",
            ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  OK  tools.yaml -> {domain}/{agent_key}")


# -- Run migration --
print("=== Migrating domain agents ===")
for agent_key, agent in AGENTS.items():
    domain = _domain_from_key(agent_key)
    tier   = _tier_from_key(agent_key)
    write_skill_md(
        BASE / "domain" / domain / agent_key / "SKILL.md",
        agent, "domain", domain, tier,
    )

print("\n=== Writing tools.yaml stubs ===")
for agent_key in AGENTS.keys():
    domain = _domain_from_key(agent_key)
    write_tools_yaml(
        BASE / "domain" / domain / agent_key / "tools.yaml",
        domain, agent_key,
    )

print("\n=== Migrating support agents ===")
for agent_key, agent in DESTEK_AJANLARI.items():
    write_skill_md(
        BASE / "support" / agent_key / "SKILL.md",
        agent, "support",
    )

print(f"\nMigration complete.")
print(f"  Domain agents : {len(AGENTS)}")
print(f"  Support agents: {len(DESTEK_AJANLARI)}")
print(f"\nNext step: python scripts/test_loader.py")
