"""tools/extractors/coolprop_extractor.py — Extract CoolProp inputs from problem text."""
import re
from tools.extractors.base_extractor import BaseInputExtractor

# Common fluid name aliases
_FLUID_ALIASES: dict[str, str] = {
    "water":      "Water",
    "steam":      "Water",
    "air":        "Air",
    "nitrogen":   "Nitrogen",
    "oxygen":     "Oxygen",
    "hydrogen":   "Hydrogen",
    "co2":        "CO2",
    "carbon dioxide": "CO2",
    "ammonia":    "Ammonia",
    "r134a":      "R134a",
    "r410a":      "R410a",
    "r22":        "R22",
    "r744":       "CO2",
    "methane":    "Methane",
    "propane":    "Propane",
    "ethanol":    "Ethanol",
    "helium":     "Helium",
    "argon":      "Argon",
}


class CoolPropExtractor(BaseInputExtractor):
    solver_name = "coolprop"

    def extract(self, text: str, brief: str = "") -> dict | None:
        combined = (brief + " " + text).lower()

        # Fluid identification
        fluid = "Water"
        for alias, name in _FLUID_ALIASES.items():
            if alias in combined:
                fluid = name
                break

        # Determine what output property is desired
        output = "T"  # default
        output_map = {
            "temperature":    "T",
            "pressure":       "P",
            "enthalpy":       "H",
            "entropy":        "S",
            "density":        "D",
            "quality":        "Q",
            "specific heat":  "Cp",
            "viscosity":      "viscosity",
            "conductivity":   "conductivity",
        }
        for keyword, prop in output_map.items():
            if keyword in combined and "find" in combined or "calculate" in combined or "compute" in combined:
                output = prop
                break

        # Extract temperature
        T = self._find_number(combined, [
            r'(?:temperature|temp)\s*[=:]\s*([\d.]+)\s*K',
            r'T\s*[=:]\s*([\d.]+)\s*K',
            r'([\d.]+)\s*K\b',
        ])

        # Extract pressure
        P = self._find_number(combined, [
            r'(?:pressure)\s*[=:]\s*([\d.]+)\s*(?:Pa|kPa|MPa|bar|atm)',
            r'P\s*[=:]\s*([\d.]+)\s*(?:Pa|kPa|MPa|bar|atm)',
        ])

        # Convert pressure units
        if P is not None:
            if re.search(r'([\d.]+)\s*MPa', combined, re.IGNORECASE):
                P *= 1e6
            elif re.search(r'([\d.]+)\s*kPa', combined, re.IGNORECASE):
                P *= 1e3
            elif re.search(r'([\d.]+)\s*bar', combined, re.IGNORECASE):
                P *= 1e5
            elif re.search(r'([\d.]+)\s*atm', combined, re.IGNORECASE):
                P *= 101325.0

        # Build input pairs
        input1_name, input1_value = "P", P if P else 101325.0
        input2_name, input2_value = "T", T if T else 300.0

        # If both T and P are available, use them as inputs
        if T and P:
            if output == "T":
                output = "H"  # already have T, compute something else
            input1_name, input1_value = "T", T
            input2_name, input2_value = "P", P

        return {
            "fluid":        fluid,
            "output":       output,
            "input1_name":  input1_name,
            "input1_value": input1_value,
            "input2_name":  input2_name,
            "input2_value": input2_value,
        }
