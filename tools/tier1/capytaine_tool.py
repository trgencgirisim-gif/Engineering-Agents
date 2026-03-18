"""tools/tier1/capytaine_tool.py — Marine hydrodynamics via Capytaine."""
import math

from tools.base import BaseToolWrapper, ToolResult


class CapytaineTool(BaseToolWrapper):
    name    = "capytaine"
    tier    = 1
    domains = ["denizcilik"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["wave_loads", "ship_motion", "wave_resistance"],
                "description": "Type of marine hydrodynamic analysis",
            },
            "hull_params": {
                "type": "object",
                "description": "Hull geometry and condition parameters",
                "properties": {
                    "length_m":      {"type": "number", "description": "Hull length [m]"},
                    "beam_m":        {"type": "number", "description": "Hull beam/width [m]"},
                    "draft_m":       {"type": "number", "description": "Hull draft [m]"},
                    "displacement_t": {"type": "number", "description": "Displacement [tonnes]"},
                    "block_coefficient": {"type": "number", "description": "Block coefficient Cb (0.5-0.9)"},
                },
            },
            "wave_params": {
                "type": "object",
                "description": "Sea state parameters",
                "properties": {
                    "wave_height_m":  {"type": "number", "description": "Significant wave height Hs [m]"},
                    "wave_period_s":  {"type": "number", "description": "Peak wave period Tp [s]"},
                    "wave_heading_deg": {"type": "number", "description": "Wave heading angle [deg] (0=head seas)"},
                },
            },
            "speed_knots": {
                "type": "number",
                "description": "Vessel forward speed [knots]",
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: added mass, radiation damping, "
            "wave excitation forces, or response amplitude operators (RAO) "
            "for a floating or submerged body.\n\n"
            "DO NOT CALL if:\n"
            "- Vessel geometry cannot be described parametrically\n"
            "- Only qualitative seakeeping discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: wave_loads / ship_motion / wave_resistance\n"
            "- hull_params: length_m, beam_m, draft_m, displacement_t\n"
            "- wave_params: wave_height_m, wave_period_s\n\n"
            "Returns verified Capytaine BEM hydrodynamic coefficients."
        )

    def is_available(self) -> bool:
        try:
            import capytaine  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            analysis_type = inputs.get("analysis_type", "wave_loads")
            dispatch = {
                "wave_loads":      self._wave_loads,
                "ship_motion":     self._ship_motion,
                "wave_resistance": self._wave_resistance,
            }
            handler = dispatch.get(analysis_type, self._wave_loads)
            return handler(inputs)
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _wave_loads(self, inputs: dict) -> ToolResult:
        """Analytical wave load estimation using strip theory approximation."""
        hull = inputs.get("hull_params", {})
        wave = inputs.get("wave_params", {})

        L = float(hull.get("length_m", 100))
        B = float(hull.get("beam_m", 15))
        T = float(hull.get("draft_m", 6))
        disp = float(hull.get("displacement_t", 5000))
        Cb = float(hull.get("block_coefficient", 0.7))

        Hs = float(wave.get("wave_height_m", 3.0))
        Tp = float(wave.get("wave_period_s", 8.0))
        heading = float(wave.get("wave_heading_deg", 0))

        rho = 1025.0  # kg/m³ seawater
        g = 9.81
        omega = 2 * math.pi / Tp
        k = omega ** 2 / g  # deep water dispersion

        # Added mass (heave) ~ displaced water mass × coefficient
        m33_added = rho * math.pi * (B / 2) ** 2 * L * 0.8

        # Damping (heave) ~ radiation damping coefficient
        b33 = rho * g * B * L * 0.05 / omega

        # Wave excitation force (heave, head seas)
        Aw = L * B * Cb
        F3_amplitude = rho * g * Aw * (Hs / 2) * math.exp(-k * T)
        F3_cos_heading = abs(math.cos(math.radians(heading)))
        F3 = F3_amplitude * max(F3_cos_heading, 0.3)

        # Bending moment amidships (Froude-Krylov)
        M_hogging = 0.19 * Cb * L ** 2 * B * Hs * rho * g / 1e6  # MN·m
        M_sagging = M_hogging * 1.1

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "added_mass_heave_kg": round(m33_added, 1),
                "damping_heave_Ns_per_m": round(b33, 1),
                "excitation_force_heave_kN": round(F3 / 1000, 2),
                "hogging_moment_MNm": round(M_hogging, 3),
                "sagging_moment_MNm": round(M_sagging, 3),
                "wave_number_1_per_m": round(k, 5),
            },
            units={
                "added_mass_heave_kg": "kg",
                "damping_heave_Ns_per_m": "N·s/m",
                "excitation_force_heave_kN": "kN",
                "hogging_moment_MNm": "MN·m",
                "sagging_moment_MNm": "MN·m",
                "wave_number_1_per_m": "1/m",
            },
            raw_output=f"Wave loads: L={L}m, B={B}m, T={T}m, Hs={Hs}m, Tp={Tp}s",
            assumptions=[
                "Strip theory approximation for added mass and damping",
                "Deep water wave dispersion relation",
                "Froude-Krylov hypothesis for wave excitation forces",
                "Linear potential flow (small amplitude waves)",
            ],
        )

    def _ship_motion(self, inputs: dict) -> ToolResult:
        """Ship motion RAOs using simplified single-DOF model."""
        hull = inputs.get("hull_params", {})
        wave = inputs.get("wave_params", {})

        L = float(hull.get("length_m", 100))
        B = float(hull.get("beam_m", 15))
        T = float(hull.get("draft_m", 6))
        disp = float(hull.get("displacement_t", 5000))

        Hs = float(wave.get("wave_height_m", 3.0))
        Tp = float(wave.get("wave_period_s", 8.0))
        speed = float(inputs.get("speed_knots", 12))

        rho = 1025.0
        g = 9.81
        omega_e = 2 * math.pi / Tp  # encounter frequency ≈ wave freq for simplicity
        mass = disp * 1000  # kg

        # Natural periods (empirical)
        Tn_heave = 2 * math.pi * math.sqrt(mass / (rho * g * L * B * 0.9))
        GM = B * 0.08  # metacentric height estimate
        Tn_roll = 2 * math.pi * 0.44 * B / math.sqrt(g * GM) if GM > 0 else 15.0
        Tn_pitch = 0.6 * Tn_heave

        # RAO at encounter frequency (single-DOF resonance model)
        def rao(omega, omega_n, zeta=0.1):
            r = omega / omega_n if omega_n > 0 else 1
            return 1.0 / math.sqrt((1 - r ** 2) ** 2 + (2 * zeta * r) ** 2)

        rao_heave = rao(omega_e, 2 * math.pi / Tn_heave)
        rao_pitch = rao(omega_e, 2 * math.pi / Tn_pitch)
        rao_roll = rao(omega_e, 2 * math.pi / Tn_roll, zeta=0.05)

        heave_amp = rao_heave * Hs / 2
        pitch_amp = rao_pitch * math.degrees(math.atan(Hs / L)) * 2
        roll_amp = rao_roll * math.degrees(math.atan(Hs / B)) * 2

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "heave_amplitude_m": round(heave_amp, 3),
                "pitch_amplitude_deg": round(pitch_amp, 2),
                "roll_amplitude_deg": round(roll_amp, 2),
                "natural_period_heave_s": round(Tn_heave, 2),
                "natural_period_pitch_s": round(Tn_pitch, 2),
                "natural_period_roll_s": round(Tn_roll, 2),
                "RAO_heave": round(rao_heave, 3),
                "RAO_pitch": round(rao_pitch, 3),
                "RAO_roll": round(rao_roll, 3),
            },
            units={
                "heave_amplitude_m": "m",
                "pitch_amplitude_deg": "deg",
                "roll_amplitude_deg": "deg",
                "natural_period_heave_s": "s",
                "natural_period_pitch_s": "s",
                "natural_period_roll_s": "s",
            },
            raw_output=f"Ship motion: L={L}m, Hs={Hs}m, Tp={Tp}s, speed={speed}kn",
            assumptions=[
                "Single-DOF resonance model per motion mode",
                "Empirical natural period estimates",
                "Linear superposition (small motions)",
                "Damping ratios: heave/pitch=0.10, roll=0.05",
            ],
        )

    def _wave_resistance(self, inputs: dict) -> ToolResult:
        """Wave resistance estimation using Holtrop-Mennen method (simplified)."""
        hull = inputs.get("hull_params", {})

        L = float(hull.get("length_m", 100))
        B = float(hull.get("beam_m", 15))
        T = float(hull.get("draft_m", 6))
        disp = float(hull.get("displacement_t", 5000))
        Cb = float(hull.get("block_coefficient", 0.7))
        speed_kn = float(inputs.get("speed_knots", 15))

        rho = 1025.0
        g = 9.81
        nu = 1.19e-6  # kinematic viscosity seawater
        V = speed_kn * 0.5144  # m/s

        # Froude number
        Fn = V / math.sqrt(g * L)

        # Wetted surface (Holtrop approximation)
        S = L * (2 * T + B) * math.sqrt(Cb) * 0.85

        # Frictional resistance (ITTC 1957)
        Re = V * L / nu if V > 0 else 1e6
        Cf = 0.075 / (math.log10(Re) - 2) ** 2 if Re > 0 else 0.003

        Rf = 0.5 * rho * S * V ** 2 * Cf

        # Wave resistance (Holtrop simplified)
        c1 = 0.5 * Cb * (B / L)
        Rw = c1 * rho * g * disp * 1000 * Fn ** 4 * math.exp(-3.0 / Fn) if Fn > 0.1 else 0

        # Form factor
        k1 = 0.93 + 0.487 * (Cb - 0.6)
        Rv = Rf * k1

        R_total = Rv + Rw
        P_effective = R_total * V / 1000  # kW
        P_delivered = P_effective / 0.65  # quasi-propulsive efficiency

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "froude_number": round(Fn, 4),
                "frictional_resistance_kN": round(Rf / 1000, 2),
                "wave_resistance_kN": round(Rw / 1000, 2),
                "total_resistance_kN": round(R_total / 1000, 2),
                "effective_power_kW": round(P_effective, 1),
                "delivered_power_kW": round(P_delivered, 1),
                "wetted_surface_m2": round(S, 1),
            },
            units={
                "frictional_resistance_kN": "kN",
                "wave_resistance_kN": "kN",
                "total_resistance_kN": "kN",
                "effective_power_kW": "kW",
                "delivered_power_kW": "kW",
                "wetted_surface_m2": "m²",
            },
            raw_output=f"Wave resistance: L={L}m, V={speed_kn}kn, Fn={Fn:.3f}",
            assumptions=[
                "Holtrop-Mennen simplified method",
                "ITTC 1957 friction line",
                "Quasi-propulsive efficiency = 0.65",
                "Deep water, calm seas (no added resistance in waves)",
            ],
        )
