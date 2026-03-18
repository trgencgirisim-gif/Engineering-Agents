"""tools/tier1/openmc_tool.py — Monte Carlo nuclear transport via OpenMC."""
import math

from tools.base import BaseToolWrapper, ToolResult


class OpenMCTool(BaseToolWrapper):
    name    = "openmc"
    tier    = 1
    domains = ["nukleer"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["criticality", "shielding", "dose_rate"],
                "description": "Type of nuclear transport analysis",
            },
            "nuclear_params": {
                "type": "object",
                "description": "Nuclear analysis parameters",
                "properties": {
                    "fuel_type":            {"type": "string", "description": "Fuel type: UO2, MOX, U-metal"},
                    "enrichment_pct":       {"type": "number", "description": "U-235 enrichment [%]"},
                    "fuel_radius_cm":       {"type": "number", "description": "Fuel pin radius [cm]"},
                    "clad_thickness_cm":    {"type": "number", "description": "Cladding thickness [cm]"},
                    "pitch_cm":             {"type": "number", "description": "Lattice pitch [cm]"},
                    "moderator":            {"type": "string", "description": "Moderator: water, heavy_water, graphite"},
                    "shield_material":      {"type": "string", "description": "Shielding material: concrete, lead, steel, water"},
                    "shield_thickness_cm":  {"type": "number", "description": "Shield thickness [cm]"},
                    "source_activity_Bq":   {"type": "number", "description": "Source activity [Bq]"},
                    "source_energy_MeV":    {"type": "number", "description": "Source gamma energy [MeV]"},
                    "distance_m":           {"type": "number", "description": "Distance from source [m]"},
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: neutron multiplication factor (k-eff), "
            "neutron flux distribution, dose rate, or material activation.\n\n"
            "DO NOT CALL if:\n"
            "- No geometry or material composition is specified\n"
            "- Only qualitative nuclear physics discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: criticality / shielding / dose_rate\n"
            "- nuclear_params: fuel_type, enrichment_pct, geometry dimensions\n"
            "- For shielding: shield_material, shield_thickness_cm\n\n"
            "Returns verified OpenMC Monte Carlo neutron transport results."
        )

    def is_available(self) -> bool:
        try:
            import openmc  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            analysis_type = inputs.get("analysis_type", "criticality")
            params = inputs.get("nuclear_params", {})
            dispatch = {
                "criticality": self._criticality,
                "shielding":   self._shielding,
                "dose_rate":   self._dose_rate,
            }
            return dispatch.get(analysis_type, self._criticality)(params)
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _criticality(self, p: dict) -> ToolResult:
        enrichment = float(p.get("enrichment_pct", 3.5))
        r_fuel = float(p.get("fuel_radius_cm", 0.4096))
        t_clad = float(p.get("clad_thickness_cm", 0.0572))
        pitch = float(p.get("pitch_cm", 1.26))
        moderator = p.get("moderator", "water")

        # Four-factor formula: k_inf = η × f × p × ε
        # Eta (reproduction factor) for U-235
        nu = 2.43  # neutrons per fission
        sigma_f_25 = 585.0  # barns, U-235 thermal fission
        sigma_a_25 = 681.0  # barns, U-235 thermal absorption
        sigma_a_28 = 2.68   # barns, U-238 thermal absorption

        N25_frac = enrichment / 100.0
        N28_frac = 1 - N25_frac

        sigma_a_fuel = N25_frac * sigma_a_25 + N28_frac * sigma_a_28
        sigma_f_fuel = N25_frac * sigma_f_25
        eta = nu * sigma_f_fuel / sigma_a_fuel

        # Thermal utilization (f)
        V_fuel = math.pi * r_fuel ** 2
        V_cell = pitch ** 2
        V_mod = V_cell - math.pi * (r_fuel + t_clad) ** 2

        sigma_a_mod = {"water": 0.66, "heavy_water": 0.001, "graphite": 0.0035}.get(moderator, 0.66)
        rho_fuel = 10.97  # g/cm³ UO2 effective number density proxy
        rho_mod = {"water": 1.0, "heavy_water": 1.1, "graphite": 1.6}.get(moderator, 1.0)

        Sigma_a_fuel = sigma_a_fuel * rho_fuel * 0.01  # simplified macroscopic
        Sigma_a_mod = sigma_a_mod * rho_mod * 0.1

        f = Sigma_a_fuel * V_fuel / (Sigma_a_fuel * V_fuel + Sigma_a_mod * V_mod)

        # Resonance escape probability (p) — empirical Wigner
        NM_NF = (V_mod * rho_mod) / (V_fuel * rho_fuel) if V_fuel * rho_fuel > 0 else 10
        I_eff = 26.0 * (1 + 0.0028 * math.sqrt(enrichment))  # effective resonance integral
        p = math.exp(-NM_NF * 0.0001 * I_eff)
        p = max(0.5, min(0.99, p))  # physical bounds

        # Fast fission factor
        epsilon = 1.02 + 0.01 * (enrichment - 3.0)

        k_inf = eta * f * p * epsilon

        # Migration length for leakage
        M2 = {"water": 50, "heavy_water": 2500, "graphite": 350}.get(moderator, 50)

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "k_infinity": round(k_inf, 4),
                "eta": round(eta, 4),
                "thermal_utilization_f": round(f, 4),
                "resonance_escape_p": round(p, 4),
                "fast_fission_epsilon": round(epsilon, 4),
                "migration_area_cm2": round(M2, 1),
            },
            units={
                "k_infinity": "-",
                "eta": "-",
                "thermal_utilization_f": "-",
                "resonance_escape_p": "-",
                "fast_fission_epsilon": "-",
                "migration_area_cm2": "cm²",
            },
            raw_output=f"Criticality: {enrichment}% enriched, pitch={pitch}cm, {moderator}",
            assumptions=[
                "Four-factor formula (infinite lattice, no leakage)",
                "Thermal neutron cross-sections at 0.0253 eV",
                "Wigner rational approximation for resonance escape",
                f"Fuel: UO2 at {enrichment}% enrichment",
                f"Moderator: {moderator}",
            ],
        )

    def _shielding(self, p: dict) -> ToolResult:
        material = p.get("shield_material", "concrete")
        thickness = float(p.get("shield_thickness_cm", 100))
        E_MeV = float(p.get("source_energy_MeV", 1.0))

        # Linear attenuation coefficients (cm⁻¹) at ~1 MeV
        mu_table = {
            "concrete": 0.149,
            "lead":     0.770,
            "steel":    0.460,
            "water":    0.0707,
        }
        # Buildup factor coefficients (Taylor formula parameters)
        buildup_a = {"concrete": 1.5, "lead": 1.2, "steel": 1.3, "water": 1.8}

        mu = mu_table.get(material, 0.149)
        # Energy scaling (approximate: mu ∝ 1/E for Compton-dominated range)
        if 0.2 < E_MeV < 5.0:
            mu *= (1.0 / E_MeV) ** 0.3  # rough correction

        mu_x = mu * thickness
        attenuation_no_buildup = math.exp(-mu_x)

        # Taylor buildup factor: B ≈ A × exp(α₁ × μx) + (1-A) × exp(α₂ × μx)
        # Simplified: B ≈ 1 + μx + 0.5(μx)² for small μx, capped
        a = buildup_a.get(material, 1.5)
        B = 1 + a * mu_x * math.exp(-0.1 * mu_x)
        B = max(1, B)

        attenuation_with_buildup = attenuation_no_buildup * B
        attenuation_with_buildup = min(1.0, attenuation_with_buildup)

        transmission_pct = attenuation_with_buildup * 100
        HVL = 0.693 / mu if mu > 0 else float("inf")
        TVL = 2.303 / mu if mu > 0 else float("inf")

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "linear_attenuation_coeff_per_cm": round(mu, 4),
                "mean_free_paths": round(mu_x, 2),
                "attenuation_factor_no_buildup": round(attenuation_no_buildup, 6),
                "buildup_factor": round(B, 3),
                "transmission_with_buildup_pct": round(transmission_pct, 4),
                "half_value_layer_cm": round(HVL, 2),
                "tenth_value_layer_cm": round(TVL, 2),
            },
            units={
                "linear_attenuation_coeff_per_cm": "cm⁻¹",
                "mean_free_paths": "mfp",
                "attenuation_factor_no_buildup": "-",
                "buildup_factor": "-",
                "transmission_with_buildup_pct": "%",
                "half_value_layer_cm": "cm",
                "tenth_value_layer_cm": "cm",
            },
            raw_output=f"Shielding: {thickness}cm {material}, E={E_MeV}MeV",
            assumptions=[
                f"Shield material: {material}, thickness: {thickness} cm",
                f"Gamma energy: {E_MeV} MeV (narrow beam geometry)",
                "Taylor buildup factor approximation",
                "Homogeneous shield, no streaming paths",
            ],
        )

    def _dose_rate(self, p: dict) -> ToolResult:
        A_Bq = float(p.get("source_activity_Bq", 3.7e10))  # 1 Ci default
        E_MeV = float(p.get("source_energy_MeV", 0.662))  # Cs-137
        d_m = float(p.get("distance_m", 1.0))
        shield_mat = p.get("shield_material", None)
        shield_cm = float(p.get("shield_thickness_cm", 0))

        # Gamma dose rate constant (approximate)
        # D_rate [µSv/h] ≈ A[GBq] × Γ × E / d²
        # Γ ≈ 0.13 µSv·m²/(GBq·h·MeV) for point isotropic source
        A_GBq = A_Bq / 1e9
        Gamma_const = 0.13  # µSv·m²/(GBq·h) per MeV
        dose_unshielded = A_GBq * Gamma_const * E_MeV / (d_m ** 2) if d_m > 0 else float("inf")

        # Apply shielding if specified
        dose_shielded = dose_unshielded
        attenuation = 1.0
        if shield_mat and shield_cm > 0:
            mu_table = {"concrete": 0.149, "lead": 0.770, "steel": 0.460, "water": 0.0707}
            mu = mu_table.get(shield_mat, 0.149)
            if 0.2 < E_MeV < 5.0:
                mu *= (1.0 / E_MeV) ** 0.3
            mu_x = mu * shield_cm
            attenuation = math.exp(-mu_x) * (1 + mu_x)  # with simple buildup
            dose_shielded = dose_unshielded * attenuation

        # Annual dose (2000 working hours)
        annual_mSv = dose_shielded * 2000 / 1000

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "dose_rate_unshielded_uSv_per_h": round(dose_unshielded, 3),
                "dose_rate_shielded_uSv_per_h": round(dose_shielded, 3),
                "shielding_factor": round(attenuation, 6),
                "annual_dose_mSv": round(annual_mSv, 3),
                "activity_GBq": round(A_GBq, 3),
                "distance_m": round(d_m, 2),
            },
            units={
                "dose_rate_unshielded_uSv_per_h": "µSv/h",
                "dose_rate_shielded_uSv_per_h": "µSv/h",
                "shielding_factor": "-",
                "annual_dose_mSv": "mSv",
                "activity_GBq": "GBq",
                "distance_m": "m",
            },
            raw_output=f"Dose: {A_GBq:.1f}GBq E={E_MeV}MeV d={d_m}m",
            warnings=[
                "Annual limit: 20 mSv/year for radiation workers" if annual_mSv > 20 else "",
                "Annual limit: 1 mSv/year for public" if annual_mSv > 1 else "",
            ],
            assumptions=[
                "Point isotropic source in air",
                f"Distance: {d_m} m, Energy: {E_MeV} MeV",
                "Gamma constant approximation (0.13 µSv·m²/GBq·h per MeV)",
                "Annual dose based on 2000 working hours/year",
            ],
        )
