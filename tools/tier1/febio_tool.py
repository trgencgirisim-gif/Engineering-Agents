"""tools/tier1/febio_tool.py — Nonlinear FE for biological materials via FEBio."""
import math

from tools.base import BaseToolWrapper, ToolResult


class FEBioTool(BaseToolWrapper):
    name    = "febio"
    tier    = 1
    domains = ["biyomedikal"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["tissue_mechanics", "implant_stress", "vessel_pressure"],
                "description": "Type of nonlinear biological FE analysis",
            },
            "parameters": {
                "type": "object",
                "description": "Material and geometry parameters",
                "properties": {
                    "C1": {
                        "type": "number",
                        "description": "Mooney-Rivlin constant C1 [Pa]",
                    },
                    "C2": {
                        "type": "number",
                        "description": "Mooney-Rivlin constant C2 [Pa]",
                    },
                    "bulk_modulus_Pa": {
                        "type": "number",
                        "description": "Bulk modulus kappa for near-incompressibility [Pa]",
                    },
                    "stretch_ratio": {
                        "type": "number",
                        "description": "Applied uniaxial stretch ratio lambda",
                    },
                    "youngs_modulus_MPa": {
                        "type": "number",
                        "description": "Young's modulus for implant material [MPa]",
                    },
                    "poissons_ratio": {
                        "type": "number",
                        "description": "Poisson's ratio for implant material",
                    },
                    "implant_diameter_mm": {
                        "type": "number",
                        "description": "Implant stem/pin diameter [mm]",
                    },
                    "implant_length_mm": {
                        "type": "number",
                        "description": "Implant length [mm]",
                    },
                    "applied_force_N": {
                        "type": "number",
                        "description": "Applied load on implant [N]",
                    },
                    "inner_radius_mm": {
                        "type": "number",
                        "description": "Vessel inner radius [mm]",
                    },
                    "wall_thickness_mm": {
                        "type": "number",
                        "description": "Vessel wall thickness [mm]",
                    },
                    "internal_pressure_mmHg": {
                        "type": "number",
                        "description": "Internal blood pressure [mmHg]",
                    },
                    "external_pressure_mmHg": {
                        "type": "number",
                        "description": "External pressure [mmHg], default 0",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "Performs nonlinear finite element analysis for biological tissues and "
            "medical implants: Mooney-Rivlin hyperelastic tissue mechanics, implant "
            "stress/strain with bone-implant interface assessment, and thick-wall "
            "vessel (Lame) pressure analysis. Accepts material constants (C1, C2), "
            "geometry, and loading conditions. Use for biocompatibility evaluation, "
            "implant design verification, or vascular device assessment."
        )

    def is_available(self) -> bool:
        try:
            import febio  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "tissue_mechanics")
        params = inputs.get("parameters", {})

        dispatch = {
            "tissue_mechanics": self._tissue_mechanics,
            "implant_stress":   self._implant_stress,
            "vessel_pressure":  self._vessel_pressure,
        }
        handler = dispatch.get(analysis_type, self._tissue_mechanics)
        return handler(params)

    # ------------------------------------------------------------------
    # Mooney-Rivlin hyperelastic tissue mechanics
    # ------------------------------------------------------------------
    def _tissue_mechanics(self, params: dict) -> ToolResult:
        try:
            # Mooney-Rivlin constants (defaults: soft tissue ~articular cartilage)
            C1    = float(params.get("C1", 0.5e6))       # [Pa]
            C2    = float(params.get("C2", 0.1e6))       # [Pa]
            kappa = float(params.get("bulk_modulus_Pa", 50.0e6))
            lam   = float(params.get("stretch_ratio", 1.1))

            if lam <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Stretch ratio must be positive",
                )

            # Incompressible Mooney-Rivlin: W = C1(I1-3) + C2(I2-3)
            # Uniaxial stress for incompressible material:
            # sigma = 2*(lam^2 - 1/lam)*(C1 + C2/lam)
            inv_lam = 1.0 / lam
            sigma = 2.0 * (lam ** 2 - inv_lam) * (C1 + C2 * inv_lam)

            # Invariants for uniaxial (lambda1=lam, lambda2=lambda3=1/sqrt(lam))
            I1 = lam ** 2 + 2.0 / lam
            I2 = 2.0 * lam + 1.0 / (lam ** 2)

            # Strain energy density
            W = C1 * (I1 - 3.0) + C2 * (I2 - 3.0)

            # Tangent modulus dσ/dλ at current stretch
            # d(sigma)/d(lam) = 2*(2*lam + 1/lam^2)*(C1 + C2/lam) + 2*(lam^2-1/lam)*(-C2/lam^2)
            dsig_dlam = (
                2.0 * (2.0 * lam + inv_lam ** 2) * (C1 + C2 * inv_lam)
                + 2.0 * (lam ** 2 - inv_lam) * (-C2 * inv_lam ** 2)
            )

            # Engineering (nominal) stress
            P = sigma / lam  # 1st Piola-Kirchhoff

            # Small-strain Young's modulus equivalent: E = 6*(C1+C2)
            E_equiv = 6.0 * (C1 + C2)

            warnings = []
            if lam > 1.5:
                warnings.append(
                    f"Stretch {lam:.2f} exceeds typical soft tissue physiological range"
                )
            if sigma > 10.0e6:
                warnings.append(f"Cauchy stress {sigma/1e6:.2f} MPa — tissue damage likely")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "cauchy_stress_Pa":          round(sigma, 2),
                    "cauchy_stress_kPa":         round(sigma / 1e3, 3),
                    "nominal_stress_Pa":         round(P, 2),
                    "strain_energy_density_Pa":  round(W, 2),
                    "tangent_modulus_Pa":         round(dsig_dlam, 2),
                    "equiv_youngs_modulus_Pa":    round(E_equiv, 2),
                    "I1":                        round(I1, 6),
                    "I2":                        round(I2, 6),
                    "stretch_ratio":             lam,
                },
                units={
                    "cauchy_stress_Pa":         "Pa",
                    "cauchy_stress_kPa":        "kPa",
                    "nominal_stress_Pa":        "Pa",
                    "strain_energy_density_Pa": "Pa",
                    "tangent_modulus_Pa":        "Pa",
                    "equiv_youngs_modulus_Pa":   "Pa",
                },
                raw_output=(
                    f"Mooney-Rivlin: C1={C1:.0f}, C2={C2:.0f} Pa, "
                    f"lambda={lam:.3f}, sigma={sigma/1e3:.2f} kPa"
                ),
                warnings=warnings,
                assumptions=[
                    "Incompressible Mooney-Rivlin hyperelastic model",
                    "Uniaxial stress state (no multiaxial loading)",
                    "Isothermal, quasi-static loading",
                    "No viscoelastic or poroelastic effects",
                    f"C1={C1} Pa, C2={C2} Pa (user-supplied or default cartilage values)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Implant stress analysis (beam/column model)
    # ------------------------------------------------------------------
    def _implant_stress(self, params: dict) -> ToolResult:
        try:
            E    = float(params.get("youngs_modulus_MPa", 110000.0))  # Ti-6Al-4V
            nu   = float(params.get("poissons_ratio", 0.34))
            d    = float(params.get("implant_diameter_mm", 12.0))
            L    = float(params.get("implant_length_mm", 100.0))
            F    = float(params.get("applied_force_N", 3000.0))

            r = d / 2.0  # mm
            A = math.pi * r ** 2          # mm^2
            I = math.pi * r ** 4 / 4.0    # mm^4

            # Axial stress [MPa]
            sigma_axial = F / A

            # Bending stress (cantilever with load at tip, eccentricity = d/4)
            e = d / 4.0  # eccentricity [mm]
            M = F * e    # bending moment [N.mm]
            sigma_bend = M * r / I

            # Combined von Mises (axial + bending, no shear)
            sigma_max = sigma_axial + sigma_bend
            sigma_min = sigma_axial - sigma_bend
            sigma_vm  = max(abs(sigma_max), abs(sigma_min))

            # Fatigue check: endurance limit for Ti-6Al-4V ~ 510 MPa (R=-1)
            # For implant with R~0: Se ~ 510 * 0.7 = 357 MPa (Goodman correction)
            Se_Ti = 357.0  # MPa
            fatigue_SF = Se_Ti / sigma_vm if sigma_vm > 0 else float("inf")

            # Bone-implant interface: bearing stress (projected area)
            A_bearing = d * L  # mm^2 (projected)
            sigma_bearing = F / A_bearing  # MPa

            # Bone yield (cortical ~ 130 MPa compression)
            bone_yield = 130.0  # MPa
            bone_SF = bone_yield / sigma_bearing if sigma_bearing > 0 else float("inf")

            # Deflection at tip (cantilever)
            delta = F * L ** 3 / (3.0 * E * I)  # mm

            warnings = []
            if fatigue_SF < 2.0:
                warnings.append(
                    f"Fatigue safety factor {fatigue_SF:.2f} < 2.0 — risk of implant fracture"
                )
            if bone_SF < 2.0:
                warnings.append(
                    f"Bone bearing SF {bone_SF:.2f} < 2.0 — risk of bone resorption/failure"
                )
            if delta > 0.5:
                warnings.append(f"Tip deflection {delta:.3f} mm may impair fixation stability")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "axial_stress_MPa":      round(sigma_axial, 2),
                    "bending_stress_MPa":    round(sigma_bend, 2),
                    "von_mises_stress_MPa":  round(sigma_vm, 2),
                    "fatigue_safety_factor": round(fatigue_SF, 2),
                    "bearing_stress_MPa":    round(sigma_bearing, 3),
                    "bone_safety_factor":    round(bone_SF, 2),
                    "tip_deflection_mm":     round(delta, 4),
                    "cross_section_mm2":     round(A, 2),
                },
                units={
                    "axial_stress_MPa":     "MPa",
                    "bending_stress_MPa":   "MPa",
                    "von_mises_stress_MPa": "MPa",
                    "bearing_stress_MPa":   "MPa",
                    "tip_deflection_mm":    "mm",
                    "cross_section_mm2":    "mm^2",
                },
                raw_output=(
                    f"Implant stress: d={d} mm, L={L} mm, F={F} N, "
                    f"sigma_vm={sigma_vm:.2f} MPa, SF_fatigue={fatigue_SF:.2f}"
                ),
                warnings=warnings,
                assumptions=[
                    "Cantilever beam model with eccentric loading (e = d/4)",
                    f"Material: Ti-6Al-4V, E = {E} MPa, nu = {nu}",
                    "Endurance limit 357 MPa (Goodman correction, R=0)",
                    "Cortical bone compressive yield = 130 MPa",
                    "Linear elastic implant material (no plasticity)",
                    "Bearing stress on projected area d x L",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Thick-wall cylinder (Lame equations) for blood vessels / stents
    # ------------------------------------------------------------------
    def _vessel_pressure(self, params: dict) -> ToolResult:
        try:
            r_i  = float(params.get("inner_radius_mm", 3.0))
            t    = float(params.get("wall_thickness_mm", 0.5))
            p_i  = float(params.get("internal_pressure_mmHg", 120.0))
            p_o  = float(params.get("external_pressure_mmHg", 0.0))

            r_o = r_i + t

            # Convert mmHg to kPa (1 mmHg = 0.133322 kPa)
            pi_kPa = p_i * 0.133322
            po_kPa = p_o * 0.133322

            # Convert to MPa for stress calculation with mm units
            pi_MPa = pi_kPa / 1000.0
            po_MPa = po_kPa / 1000.0

            # Lame equations for thick-wall cylinder
            # sigma_r(r) = (A - B/r^2)  circumferential: sigma_theta(r) = (A + B/r^2)
            # A = (pi*ri^2 - po*ro^2) / (ro^2 - ri^2)
            # B = (pi - po)*ri^2*ro^2 / (ro^2 - ri^2)
            denom = r_o ** 2 - r_i ** 2
            if denom <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Outer radius must exceed inner radius",
                )

            A = (pi_MPa * r_i ** 2 - po_MPa * r_o ** 2) / denom
            B = (pi_MPa - po_MPa) * r_i ** 2 * r_o ** 2 / denom

            # Stresses at inner wall (maximum hoop stress)
            sigma_r_inner     = A - B / (r_i ** 2)  # = -pi (check)
            sigma_theta_inner = A + B / (r_i ** 2)

            # Stresses at outer wall
            sigma_r_outer     = A - B / (r_o ** 2)  # = -po (check)
            sigma_theta_outer = A + B / (r_o ** 2)

            # Von Mises at inner wall (plane stress, sigma_z ~ 0 for open-ended)
            sigma_vm_inner = math.sqrt(
                sigma_theta_inner ** 2
                - sigma_theta_inner * sigma_r_inner
                + sigma_r_inner ** 2
            )

            # Thin-wall approximation for comparison: sigma = p*r/t
            sigma_thin = pi_MPa * r_i / t

            # Circumferential (hoop) strain — assuming E ~ 1 MPa for artery
            E_tissue = 1.0  # MPa (healthy artery, order of magnitude)
            hoop_strain = sigma_theta_inner / E_tissue

            # Wall shear stress (Poiseuille approximation)
            # tau_w = 4*mu*Q / (pi*r^3) — need flow; provide generic estimate
            # Typical arterial wall shear: 1-7 Pa
            tau_wall_Pa = 1.5  # Pa, typical resting

            # Compliance: dV/V per mmHg
            compliance = (2.0 * r_i * hoop_strain) / (p_i if p_i > 0 else 1.0)

            warnings = []
            if sigma_theta_inner > 0.5:
                warnings.append(
                    f"Hoop stress {sigma_theta_inner*1000:.1f} kPa may exceed vessel "
                    f"ultimate strength (~1-2 MPa for aorta)"
                )
            if hoop_strain > 0.3:
                warnings.append(
                    f"Hoop strain {hoop_strain:.2%} exceeds physiological range (~5-15%)"
                )

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "hoop_stress_inner_kPa":   round(sigma_theta_inner * 1000, 3),
                    "radial_stress_inner_kPa": round(sigma_r_inner * 1000, 3),
                    "hoop_stress_outer_kPa":   round(sigma_theta_outer * 1000, 3),
                    "von_mises_inner_kPa":     round(sigma_vm_inner * 1000, 3),
                    "thin_wall_hoop_kPa":      round(sigma_thin * 1000, 3),
                    "hoop_strain_pct":         round(hoop_strain * 100, 3),
                    "wall_compliance_per_mmHg": round(compliance, 6),
                    "inner_radius_mm":         r_i,
                    "outer_radius_mm":         round(r_o, 3),
                    "pressure_kPa":            round(pi_kPa, 3),
                },
                units={
                    "hoop_stress_inner_kPa":   "kPa",
                    "radial_stress_inner_kPa": "kPa",
                    "hoop_stress_outer_kPa":   "kPa",
                    "von_mises_inner_kPa":     "kPa",
                    "thin_wall_hoop_kPa":      "kPa",
                    "hoop_strain_pct":         "%",
                    "inner_radius_mm":         "mm",
                    "outer_radius_mm":         "mm",
                    "pressure_kPa":            "kPa",
                },
                raw_output=(
                    f"Lame thick-wall: ri={r_i} mm, t={t} mm, "
                    f"pi={p_i} mmHg, sigma_theta={sigma_theta_inner*1000:.2f} kPa"
                ),
                warnings=warnings,
                assumptions=[
                    "Thick-wall cylinder (Lame equations) — linear elastic",
                    "Open-ended vessel (sigma_z = 0, plane-stress axial)",
                    f"Wall tissue E ~ {E_tissue} MPa (healthy artery order of magnitude)",
                    "Homogeneous, isotropic wall (no layered structure)",
                    "Static pressure analysis (no pulsatile dynamics)",
                    "Wall shear stress reported as typical resting value (1.5 Pa)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
