"""tools/tier1/coolprop_tool.py — Fluid thermophysical properties via CoolProp."""
from tools.base import BaseToolWrapper, ToolResult


class CoolPropTool(BaseToolWrapper):
    name    = "coolprop"
    tier    = 1
    domains = ["termodinamik", "termal", "akiskan", "kimya", "yanma"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "fluid":        {"type": "string",
                             "description": "Fluid name: Water, R134a, Air, CO2, Nitrogen, etc."},
            "output":       {"type": "string",
                             "description": "Output property: T, P, H, S, D, Q, Cp, viscosity, conductivity"},
            "input1_name":  {"type": "string",
                             "description": "First input property: T, P, H, S, D, Q"},
            "input1_value": {"type": "number", "description": "First input value (SI units)"},
            "input2_name":  {"type": "string",  "description": "Second input property"},
            "input2_value": {"type": "number",  "description": "Second input value (SI units)"},
        },
        "required": ["fluid", "output", "input1_name", "input1_value",
                     "input2_name", "input2_value"],
    }

    _UNITS = {
        "T": "K", "P": "Pa", "H": "J/kg", "S": "J/kg-K",
        "D": "kg/m3", "Q": "-", "Cp": "J/kg-K",
        "viscosity": "Pa-s", "conductivity": "W/m-K",
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever a thermodynamic or transport property of a real fluid is needed: "
            "density, enthalpy, entropy, specific heat, viscosity, thermal conductivity, "
            "saturation temperature, or quality at a given state point.\n\n"
            "DO NOT CALL if:\n"
            "- The fluid is not a standard engineering fluid (use ideal gas relations instead)\n"
            "- Only qualitative comparison is needed\n\n"
            "REQUIRED inputs:\n"
            "- fluid: Water / R134a / Air / CO2 / Nitrogen / Hydrogen / Ammonia / etc.\n"
            "- output: T / P / H / S / D / Q / Cp / viscosity / conductivity\n"
            "- two independent state properties (e.g. P and T, or P and Q)\n\n"
            "Returns verified CoolProp REFPROP-quality fluid properties. "
            "Always prefer over ideal gas assumptions for two-phase or near-critical states."
        )

    def is_available(self) -> bool:
        try:
            import CoolProp.CoolProp as cp
            cp.PropsSI("T", "P", 101325, "Q", 0, "Water")
            return True
        except Exception:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            import CoolProp.CoolProp as cp

            fluid = inputs["fluid"]
            out   = inputs["output"]
            n1, v1 = inputs["input1_name"], float(inputs["input1_value"])
            n2, v2 = inputs["input2_name"], float(inputs["input2_value"])

            primary = cp.PropsSI(out, n1, v1, n2, v2, fluid)

            # Compute a supplementary set of properties
            extras = {}
            for prop in ["T", "P", "D", "Cp", "viscosity", "conductivity"]:
                if prop == out:
                    continue
                try:
                    extras[prop] = round(cp.PropsSI(prop, n1, v1, n2, v2, fluid), 6)
                except Exception:
                    pass

            data  = {f"{out}_{fluid}": round(primary, 6)}
            units = {f"{out}_{fluid}": self._UNITS.get(out, "-")}
            for k, v in extras.items():
                data[f"{k}_{fluid}"]  = v
                units[f"{k}_{fluid}"] = self._UNITS.get(k, "-")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data=data, units=units,
                raw_output=f"CoolProp: {fluid} {out}({n1}={v1},{n2}={v2})={primary:.6g}",
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
