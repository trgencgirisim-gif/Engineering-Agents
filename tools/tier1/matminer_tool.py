"""tools/tier1/matminer_tool.py — Material property prediction via Matminer."""
import math
import re
from tools.base import BaseToolWrapper, ToolResult


# ---------------------------------------------------------------------------
# Lightweight composition parser (no external dependency)
# ---------------------------------------------------------------------------
_ELEMENT_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")

# Approximate elemental properties for analytical estimation
_ELEMENT_DATA = {
    # symbol: (atomic_mass, electronegativity_Pauling, atomic_radius_pm, group)
    "H":  (1.008,  2.20,  25,  1), "He": (4.003, 0.00,  31, 18),
    "Li": (6.941,  0.98, 152,  1), "Be": (9.012, 1.57, 112,  2),
    "B":  (10.81,  2.04,  87, 13), "C":  (12.01, 2.55,  77, 14),
    "N":  (14.01,  3.04,  75, 15), "O":  (16.00, 3.44,  73, 16),
    "F":  (19.00,  3.98,  72, 17), "Na": (22.99, 0.93, 186,  1),
    "Mg": (24.31,  1.31, 160,  2), "Al": (26.98, 1.61, 143, 13),
    "Si": (28.09,  1.90, 117, 14), "P":  (30.97, 2.19, 110, 15),
    "S":  (32.07,  2.58, 104, 16), "Cl": (35.45, 3.16,  99, 17),
    "K":  (39.10,  0.82, 227,  1), "Ca": (40.08, 1.00, 197,  2),
    "Ti": (47.87,  1.54, 147,  4), "V":  (50.94, 1.63, 134,  5),
    "Cr": (52.00,  1.66, 128,  6), "Mn": (54.94, 1.55, 127,  7),
    "Fe": (55.85,  1.83, 126,  8), "Co": (58.93, 1.88, 125,  9),
    "Ni": (58.69,  1.91, 124, 10), "Cu": (63.55, 1.90, 128, 11),
    "Zn": (65.38,  1.65, 134, 12), "Ga": (69.72, 1.81, 135, 13),
    "Ge": (72.63,  2.01, 122, 14), "As": (74.92, 2.18, 119, 15),
    "Se": (78.96,  2.55, 120, 16), "Br": (79.90, 2.96, 120, 17),
    "Sr": (87.62,  0.95, 215,  2), "Y":  (88.91, 1.22, 180,  3),
    "Zr": (91.22,  1.33, 160,  4), "Nb": (92.91, 1.60, 146,  5),
    "Mo": (95.96,  2.16, 139,  6), "Ru": (101.1, 2.20, 134,  8),
    "Rh": (102.9,  2.28, 134,  9), "Pd": (106.4, 2.20, 137, 10),
    "Ag": (107.9,  1.93, 144, 11), "Cd": (112.4, 1.69, 151, 12),
    "In": (114.8,  1.78, 167, 13), "Sn": (118.7, 1.96, 140, 14),
    "Sb": (121.8,  2.05, 145, 15), "Te": (127.6, 2.10, 142, 16),
    "Ba": (137.3,  0.89, 222,  2), "La": (138.9, 1.10, 187,  3),
    "W":  (183.8,  2.36, 139,  6), "Pt": (195.1, 2.28, 139, 10),
    "Au": (197.0,  2.54, 144, 11), "Pb": (207.2, 2.33, 175, 14),
    "Bi": (209.0,  2.02, 156, 15), "U":  (238.0, 1.38, 156,  3),
}


def _parse_formula(formula: str) -> dict[str, float]:
    """Parse a chemical formula string into {element: count}."""
    comp: dict[str, float] = {}
    for sym, num in _ELEMENT_RE.findall(formula):
        if sym:
            comp[sym] = comp.get(sym, 0.0) + (float(num) if num else 1.0)
    return comp


class MatminerTool(BaseToolWrapper):
    name    = "matminer"
    tier    = 1
    domains = ["malzeme"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "formula": {
                "type": "string",
                "description": "Chemical formula, e.g. 'Fe2O3', 'SiC', 'GaAs'",
            },
            "properties": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Properties to predict: band_gap, formation_energy, "
                    "density, electronegativity, atomic_radius"
                ),
            },
        },
        "required": ["formula"],
    }

    def _description(self) -> str:
        return (
            "Material property prediction using Matminer composition-based featurizers. "
            "Given a chemical formula, computes descriptors such as average electronegativity, "
            "atomic radius, estimated band gap, formation energy proxy, and density estimate. "
            "Use for rapid material screening or when composition-property relationships are needed."
        )

    def is_available(self) -> bool:
        try:
            import matminer  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            formula = inputs.get("formula", "")
            if not formula:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="", error="No formula provided",
                )

            requested = inputs.get("properties", [
                "band_gap", "formation_energy", "density",
                "electronegativity", "atomic_radius",
            ])

            comp = _parse_formula(formula)
            if not comp:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error=f"Could not parse formula: {formula}",
                )

            total_atoms = sum(comp.values())
            fractions = {el: n / total_atoms for el, n in comp.items()}

            # Weighted-average elemental features
            avg_en   = 0.0   # electronegativity
            avg_rad  = 0.0   # atomic radius (pm)
            avg_mass = 0.0
            en_range = 0.0
            known_elements = []

            for el, frac in fractions.items():
                props = _ELEMENT_DATA.get(el)
                if props is None:
                    continue
                mass, en, rad, grp = props
                known_elements.append(el)
                avg_en   += frac * en
                avg_rad  += frac * rad
                avg_mass += frac * mass

            if not known_elements:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error=f"No recognized elements in {formula}",
                )

            ens = [_ELEMENT_DATA[el][1] for el in known_elements if _ELEMENT_DATA[el][1] > 0]
            en_range = max(ens) - min(ens) if len(ens) > 1 else 0.0

            # ---------- property estimation ----------
            data  = {}
            units = {}
            assumptions = []

            if "electronegativity" in requested:
                data["avg_electronegativity"] = round(avg_en, 3)
                units["avg_electronegativity"] = "Pauling"

            if "atomic_radius" in requested:
                data["avg_atomic_radius_pm"] = round(avg_rad, 1)
                units["avg_atomic_radius_pm"] = "pm"

            if "band_gap" in requested:
                # Empirical: band gap correlates with electronegativity difference
                # and inversely with average metallic character
                # Simple model: Eg ~ 3.5 * (en_range / max_en) for semiconductors
                max_en = max(ens) if ens else 1.0
                eg_est = 3.5 * (en_range / max_en) if max_en > 0 else 0.0
                # Metals (small en_range) get ~0 gap
                if en_range < 0.3:
                    eg_est = 0.0
                data["band_gap_eV"] = round(eg_est, 2)
                units["band_gap_eV"] = "eV"
                assumptions.append(
                    "Band gap estimated from electronegativity difference heuristic"
                )

            if "formation_energy" in requested:
                # Rough proxy: negative for stable compounds, proportional to en difference
                # Miedema-like: dH ~ -k * (dEN)^2 * V^(2/3)
                V_avg = (avg_rad / 100.0) ** 3 * 4.0 / 3.0 * math.pi  # nm^3
                dH = -0.5 * en_range ** 2 * (V_avg * 1e21) ** (2.0 / 3.0)
                data["formation_energy_eV_per_atom"] = round(dH, 3)
                units["formation_energy_eV_per_atom"] = "eV/atom"
                assumptions.append(
                    "Formation energy estimated from Miedema-type electronegativity model"
                )

            if "density" in requested:
                # Estimate from average atomic mass and radius
                # rho ~ (mass * n_atoms) / (V_cell)
                # V_cell ~ (2 * r_avg)^3 for simple cubic packing
                r_m = avg_rad * 1e-12  # to metres
                V_atom = (2 * r_m) ** 3  # approximate unit cell volume per atom
                amu_kg = avg_mass * 1.66054e-27
                rho = amu_kg / V_atom if V_atom > 0 else 0.0
                data["density_kg_per_m3"] = round(rho, 0)
                data["density_g_per_cm3"] = round(rho / 1e3, 2)
                units["density_kg_per_m3"] = "kg/m3"
                units["density_g_per_cm3"] = "g/cm3"
                assumptions.append(
                    "Density estimated from atomic mass and radius with simple packing model"
                )

            data["n_elements"] = len(comp)
            data["composition"] = {el: round(frac, 4) for el, frac in fractions.items()}

            warnings = []
            unknown = set(comp.keys()) - set(known_elements)
            if unknown:
                warnings.append(
                    f"Elements {unknown} not in lookup table — excluded from averages"
                )

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data=data, units=units,
                raw_output=f"Matminer featurizer: {formula}, {len(comp)} elements, {total_atoms} atoms/fu",
                warnings=warnings,
                assumptions=assumptions or [
                    "Composition-weighted elemental feature averages",
                ],
            )

        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
