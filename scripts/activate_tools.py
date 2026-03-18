#!/usr/bin/env python3
"""Batch-update all tools.yaml files to activate tools and set wrapper paths."""

import os
import glob
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Map tool name -> wrapper file path
WRAPPER_MAP = {
    "cantera":           "tools/tier1/cantera_tool.py",
    "coolprop":          "tools/tier1/coolprop_tool.py",
    "fenics":            "tools/tier1/fenics_tool.py",
    "materials_project": "tools/tier1/materials_project_tool.py",
    "matminer":          "tools/tier1/matminer_tool.py",
    "opensees":          "tools/tier1/opensees_tool.py",
    "pybullet":          "tools/tier1/pybullet_tool.py",
    "pyspice":           "tools/tier1/pyspice_tool.py",
    "python_control":    "tools/tier1/python_control_tool.py",
    "reliability":       "tools/tier1/reliability_tool.py",
    "su2":               "tools/tier1/su2_tool.py",
    "pypsa":             "tools/tier1/pypsa_tool.py",
    "brightway2":        "tools/tier1/brightway2_tool.py",
    "capytaine":         "tools/tier1/capytaine_tool.py",
    "rayoptics":         "tools/tier1/rayoptics_tool.py",
    "meep":              "tools/tier1/meep_tool.py",
    "openmc":            "tools/tier1/openmc_tool.py",
    "openrocket":        "tools/tier1/openrocket_tool.py",
    "openfoam":          "tools/tier1/openfoam_tool.py",
    "opensim":           "tools/tier1/opensim_tool.py",
    "febio":             "tools/tier1/febio_tool.py",
    "openmodelica":      "tools/tier1/openmodelica_tool.py",
    "freecad":           "tools/tier1/freecad_tool.py",
    "dwsim":             "tools/tier1/dwsim_tool.py",
    "sumo":              "tools/tier1/sumo_tool.py",
}


def activate_tools_yaml(filepath):
    """Read a tools.yaml, activate its tools, and write back."""
    with open(filepath, "r") as f:
        content = f.read()

    # Extract tool names from planned_tools
    tool_names = re.findall(r'^\s+- name:\s*(\S+)', content, re.MULTILINE)
    if not tool_names:
        return False

    # Build active_tools list
    active_list = ", ".join(f'"{t}"' for t in tool_names)
    content = re.sub(r'^active_tools:\s*\[\]', f'active_tools: [{active_list}]',
                     content, flags=re.MULTILINE)

    # Update status: planned -> active
    content = content.replace("status: planned", "status: active")

    # Update wrapper: null -> actual path
    for tool_name in tool_names:
        wrapper_path = WRAPPER_MAP.get(tool_name)
        if wrapper_path:
            # Replace wrapper: null for this tool's block
            content = content.replace(
                f"name: {tool_name}\n",
                f"name: {tool_name}\n",
            )
            # Use regex to find the wrapper field after this tool name
            pattern = rf'(- name: {re.escape(tool_name)}\b.*?wrapper:)\s*null'
            replacement = rf'\1 {wrapper_path}'
            content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    with open(filepath, "w") as f:
        f.write(content)
    return True


def main():
    pattern = os.path.join(ROOT, "agents", "domain", "**", "tools.yaml")
    files = glob.glob(pattern, recursive=True)

    updated = 0
    for filepath in sorted(files):
        rel = os.path.relpath(filepath, ROOT)
        if activate_tools_yaml(filepath):
            print(f"  ACTIVATED: {rel}")
            updated += 1
        else:
            print(f"  SKIPPED:   {rel} (no planned_tools)")

    print(f"\nTotal: {updated} files updated out of {len(files)}")


if __name__ == "__main__":
    main()
