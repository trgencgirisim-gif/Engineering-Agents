"""tools/tier1/su2_tool.py — CFD analysis via SU2."""
import math
import shutil

from tools.base import BaseToolWrapper, ToolResult


class SU2Tool(BaseToolWrapper):
    name    = "su2"
    tier    = 1
    domains = ["aerodinamik", "uzay"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["airfoil_analysis", "3d_flow"],
                "description": "Type of CFD analysis to perform",
            },
            "flow_params": {
                "type": "object",
                "description": "Flow conditions",
                "properties": {
                    "mach":        {"type": "number", "description": "Mach number"},
                    "reynolds":    {"type": "number", "description": "Reynolds number"},
                    "alpha_deg":   {"type": "number", "description": "Angle of attack [degrees]"},
                    "pressure":    {"type": "number", "description": "Freestream static pressure [Pa]", "default": 101325},
                    "temperature": {"type": "number", "description": "Freestream temperature [K]", "default": 288.15},
                },
            },
            "geometry": {
                "type": "object",
                "description": "Geometry specification",
                "properties": {
                    "airfoil_type": {"type": "string", "description": "NACA airfoil designation (e.g. '0012', '2412')"},
                    "shape":        {"type": "string", "description": "Generic shape description for 3D flow"},
                    "chord":        {"type": "number", "description": "Chord length [m]", "default": 1.0},
                    "span":         {"type": "number", "description": "Wing span [m] (for 3D)"},
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "Performs computational fluid dynamics analysis using SU2 or analytical "
            "aerodynamic approximations: thin airfoil theory for lift, flat-plate skin "
            "friction plus induced drag for drag estimation, compressibility corrections "
            "(Prandtl-Glauert, Ackeret). Supports subsonic and supersonic regimes. "
            "Use for airfoil aerodynamic performance, pressure distribution, and flow analysis."
        )

    def is_available(self) -> bool:
        try:
            import SU2  # noqa: F401
            return True
        except ImportError:
            return shutil.which("SU2_CFD") is not None

    def execute(self, inputs: dict) -> ToolResult:
        try:
            analysis_type = inputs.get("analysis_type", "airfoil_analysis")
            flow = inputs.get("flow_params", {})
            geom = inputs.get("geometry", {})

            if analysis_type == "airfoil_analysis":
                return self._airfoil_analysis(flow, geom)
            elif analysis_type == "3d_flow":
                return self._3d_flow(flow, geom)
            else:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error=f"Unknown analysis_type: {analysis_type}",
                )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _airfoil_analysis(self, flow: dict, geom: dict) -> ToolResult:
        mach      = float(flow.get("mach", 0.3))
        Re        = float(flow.get("reynolds", 1e6))
        alpha_deg = float(flow.get("alpha_deg", 5.0))
        P_inf     = float(flow.get("pressure", 101325.0))
        T_inf     = float(flow.get("temperature", 288.15))
        chord     = float(geom.get("chord", 1.0))
        airfoil   = geom.get("airfoil_type", "0012")

        alpha_rad = math.radians(alpha_deg)
        gamma = 1.4
        R_air = 287.058

        warnings = []
        assumptions = []

        # Parse NACA 4-digit for camber
        max_camber_pct = 0.0
        camber_pos_pct = 0.0
        thickness_pct = 12.0
        if len(airfoil) == 4 and airfoil.isdigit():
            max_camber_pct = int(airfoil[0])  # percentage of chord
            camber_pos_pct = int(airfoil[1]) * 10  # percentage of chord
            thickness_pct = int(airfoil[2:4])
        assumptions.append(f"NACA {airfoil} airfoil")

        # Thin airfoil theory: Cl = 2*pi*(alpha + alpha_L0)
        # For cambered airfoil, alpha_L0 ~ -2*(max_camber/100)
        alpha_L0 = -2.0 * (max_camber_pct / 100.0) if max_camber_pct > 0 else 0.0
        Cl_incomp = 2.0 * math.pi * (alpha_rad - alpha_L0)

        # Lift-curve slope correction for finite thickness
        # Empirical: dCl/dalpha ~ 2*pi * (1 + 0.77 * t/c)
        t_over_c = thickness_pct / 100.0
        slope_correction = 1.0 + 0.77 * t_over_c
        Cl_incomp *= slope_correction / 1.0  # normalize relative to 2pi

        if mach < 1.0:
            # Prandtl-Glauert compressibility correction
            beta_pg = math.sqrt(1.0 - mach ** 2) if mach < 0.99 else 0.1
            Cl = Cl_incomp / beta_pg
            assumptions.append("Prandtl-Glauert compressibility correction (subsonic)")
        else:
            # Ackeret (linearized supersonic): Cl = 4*alpha / sqrt(M^2 - 1)
            beta_sup = math.sqrt(mach ** 2 - 1.0) if mach > 1.001 else 0.1
            Cl = 4.0 * alpha_rad / beta_sup
            assumptions.append("Ackeret linearized supersonic theory")
            warnings.append("Supersonic thin airfoil theory — accuracy limited for thick airfoils")

        # Skin friction drag (turbulent flat plate, Schlichting formula)
        if Re > 0:
            Cf = 0.455 / (math.log10(Re) ** 2.58)
        else:
            Cf = 0.005
            warnings.append("Reynolds number not provided — using default Cf=0.005")
        assumptions.append("Turbulent flat plate skin friction (Schlichting)")

        # Form factor (Shevell method for airfoils)
        FF = 1.0 + 2.0 * t_over_c + 60.0 * t_over_c ** 4
        Cd_friction = Cf * FF * 2.0  # factor 2 for upper+lower surfaces (wetted area ~ 2*planform)

        # Induced drag (2D has no induced drag in strict sense, but profile drag due to lift)
        # For 2D: Cd_pressure ~ Cl^2 / (4*pi) from thin airfoil theory
        Cd_pressure = Cl ** 2 / (4.0 * math.pi) if mach < 1.0 else 0.0

        # Wave drag for supersonic
        Cd_wave = 0.0
        if mach >= 1.0:
            beta_sup = math.sqrt(mach ** 2 - 1.0) if mach > 1.001 else 0.1
            # Ackeret wave drag: Cd_w = 4*(alpha^2 + (t/c)^2/4) / sqrt(M^2-1)
            Cd_wave = 4.0 * (alpha_rad ** 2 + (t_over_c ** 2) / 4.0) / beta_sup
            assumptions.append("Ackeret wave drag model")

        Cd_total = Cd_friction + Cd_pressure + Cd_wave
        L_over_D = Cl / Cd_total if Cd_total > 0 else float("inf")

        # Moment coefficient (about c/4 — thin airfoil: Cm_c/4 = -pi/2 * camber effect)
        Cm_c4 = -math.pi / 2.0 * (max_camber_pct / 100.0) if max_camber_pct > 0 else 0.0

        # Dynamic pressure
        rho = P_inf / (R_air * T_inf)
        V_inf = mach * math.sqrt(gamma * R_air * T_inf)
        q_inf = 0.5 * rho * V_inf ** 2

        # Dimensional forces per unit span
        L_per_span = Cl * q_inf * chord
        D_per_span = Cd_total * q_inf * chord

        # Stall check
        if abs(alpha_deg) > 12.0:
            warnings.append(f"AoA={alpha_deg} deg exceeds typical stall angle — thin airfoil theory inaccurate")

        if mach > 0.7 and mach < 1.0:
            warnings.append("Transonic regime — Prandtl-Glauert correction loses accuracy above M~0.7")

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "Cl":                 round(Cl, 5),
                "Cd_total":           round(Cd_total, 6),
                "Cd_friction":        round(Cd_friction, 6),
                "Cd_pressure":        round(Cd_pressure, 6),
                "Cd_wave":            round(Cd_wave, 6),
                "L_over_D":           round(L_over_D, 2),
                "Cm_quarter_chord":   round(Cm_c4, 5),
                "lift_per_span_N_m":  round(L_per_span, 3),
                "drag_per_span_N_m":  round(D_per_span, 4),
                "dynamic_pressure_Pa": round(q_inf, 2),
            },
            units={
                "lift_per_span_N_m":   "N/m",
                "drag_per_span_N_m":   "N/m",
                "dynamic_pressure_Pa": "Pa",
            },
            raw_output=(
                f"SU2 analytical: NACA {airfoil}, M={mach}, Re={Re:.0f}, "
                f"alpha={alpha_deg} deg, chord={chord} m"
            ),
            warnings=warnings,
            assumptions=assumptions + ["Thin airfoil theory (2D, inviscid core)"],
        )

    def _3d_flow(self, flow: dict, geom: dict) -> ToolResult:
        mach      = float(flow.get("mach", 0.3))
        Re        = float(flow.get("reynolds", 1e6))
        alpha_deg = float(flow.get("alpha_deg", 5.0))
        P_inf     = float(flow.get("pressure", 101325.0))
        T_inf     = float(flow.get("temperature", 288.15))
        span      = float(geom.get("span", 10.0))
        chord     = float(geom.get("chord", 1.5))
        airfoil   = geom.get("airfoil_type", "0012")

        alpha_rad = math.radians(alpha_deg)
        gamma = 1.4
        R_air = 287.058
        AR = span / chord  # aspect ratio (rectangular wing)

        # 2D lift slope
        a0 = 2.0 * math.pi
        # Finite wing correction (Helmbold equation for low AR)
        a_3d = a0 / (1.0 + a0 / (math.pi * AR) + a0 / (math.pi * AR) ** 2) ** 0.5
        # Simplified: a_3d ~ a0 / (1 + a0/(pi*e*AR)) for moderate AR
        e_oswald = 0.85  # Oswald efficiency
        a_3d_simple = a0 / (1.0 + a0 / (math.pi * e_oswald * AR))

        CL = a_3d_simple * alpha_rad

        # Compressibility
        if mach < 1.0 and mach > 0.0:
            beta_pg = math.sqrt(max(1.0 - mach ** 2, 0.01))
            CL /= beta_pg

        # Induced drag: CDi = CL^2 / (pi * e * AR)
        CDi = CL ** 2 / (math.pi * e_oswald * AR)

        # Parasite drag (turbulent flat plate)
        if Re > 0:
            Cf = 0.455 / (math.log10(Re) ** 2.58)
        else:
            Cf = 0.005
        S_wet_ratio = 2.05  # wetted area / reference area for a wing
        CD0 = Cf * S_wet_ratio

        CD_total = CD0 + CDi
        L_over_D = CL / CD_total if CD_total > 0 else 0.0

        # Dimensional
        rho = P_inf / (R_air * T_inf)
        V_inf = mach * math.sqrt(gamma * R_air * T_inf)
        q_inf = 0.5 * rho * V_inf ** 2
        S_ref = span * chord
        Lift = CL * q_inf * S_ref
        Drag = CD_total * q_inf * S_ref

        warnings = []
        if abs(alpha_deg) > 14:
            warnings.append("AoA exceeds typical stall limit for finite wings")
        if AR < 3:
            warnings.append("Low aspect ratio — lifting line theory less accurate")

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "CL":               round(CL, 5),
                "CD_total":          round(CD_total, 6),
                "CD_induced":        round(CDi, 6),
                "CD_parasite":       round(CD0, 6),
                "L_over_D":          round(L_over_D, 2),
                "lift_N":            round(Lift, 2),
                "drag_N":            round(Drag, 2),
                "aspect_ratio":      round(AR, 2),
                "oswald_efficiency": e_oswald,
                "wing_area_m2":      round(S_ref, 3),
            },
            units={
                "lift_N":       "N",
                "drag_N":       "N",
                "wing_area_m2": "m^2",
            },
            raw_output=(
                f"SU2 3D analytical: AR={AR:.1f}, M={mach}, Re={Re:.0f}, "
                f"alpha={alpha_deg} deg, span={span} m, chord={chord} m"
            ),
            warnings=warnings,
            assumptions=[
                f"Rectangular wing, AR={AR:.2f}",
                f"Oswald efficiency e={e_oswald}",
                "Lifting line theory with Prandtl-Glauert correction",
                "Turbulent flat plate skin friction (Schlichting)",
            ],
        )
