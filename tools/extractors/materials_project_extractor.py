"""tools/extractors/materials_project_extractor.py — Extract Materials Project query from text."""
import re
from tools.extractors.base_extractor import BaseInputExtractor

# Common engineering materials and their formulas
_MATERIAL_FORMULAS: dict[str, str] = {
    "steel":        "Fe",
    "iron":         "Fe",
    "aluminum":     "Al",
    "aluminium":    "Al",
    "copper":       "Cu",
    "titanium":     "Ti",
    "nickel":       "Ni",
    "silicon":      "Si",
    "gold":         "Au",
    "silver":       "Ag",
    "tungsten":     "W",
    "zinc":         "Zn",
    "magnesium":    "Mg",
    "alumina":      "Al2O3",
    "silica":       "SiO2",
    "silicon carbide": "SiC",
    "titanium dioxide": "TiO2",
    "zirconia":     "ZrO2",
    "graphite":     "C",
    "diamond":      "C",
}

_FORMULA_RE = re.compile(
    r'\b([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?)*)\b'
)


class MaterialsProjectExtractor(BaseInputExtractor):
    solver_name = "materials_project"

    def extract(self, text: str, brief: str = "") -> dict | None:
        combined = brief + " " + text
        lower = combined.lower()

        # Check for MP ID
        mp_match = re.search(r'(mp-\d+)', combined, re.IGNORECASE)
        if mp_match:
            return {
                "query_type":  "by_material_id",
                "material_id": mp_match.group(1),
            }

        # Check for common material names
        formula = None
        for name, form in _MATERIAL_FORMULAS.items():
            if name in lower:
                formula = form
                break

        # Check for chemical formulas
        if formula is None:
            for match in _FORMULA_RE.finditer(combined):
                candidate = match.group(1)
                # Must have at least one uppercase letter followed by lowercase or digit
                if re.match(r'^[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*$', candidate):
                    if len(candidate) >= 2 and candidate not in ("In", "If", "It", "Is", "As", "At", "Or", "On", "An", "No", "So", "Do", "Be", "He", "We", "My"):
                        formula = candidate
                        break

        if formula:
            return {
                "query_type": "by_formula",
                "formula":    formula,
            }

        # Default fallback
        return {
            "query_type": "by_formula",
            "formula":    "Fe",
        }
