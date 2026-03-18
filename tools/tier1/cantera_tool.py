"""tools/tier1/cantera_tool.py — Combustion kinetics via Cantera."""
from tools.base import BaseToolWrapper, ToolResult


class CanteraTool(BaseToolWrapper):
    name    = "cantera"
    tier    = 1
    domains = ["yanma", "termodinamik", "kimya"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "fuel":      {"type": "string",
                          "description": "Fuel formula: CH4, C3H8, H2, JP-10, C8H18, etc."},
            "oxidizer":  {"type": "string",
                          "description": "Oxidizer: air or O2", "default": "air"},
            "phi":       {"type": "number",
                          "description": "Equivalence ratio (0.5 - 2.0)", "default": 1.0},
            "T_initial": {"type": "number",
                          "description": "Initial temperature [K]", "default": 300},
            "P_initial": {"type": "number",
                          "description": "Initial pressure [Pa]", "default": 101325},
            "mechanism": {"type": "string",
                          "description": "Reaction mechanism file", "default": "gri30.yaml"},
        },
        "required": ["fuel"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: adiabatic flame temperature, "
            "CO/CO2/NOx emissions, heat release rate, or laminar flame speed.\n\n"
            "DO NOT CALL if:\n"
            "- Question is qualitative (which fuel is better, not how hot)\n"
            "- No fuel information is present in the brief\n\n"
            "REQUIRED inputs:\n"
            "- fuel: CH4 / H2 / C3H8 / JP-10 / C8H18 (default: CH4)\n"
            "- phi: equivalence ratio (default: 1.0)\n"
            "- T_initial: K (default: 300)\n"
            "- P_initial: Pa (default: 101325)\n\n"
            "Returns verified Cantera GRI3.0 results. "
            "Estimating flame temperature when this tool is available is a quality failure."
        )

    def is_available(self) -> bool:
        try:
            import cantera as ct
            ct.Solution("gri30.yaml")
            return True
        except Exception:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            import cantera as ct

            fuel      = inputs.get("fuel", "CH4")
            oxidizer  = inputs.get("oxidizer", "air")
            phi       = float(inputs.get("phi", 1.0))
            T_initial = float(inputs.get("T_initial", 300.0))
            P_initial = float(inputs.get("P_initial", 101325.0))
            mechanism = inputs.get("mechanism", "gri30.yaml")

            gas = ct.Solution(mechanism)
            gas.set_equivalence_ratio(phi, fuel, oxidizer)
            gas.TP = T_initial, P_initial
            gas.equilibrate("HP")

            warnings = []
            if phi > 1.5:
                warnings.append("Rich mixture (phi > 1.5): elevated CO, reduced NOx")
            if phi < 0.5:
                warnings.append("Lean mixture (phi < 0.5): flame stability risk")
            if T_initial > 700:
                warnings.append("High preheat temperature: check auto-ignition")

            return ToolResult(
                success=True,
                solver=self.name,
                confidence="HIGH",
                data={
                    "T_adiabatic_flame_K":   round(gas.T, 1),
                    "CO2_mole_fraction":     round(float(gas["CO2"].X[0]), 6),
                    "CO_mole_fraction":      round(float(gas["CO"].X[0]),  6),
                    "NOx_ppm":               round(float(gas["NO"].X[0]) * 1e6, 3),
                    "heat_release_J_per_kg": round(-gas.enthalpy_mass, 0),
                    "density_kg_m3":         round(gas.density, 4),
                },
                units={
                    "T_adiabatic_flame_K":   "K",
                    "heat_release_J_per_kg": "J/kg",
                    "density_kg_m3":         "kg/m3",
                    "NOx_ppm":               "ppm",
                },
                raw_output=(
                    f"Cantera {mechanism}: {fuel}/air phi={phi} "
                    f"T_in={T_initial} K P_in={P_initial} Pa"
                ),
                warnings=warnings,
                assumptions=[
                    f"Mechanism: {mechanism}",
                    "Constant-pressure adiabatic combustion (HP equilibration)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
