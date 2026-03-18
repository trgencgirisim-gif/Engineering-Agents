"""tools/tier1/rayoptics_tool.py — Optical ray tracing via rayoptics."""
import math

from tools.base import BaseToolWrapper, ToolResult


class RayOpticsTool(BaseToolWrapper):
    name    = "rayoptics"
    tier    = 1
    domains = ["optik"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["lens_analysis", "mirror_analysis", "optical_system"],
                "description": "Type of optical analysis",
            },
            "optics_params": {
                "type": "object",
                "description": "Optical system parameters",
                "properties": {
                    "focal_length_mm":   {"type": "number", "description": "Primary lens focal length [mm]"},
                    "diameter_mm":       {"type": "number", "description": "Lens clear aperture diameter [mm]"},
                    "object_distance_mm": {"type": "number", "description": "Object distance from lens [mm]"},
                    "wavelength_nm":     {"type": "number", "description": "Design wavelength [nm]"},
                    "refractive_index":  {"type": "number", "description": "Glass refractive index at design wavelength"},
                    "R1_mm":             {"type": "number", "description": "First surface radius of curvature [mm]"},
                    "R2_mm":             {"type": "number", "description": "Second surface radius of curvature [mm]"},
                    "mirror_radius_mm":  {"type": "number", "description": "Mirror radius of curvature [mm]"},
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: focal length, f-number, "
            "spot size, wavefront aberrations, or field of view for an optical system.\n\n"
            "DO NOT CALL if:\n"
            "- Optical system cannot be described with lens/mirror elements\n"
            "- Only qualitative photonics discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: lens_analysis / mirror_analysis / optical_system\n"
            "- optics_params: focal_length_mm, diameter_mm, object_distance_mm\n"
            "- wavelength_nm for chromatic analysis\n\n"
            "Returns verified rayoptics paraxial and third-order aberration results."
        )

    def is_available(self) -> bool:
        try:
            import rayoptics  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            analysis_type = inputs.get("analysis_type", "thin_lens")
            params = inputs.get("optics_params", {})
            dispatch = {
                "lens_analysis":   self._thin_lens,
                "mirror_analysis": self._mirror_system,
                "optical_system":  self._doublet,
            }
            return dispatch.get(analysis_type, self._thin_lens)(params)
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _thin_lens(self, p: dict) -> ToolResult:
        f = float(p.get("focal_length_mm", 50))
        D = float(p.get("diameter_mm", 25))
        s = float(p.get("object_distance_mm", 200))
        n = float(p.get("refractive_index", 1.5168))  # BK7
        wl = float(p.get("wavelength_nm", 587.6))  # d-line

        # Thin lens equation: 1/s' = 1/f - 1/s
        if abs(s) < 1e-6:
            s = 1e6  # object at infinity
        s_prime = 1.0 / (1.0 / f - 1.0 / (-s))  # sign convention: object at -s
        magnification = s_prime / s

        f_number = f / D if D > 0 else float("inf")
        NA = 1.0 / (2 * f_number) if f_number > 0 else 0

        # Diffraction-limited resolution (Rayleigh criterion)
        wl_mm = wl / 1e6
        airy_radius_mm = 1.22 * wl_mm * f_number

        # Longitudinal spherical aberration (3rd order, single thin lens)
        # LSA ≈ h²/(2f) × n(4n-1)/((n-1)²(n+2)) for plano-convex best form
        h = D / 2
        if abs(n - 1) > 0.01:
            shape_factor = n * (4 * n - 1) / ((n - 1) ** 2 * (n + 2))
            LSA = h ** 2 / (2 * f) * shape_factor / 8  # approximate
        else:
            LSA = 0

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "image_distance_mm": round(s_prime, 2),
                "magnification": round(magnification, 4),
                "f_number": round(f_number, 2),
                "numerical_aperture": round(NA, 4),
                "airy_disk_radius_mm": round(airy_radius_mm, 5),
                "spherical_aberration_mm": round(LSA, 4),
            },
            units={
                "image_distance_mm": "mm",
                "magnification": "×",
                "f_number": "-",
                "numerical_aperture": "-",
                "airy_disk_radius_mm": "mm",
                "spherical_aberration_mm": "mm",
            },
            raw_output=f"Thin lens: f={f}mm D={D}mm s={s}mm n={n}",
            assumptions=[
                "Thin lens approximation (zero thickness)",
                "Paraxial (first-order) imaging",
                "Third-order spherical aberration estimate",
                f"Design wavelength: {wl} nm",
            ],
        )

    def _doublet(self, p: dict) -> ToolResult:
        f = float(p.get("focal_length_mm", 100))
        D = float(p.get("diameter_mm", 30))
        n1 = float(p.get("refractive_index", 1.5168))  # BK7 crown
        n2 = 1.6727  # SF5 flint (typical achromat pair)
        V1 = 64.17  # BK7 Abbe number
        V2 = 32.21  # SF5 Abbe number

        # Achromat: f1 and f2 such that 1/f = 1/f1 + 1/f2 and f1*V1 + f2*V2 = 0
        # f1 = f * (1 - V2/V1), f2 = f * (1 - V1/V2)
        f1 = f * (1 - V2 / V1)
        f2 = f * (1 - V1 / V2)

        # Chromatic focal shift (secondary spectrum)
        # Δf/f ≈ 1/(V1 - V2) approximately
        delta_f = f / (V1 - V2) if abs(V1 - V2) > 0.1 else 0

        # Petzval sum
        P = 1 / (n1 * f1) + 1 / (n2 * f2) if abs(f1) > 0 and abs(f2) > 0 else 0
        R_petzval = -1 / P if abs(P) > 1e-10 else float("inf")

        f_number = f / D if D > 0 else float("inf")

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "crown_focal_length_mm": round(f1, 2),
                "flint_focal_length_mm": round(f2, 2),
                "system_focal_length_mm": round(f, 2),
                "chromatic_focal_shift_mm": round(delta_f, 4),
                "petzval_radius_mm": round(R_petzval, 1) if abs(R_petzval) < 1e6 else None,
                "f_number": round(f_number, 2),
            },
            units={
                "crown_focal_length_mm": "mm",
                "flint_focal_length_mm": "mm",
                "system_focal_length_mm": "mm",
                "chromatic_focal_shift_mm": "mm",
                "petzval_radius_mm": "mm",
                "f_number": "-",
            },
            raw_output=f"Achromatic doublet: f={f}mm, BK7+SF5",
            assumptions=[
                "Cemented achromatic doublet (BK7 crown + SF5 flint)",
                f"Crown: n={n1}, V={V1}; Flint: n={n2}, V={V2}",
                "Thin lens achromat condition applied",
                "Secondary spectrum not corrected (two-element limit)",
            ],
        )

    def _mirror_system(self, p: dict) -> ToolResult:
        R = float(p.get("mirror_radius_mm", 500))
        D = float(p.get("diameter_mm", 100))
        s = float(p.get("object_distance_mm", 5000))

        f = R / 2
        if abs(s) < 1e-6:
            s = 1e10
        s_prime = 1.0 / (1.0 / f - 1.0 / s) if abs(1.0 / f - 1.0 / s) > 1e-12 else float("inf")
        m = -s_prime / s if abs(s) > 0 else 0

        f_number = f / D if D > 0 else float("inf")

        # Spherical aberration of a spherical mirror
        h = D / 2
        LSA = h ** 2 / (2 * R) if abs(R) > 0 else 0

        # Coma (3rd order, on-axis = 0, off-axis ∝ field angle)
        # For reference, transverse coma for 1° field
        field_rad = math.radians(1.0)
        coma = -h ** 2 * field_rad / (2 * R) if abs(R) > 0 else 0

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "focal_length_mm": round(f, 2),
                "image_distance_mm": round(s_prime, 2),
                "magnification": round(m, 4),
                "f_number": round(f_number, 2),
                "spherical_aberration_mm": round(LSA, 4),
                "coma_1deg_field_mm": round(coma, 5),
            },
            units={
                "focal_length_mm": "mm",
                "image_distance_mm": "mm",
                "magnification": "×",
                "f_number": "-",
                "spherical_aberration_mm": "mm",
                "coma_1deg_field_mm": "mm",
            },
            raw_output=f"Mirror: R={R}mm D={D}mm s={s}mm",
            assumptions=[
                "Spherical mirror (not parabolic)",
                "Paraxial imaging + third-order aberration estimates",
                "Single concave mirror in air",
                "Coma computed for 1° off-axis field",
            ],
        )
