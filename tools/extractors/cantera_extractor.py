"""tools/extractors/cantera_extractor.py — Extract Cantera inputs from problem text."""
import re
from tools.extractors.base_extractor import BaseInputExtractor

_FUEL_ALIASES: dict[str, str] = {
    "methane":     "CH4", "natural gas":  "CH4",
    "propane":     "C3H8",
    "hydrogen":    "H2",
    "kerosene":    "C12H23",
    "jp-10":       "C10H16", "jp10": "C10H16",
    "gasoline":    "C8H18",
    "diesel":      "C12H26",
    "ethanol":     "C2H5OH",
    "ammonia":     "NH3",
}

_FORMULA_RE = re.compile(
    r'\b(CH4|H2|C3H8|C2H5OH|C10H16|C12H23|C12H26|C8H18|NH3)\b', re.IGNORECASE
)


class CanteraExtractor(BaseInputExtractor):
    solver_name = "cantera"

    def extract(self, text: str, brief: str = "") -> dict | None:
        combined = (brief + " " + text).lower()

        # Fuel identification
        fuel = "CH4"
        for alias, formula in _FUEL_ALIASES.items():
            if alias in combined:
                fuel = formula
                break
        m_formula = _FORMULA_RE.search(brief + " " + text)
        if m_formula:
            fuel = m_formula.group(1).upper()

        # Equivalence ratio
        phi = self._find_number(combined, [
            r'phi\s*[=:]\s*([\d.]+)',
            r'equivalence\s+ratio\s*[=:]\s*([\d.]+)',
            r'stoichiometric\s+ratio\s*([\d.]+)',
        ], default=1.0)

        # Initial temperature
        T = self._find_number(combined, [
            r'(?:inlet|initial|preheat)\s+temp[^=\n]*[=:]\s*([\d.]+)',
            r'T_in\s*[=:]\s*([\d.]+)',
            r'T_0\s*[=:]\s*([\d.]+)',
            r'(\d{2,4})\s*K\b',
        ], default=300.0)
        if T and T < 150:
            T += 273.15  # assume Celsius

        # Initial pressure
        P = None
        for pat, factor in [
            (r'([\d.]+)\s*atm\b', 101325.0),
            (r'([\d.]+)\s*bar\b', 1e5),
            (r'([\d.]+)\s*MPa\b', 1e6),
            (r'([\d.]+)\s*kPa\b', 1e3),
        ]:
            m_p = re.search(pat, combined, re.IGNORECASE)
            if m_p:
                P = float(m_p.group(1)) * factor
                break
        if P is None:
            P = 101325.0

        return {
            "fuel":      fuel,
            "oxidizer":  "air",
            "phi":       round(float(phi), 3),
            "T_initial": round(float(T), 1),
            "P_initial": round(float(P), 1),
        }
