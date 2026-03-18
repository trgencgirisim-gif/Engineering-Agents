#!/usr/bin/env python3
"""
Test installation and basic functionality of ALL registered solver tools.

Prints availability report, runs functional tests for each available solver
with realistic engineering inputs, and exits with code 1 if any test fails.
"""
import sys
import os
import traceback

# Add parent directory to sys.path so we can import tools
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools
from tools.registry import availability_report


# ── Availability Report ──────────────────────────────────────────────────────

def print_availability_report():
    """Print installation status for all registered tools."""
    report = availability_report()
    print("=" * 70)
    print("SOLVER AVAILABILITY REPORT")
    print("=" * 70)

    installed = []
    not_installed = []

    for name, info in sorted(report.items()):
        status = "INSTALLED" if info["available"] else "NOT INSTALLED"
        domains = ", ".join(info["domains"])
        line = f"  {name:<22} Tier {info['tier']}  [{status:>14}]  Domains: {domains}"
        print(line)
        if info["available"]:
            installed.append(name)
        else:
            not_installed.append(name)

    print("-" * 70)
    print(f"  Installed: {len(installed)}  |  Not installed: {len(not_installed)}")
    print(f"  Installed:     {', '.join(installed) if installed else '(none)'}")
    print(f"  Not installed: {', '.join(not_installed) if not_installed else '(none)'}")
    print("=" * 70)
    print()
    return installed, not_installed


# ── Test Cases ────────────────────────────────────────────────────────────────

TEST_CASES = {
    "cantera": {
        "description": "CH4/air combustion at phi=1.0 (stoichiometric)",
        "inputs": {
            "fuel": "CH4",
            "oxidizer": "air",
            "phi": 1.0,
            "T_initial": 300,
            "P_initial": 101325,
        },
        "validate": lambda r: (
            r.success
            and r.data.get("T_adiabatic_flame_K", 0) > 2000
            and r.data.get("T_adiabatic_flame_K", 0) < 2500
            and r.data.get("CO2_mole_fraction", 0) > 0.05
        ),
        "expected": "Adiabatic flame temperature ~2230 K, CO2 fraction > 0.05",
    },
    "coolprop": {
        "description": "Water boiling point at 1 atm (101325 Pa)",
        "inputs": {
            "fluid": "Water",
            "output": "T",
            "input1_name": "P",
            "input1_value": 101325,
            "input2_name": "Q",
            "input2_value": 0,
        },
        "validate": lambda r: (
            r.success
            and abs(r.data.get("T_Water", 0) - 373.15) < 1.0
        ),
        "expected": "Boiling point ~373.15 K (100 C)",
    },
    "python_control": {
        "description": "2nd order system stability margins: G(s) = 1 / (s^2 + 3s + 2)",
        "inputs": {
            "analysis_type": "stability_margins",
            "numerator": [1],
            "denominator": [1, 3, 2],
        },
        "validate": lambda r: (
            r.success
            and r.data.get("is_stable") is True
            and r.data.get("phase_margin_deg", 0) > 0
        ),
        "expected": "Stable system with positive phase margin",
    },
    "fenics": {
        "description": "Cantilever beam bending (steel, 1m x 0.1m x 0.05m, 10 kN/m2)",
        "inputs": {
            "problem_type": "beam_bending",
            "geometry": {"length": 1.0, "width": 0.1, "height": 0.05},
            "material": {"E": 210e9, "nu": 0.3, "sigma_yield": 250e6},
            "loads": {"distributed": 10000.0},
        },
        "validate": lambda r: (
            r.success
            and r.data.get("max_deflection_m", 0) > 0
            and r.data.get("max_bending_stress_MPa", 0) > 0
            and r.data.get("safety_factor", 0) > 1.0
        ),
        "expected": "Positive deflection, stress, and safety factor > 1.0",
    },
    "materials_project": {
        "description": "Fe (iron) material properties lookup",
        "inputs": {
            "query_type": "by_formula",
            "formula": "Fe",
        },
        "validate": lambda r: (
            r.success
            and len(r.data) > 0
        ),
        "expected": "At least one property returned for Fe",
    },
    "reliability": {
        "description": "MTBF calculation with exponential failure model (lambda=1e-4/hr, t=1000hr)",
        "inputs": {
            "analysis_type": "mtbf_calculation",
            "parameters": {
                "failure_rate": 1e-4,
                "mission_time": 1000.0,
            },
        },
        "validate": lambda r: (
            r.success
            and r.data.get("MTBF_hours", 0) == 10000.0
            and 0 < r.data.get("reliability_at_t", 0) < 1
        ),
        "expected": "MTBF = 10000 hrs, reliability at 1000 hrs ~ 0.905",
    },
    "opensees": {
        "description": "Gravity load analysis on a simple portal frame",
        "inputs": {
            "analysis_type": "gravity_load",
            "geometry": {
                "nodes": [
                    {"id": 1, "x": 0.0, "y": 0.0},
                    {"id": 2, "x": 6.0, "y": 0.0},
                    {"id": 3, "x": 0.0, "y": 3.5},
                    {"id": 4, "x": 6.0, "y": 3.5},
                ],
                "elements": [
                    {"id": 1, "node_i": 1, "node_j": 3, "A": 0.01, "I": 8.33e-4},
                    {"id": 2, "node_i": 2, "node_j": 4, "A": 0.01, "I": 8.33e-4},
                    {"id": 3, "node_i": 3, "node_j": 4, "A": 0.008, "I": 4.0e-4},
                ],
            },
            "material": {"E": 200e9, "fy": 345e6},
            "loads": {"gravity": 200e3},
        },
        "validate": lambda r: (
            r.success
            and r.data.get("total_gravity_load_kN", 0) == 200.0
            and r.data.get("reaction_per_column_kN", 0) > 0
            and r.data.get("column_utilization_ratio", 0) > 0
        ),
        "expected": "Total gravity 200 kN, positive reactions and utilization ratio",
    },
    "su2": {
        "description": "NACA 0012 airfoil at M=0.3, Re=1e6, alpha=5 deg",
        "inputs": {
            "analysis_type": "airfoil_analysis",
            "flow_params": {
                "mach": 0.3,
                "reynolds": 1e6,
                "alpha_deg": 5.0,
                "pressure": 101325,
                "temperature": 288.15,
            },
            "geometry": {
                "airfoil_type": "0012",
                "chord": 1.0,
            },
        },
        "validate": lambda r: (
            r.success
            and r.data.get("Cl", 0) > 0.3
            and r.data.get("Cd_total", 0) > 0
            and r.data.get("L_over_D", 0) > 5
        ),
        "expected": "Positive Cl > 0.3, positive Cd, L/D > 5",
    },
    "matminer": {
        "description": "Fe2O3 (iron oxide) material property estimation",
        "inputs": {
            "formula": "Fe2O3",
            "properties": [
                "band_gap", "formation_energy", "density",
                "electronegativity", "atomic_radius",
            ],
        },
        "validate": lambda r: (
            r.success
            and r.data.get("avg_electronegativity", 0) > 0
            and r.data.get("n_elements", 0) == 2
        ),
        "expected": "Positive electronegativity, 2 elements (Fe, O)",
    },
    "pyspice": {
        "description": "Voltage divider: 10V, R1=10k, R2=10k -> Vout=5V",
        "inputs": {
            "circuit_type": "voltage_divider",
            "components": {
                "R1": 10000.0,
                "R2": 10000.0,
                "V": 10.0,
            },
        },
        "validate": lambda r: (
            r.success
            and abs(r.data.get("V_out_V", 0) - 5.0) < 0.01
            and r.data.get("I_total_mA", 0) > 0
        ),
        "expected": "Vout = 5.0 V, positive current",
    },
    "pybullet": {
        "description": "2-link planar robot FK: L1=1m, L2=0.8m, q1=pi/4, q2=-pi/6",
        "inputs": {
            "simulation_type": "forward_kinematics",
            "robot_params": {
                "lengths": [1.0, 0.8],
                "joints": [0.7854, -0.5236],
            },
        },
        "validate": lambda r: (
            r.success
            and r.data.get("end_effector_dist_m", 0) > 0
            and r.data.get("n_dof", 0) == 2
        ),
        "expected": "Positive end-effector distance, 2 DOF",
    },
}


# ── Test Runner ───────────────────────────────────────────────────────────────

def run_tests(installed_solvers):
    """Run functional tests for all available solvers."""
    print("=" * 70)
    print("FUNCTIONAL TESTS")
    print("=" * 70)

    passed = []
    failed = []
    skipped = []

    for solver_name in sorted(TEST_CASES.keys()):
        tc = TEST_CASES[solver_name]
        print(f"\n  [{solver_name.upper()}] {tc['description']}")

        if solver_name not in installed_solvers:
            print(f"    SKIPPED — solver not installed")
            skipped.append(solver_name)
            continue

        tool = tools.get_tool(solver_name)
        if tool is None:
            print(f"    SKIPPED — solver not in registry")
            skipped.append(solver_name)
            continue

        try:
            result = tool.execute(tc["inputs"])

            if tc["validate"](result):
                print(f"    PASSED")
                print(f"    Expected: {tc['expected']}")
                # Print key data points
                for key, val in list(result.data.items())[:5]:
                    unit = result.units.get(key, "")
                    if isinstance(val, float):
                        print(f"      {key} = {val:.6g} {unit}")
                    elif not isinstance(val, (list, dict)):
                        print(f"      {key} = {val} {unit}")
                passed.append(solver_name)
            else:
                print(f"    FAILED — validation did not pass")
                print(f"    Expected: {tc['expected']}")
                if not result.success:
                    print(f"    Error: {result.error}")
                else:
                    for key, val in list(result.data.items())[:5]:
                        if isinstance(val, (int, float)):
                            print(f"      {key} = {val}")
                failed.append(solver_name)

        except Exception as exc:
            print(f"    FAILED — exception: {exc}")
            traceback.print_exc(limit=3)
            failed.append(solver_name)

    return passed, failed, skipped


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    installed, not_installed = print_availability_report()

    passed, failed, skipped = run_tests(installed)

    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"  Total test cases: {len(TEST_CASES)}")
    print(f"  Passed:  {len(passed):>3}  {', '.join(passed) if passed else '(none)'}")
    print(f"  Failed:  {len(failed):>3}  {', '.join(failed) if failed else '(none)'}")
    print(f"  Skipped: {len(skipped):>3}  {', '.join(skipped) if skipped else '(none)'}")
    print("=" * 70)

    if failed:
        print("\nRESULT: FAIL")
        sys.exit(1)
    else:
        print("\nRESULT: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
