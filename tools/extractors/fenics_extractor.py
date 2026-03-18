"""tools/extractors/fenics_extractor.py — Extract FEniCS inputs from problem text."""
import re
from tools.extractors.base_extractor import BaseInputExtractor


class FenicsExtractor(BaseInputExtractor):
    solver_name = "fenics"

    def extract(self, text: str, brief: str = "") -> dict | None:
        combined = (brief + " " + text).lower()

        # Detect problem type
        problem_type = "beam_bending"
        if any(kw in combined for kw in ["heat", "thermal", "conduction", "temperature"]):
            problem_type = "heat_conduction"
        elif any(kw in combined for kw in ["modal", "vibration", "frequency", "natural freq"]):
            problem_type = "modal_analysis"
        elif any(kw in combined for kw in ["plate", "membrane", "shell"]):
            problem_type = "plate_stress"

        # Geometry extraction
        length = self._find_number(combined, [
            r'length\s*[=:]\s*([\d.]+)\s*m',
            r'span\s*[=:]\s*([\d.]+)\s*m',
            r'L\s*[=:]\s*([\d.]+)\s*m',
            r'([\d.]+)\s*m\s*(?:long|length|span)',
        ], default=1.0)

        width = self._find_number(combined, [
            r'width\s*[=:]\s*([\d.]+)\s*m',
            r'b\s*[=:]\s*([\d.]+)\s*m',
            r'([\d.]+)\s*m\s*wide',
        ], default=0.1)

        height = self._find_number(combined, [
            r'(?:height|thickness|depth)\s*[=:]\s*([\d.]+)\s*m',
            r'h\s*[=:]\s*([\d.]+)\s*m',
            r'([\d.]+)\s*(?:mm|cm)\s*(?:thick|height)',
        ], default=0.05)

        # Convert mm/cm to m if small values detected
        if height and height > 1.0:
            if height < 100:
                height /= 100.0  # cm to m
            else:
                height /= 1000.0  # mm to m

        # Material properties
        E = self._find_number(combined, [
            r"young'?s?\s+modulus\s*[=:]\s*([\d.]+)\s*GPa",
            r'E\s*[=:]\s*([\d.]+)\s*GPa',
            r'([\d.]+)\s*GPa\s*(?:modulus|stiffness)',
        ])
        if E:
            E *= 1e9  # GPa to Pa
        else:
            E = 210e9  # default steel

        sigma_yield = self._find_number(combined, [
            r'yield\s*(?:strength|stress)\s*[=:]\s*([\d.]+)\s*MPa',
            r'fy\s*[=:]\s*([\d.]+)\s*MPa',
            r'sigma_y\s*[=:]\s*([\d.]+)\s*MPa',
        ])
        if sigma_yield:
            sigma_yield *= 1e6  # MPa to Pa
        else:
            sigma_yield = 250e6  # default steel

        rho = self._find_number(combined, [
            r'density\s*[=:]\s*([\d.]+)\s*kg/m',
            r'rho\s*[=:]\s*([\d.]+)',
        ], default=7850.0)

        k_thermal = self._find_number(combined, [
            r'(?:thermal\s+)?conductivity\s*[=:]\s*([\d.]+)',
            r'k\s*[=:]\s*([\d.]+)\s*W/m',
        ], default=50.0)

        # Loads
        distributed = self._find_number(combined, [
            r'(?:distributed|uniform)\s+load\s*[=:]\s*([\d.]+)',
            r'q\s*[=:]\s*([\d.]+)\s*(?:N/m|kN/m)',
            r'([\d.]+)\s*(?:N/m2|Pa)\s*(?:load|pressure)',
        ], default=10000.0)

        point_load = self._find_number(combined, [
            r'point\s+load\s*[=:]\s*([\d.]+)',
            r'P\s*[=:]\s*([\d.]+)\s*(?:N|kN)',
            r'force\s*[=:]\s*([\d.]+)\s*(?:N|kN)',
        ])

        temperature = self._find_number(combined, [
            r'(?:boundary|surface)\s+temp[^=\n]*[=:]\s*([\d.]+)',
            r'T_w\s*[=:]\s*([\d.]+)',
            r'([\d.]+)\s*(?:K|C)\s*(?:boundary|wall|surface)',
        ], default=100.0)

        result = {
            "problem_type": problem_type,
            "geometry": {
                "length": round(float(length), 4),
                "width":  round(float(width), 4),
                "height": round(float(height), 4),
            },
            "material": {
                "E":           E,
                "sigma_yield": sigma_yield,
                "rho":         rho,
                "k":           k_thermal,
            },
            "loads": {},
        }

        if distributed:
            result["loads"]["distributed"] = float(distributed)
        if point_load:
            result["loads"]["point"] = float(point_load)
        if problem_type == "heat_conduction":
            result["loads"]["temperature"] = float(temperature)

        return result
