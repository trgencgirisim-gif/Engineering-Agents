"""tools/tier1/materials_project_tool.py — Material properties via Materials Project API."""
import os
from tools.base import BaseToolWrapper, ToolResult


class MaterialsProjectTool(BaseToolWrapper):
    name    = "materials_project"
    tier    = 1
    domains = ["malzeme", "yapisal", "termal", "elektrik"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["by_formula", "by_material_id", "by_elements"],
            },
            "formula":     {"type": "string",
                            "description": "Chemical formula: Fe, Al2O3, TiO2, SiC, etc."},
            "material_id": {"type": "string",
                            "description": "Materials Project ID: mp-13, mp-19175, etc."},
            "elements":    {"type": "array", "items": {"type": "string"},
                            "description": "Element list: ['Ti', 'Al', 'V']"},
        },
        "required": ["query_type"],
    }

    def _description(self) -> str:
        return (
            "Retrieves DFT-computed material properties from the Materials Project database. "
            "Query by chemical formula, MP ID, or element list. "
            "Returns: density, band gap, bulk modulus, shear modulus, energy per atom. "
            "Requires MP_API_KEY in environment. "
            "Use for material selection, property verification, or structural analysis inputs."
        )

    def is_available(self) -> bool:
        try:
            from mp_api.client import MPRester  # noqa: F401
            return bool(os.getenv("MP_API_KEY"))
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            from mp_api.client import MPRester

            key        = os.getenv("MP_API_KEY")
            query_type = inputs["query_type"]
            fields     = [
                "formula_pretty", "density", "band_gap",
                "bulk_modulus", "shear_modulus", "energy_per_atom",
            ]

            with MPRester(key) as mpr:
                if query_type == "by_formula":
                    results = mpr.materials.summary.search(
                        formula=inputs.get("formula"), fields=fields)
                elif query_type == "by_material_id":
                    results = [mpr.materials.summary.get_data_by_id(
                        inputs["material_id"], fields=fields)]
                else:
                    results = mpr.materials.summary.search(
                        elements=inputs.get("elements", []), fields=fields)

            if not results:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="No materials found for the given query",
                )

            # Select most stable structure (lowest energy per atom)
            best = min(results,
                       key=lambda r: getattr(r, "energy_per_atom", 0) or 0)

            data: dict = {}
            units: dict = {}
            prop_units = {
                "density":         "g/cm3",
                "band_gap":        "eV",
                "energy_per_atom": "eV/atom",
            }

            for field in fields:
                val = getattr(best, field, None)
                if val is None:
                    continue
                if hasattr(val, "vrh"):
                    data[f"{field}_vrh_GPa"]  = round(float(val.vrh) / 1e9, 3)
                    units[f"{field}_vrh_GPa"] = "GPa"
                elif isinstance(val, (int, float)):
                    data[field]  = round(float(val), 6)
                    units[field] = prop_units.get(field, "-")
                else:
                    data[field]  = str(val)
                    units[field] = "-"

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data=data, units=units,
                raw_output=f"Materials Project: {query_type}",
                assumptions=["DFT values at 0 K for pure, defect-free material"],
                warnings=[
                    "Real alloy properties depend on composition, heat treatment, "
                    "and microstructure — DFT values are reference baselines only."
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
