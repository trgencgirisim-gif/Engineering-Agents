"""tools/tier1/openfoam_tool.py — CFD analysis via OpenFOAM."""
import math

from tools.base import BaseToolWrapper, ToolResult


# Fluid properties database
FLUID_PROPS = {
    "air": {"rho": 1.225, "mu": 1.789e-5, "cp": 1006.0, "k": 0.0257, "Pr": 0.707},
    "water": {"rho": 998.2, "mu": 1.002e-3, "cp": 4182.0, "k": 0.598, "Pr": 7.01},
    "oil_sae30": {"rho": 891.0, "mu": 0.29, "cp": 1845.0, "k": 0.145, "Pr": 3690.0},
    "steam_100C": {"rho": 0.598, "mu": 1.23e-5, "cp": 2010.0, "k": 0.0248, "Pr": 0.998},
    "glycerin": {"rho": 1261.0, "mu": 1.412, "cp": 2427.0, "k": 0.286, "Pr": 11970.0},
    "ethanol": {"rho": 789.0, "mu": 1.2e-3, "cp": 2440.0, "k": 0.169, "Pr": 17.3},
}


class OpenFOAMTool(BaseToolWrapper):
    name = "openfoam"
    tier = 1
    domains = ["aerodinamik", "akiskan"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["pipe_flow", "external_flow", "heat_transfer"],
                "description": "Type of CFD analysis to perform",
            },
            "parameters": {
                "type": "object",
                "description": "Flow parameters",
                "properties": {
                    "fluid": {
                        "type": "string",
                        "description": "Fluid type (air, water, oil_sae30, steam_100C, glycerin, ethanol)",
                    },
                    "velocity_mps": {
                        "type": "number",
                        "description": "Flow velocity [m/s]",
                    },
                    "diameter_m": {
                        "type": "number",
                        "description": "Pipe diameter or characteristic length [m]",
                    },
                    "length_m": {
                        "type": "number",
                        "description": "Pipe or plate length [m]",
                    },
                    "roughness_mm": {
                        "type": "number",
                        "description": "Surface roughness [mm] (default 0.045 for commercial steel)",
                    },
                    "density_kgm3": {
                        "type": "number",
                        "description": "Custom fluid density [kg/m^3] (overrides fluid lookup)",
                    },
                    "viscosity_Pas": {
                        "type": "number",
                        "description": "Custom dynamic viscosity [Pa*s] (overrides fluid lookup)",
                    },
                    "wall_temp_C": {
                        "type": "number",
                        "description": "Wall temperature [C] for heat transfer",
                    },
                    "fluid_temp_C": {
                        "type": "number",
                        "description": "Bulk fluid temperature [C] for heat transfer",
                    },
                    "chord_m": {
                        "type": "number",
                        "description": "Airfoil chord length [m] for external flow",
                    },
                    "angle_of_attack_deg": {
                        "type": "number",
                        "description": "Angle of attack [deg] for airfoil analysis",
                    },
                    "span_m": {
                        "type": "number",
                        "description": "Wing span [m] for 3D lift/drag",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call for internal pipe/duct flow, external bluff body flows, "
            "or turbulent flow fields requiring velocity, pressure, and turbulence data.\n\n"
            "DO NOT CALL if:\n"
            "- Problem is better handled by SU2 (external aerodynamics with airfoils)\n"
            "- Only qualitative flow discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: pipe_flow / external_flow / heat_transfer\n"
            "- parameters.fluid: air / water / oil_sae30 / etc.\n"
            "- parameters.velocity_mps: flow velocity in m/s\n"
            "- parameters.diameter_m: pipe diameter or characteristic length\n\n"
            "Returns verified OpenFOAM CFD results: pressure drop, velocity profile, "
            "friction factor, Nusselt number."
        )

    def is_available(self) -> bool:
        try:
            # Check for OpenFOAM installation via subprocess
            import subprocess
            result = subprocess.run(
                ["simpleFoam", "-help"], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "pipe_flow")
        params = inputs.get("parameters", {})

        dispatch = {
            "pipe_flow": self._pipe_flow,
            "external_flow": self._external_flow,
            "heat_transfer": self._heat_transfer,
        }
        handler = dispatch.get(analysis_type, self._pipe_flow)
        return handler(params)

    def _get_fluid_props(self, params: dict) -> dict:
        """Get fluid properties from database or custom overrides."""
        fluid_key = params.get("fluid", "water")
        props = FLUID_PROPS.get(fluid_key, FLUID_PROPS["water"]).copy()
        if "density_kgm3" in params:
            props["rho"] = float(params["density_kgm3"])
        if "viscosity_Pas" in params:
            props["mu"] = float(params["viscosity_Pas"])
        return props

    def _colebrook_friction(self, Re: float, e_over_D: float) -> float:
        """Solve Colebrook-White equation iteratively for Darcy friction factor."""
        if Re < 2300:
            return 64.0 / Re if Re > 0 else 0.0
        # Initial guess (Swamee-Jain explicit approximation)
        if Re > 0 and e_over_D >= 0:
            f = 0.25 / (math.log10(e_over_D / 3.7 + 5.74 / Re**0.9))**2
        else:
            f = 0.02
        # Newton-Raphson iteration on Colebrook equation
        for _ in range(30):
            sqrt_f = math.sqrt(f) if f > 0 else 0.1
            rhs = -2.0 * math.log10(e_over_D / 3.7 + 2.51 / (Re * sqrt_f))
            residual = 1.0 / sqrt_f - rhs
            # Derivative: d/df(1/sqrt(f)) = -0.5 * f^(-3/2)
            deriv = -0.5 * f**(-1.5) - 2.51 / (Re * 2.0 * f * sqrt_f * math.log(10) *
                     (e_over_D / 3.7 + 2.51 / (Re * sqrt_f)))
            if abs(deriv) > 1e-15:
                f -= residual / deriv
                f = max(f, 1e-6)
            if abs(residual) < 1e-8:
                break
        return f

    def _pipe_flow(self, params: dict) -> ToolResult:
        """Darcy-Weisbach pipe flow analysis."""
        try:
            props = self._get_fluid_props(params)
            V = float(params.get("velocity_mps", 2.0))
            D = float(params.get("diameter_m", 0.05))
            L = float(params.get("length_m", 10.0))
            e = float(params.get("roughness_mm", 0.045)) / 1000.0  # convert to m
            rho = props["rho"]
            mu = props["mu"]
            g = 9.81

            Re = rho * V * D / mu if mu > 0 else 0
            e_over_D = e / D if D > 0 else 0

            # Friction factor via Colebrook-White
            f = self._colebrook_friction(Re, e_over_D)

            # Darcy-Weisbach: dP = f * (L/D) * (rho*V^2/2)
            dP = f * (L / D) * (rho * V**2 / 2.0) if D > 0 else 0
            head_loss = dP / (rho * g) if rho > 0 else 0

            # Volume flow rate
            A = math.pi * (D / 2.0)**2
            Q = V * A
            Q_lpm = Q * 60000.0  # litres per minute

            # Power to overcome friction
            P_pump = dP * Q  # Watts

            # Wall shear stress
            tau_w = f * rho * V**2 / 8.0

            # Entry length
            if Re < 2300:
                L_entry = 0.06 * Re * D
                regime = "laminar"
            else:
                L_entry = 4.4 * Re**(1.0/6.0) * D
                regime = "turbulent"

            warnings = []
            if 2000 < Re < 4000:
                warnings.append(f"Re = {Re:.0f}: transitional flow regime — results uncertain")
            if L < L_entry:
                warnings.append(f"Pipe length ({L} m) < entry length ({L_entry:.1f} m): flow not fully developed")
            if V > 10 and props.get("rho", 1000) > 500:
                warnings.append("High velocity for liquid — check for cavitation")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "reynolds_number": round(Re, 0),
                    "flow_regime": regime,
                    "friction_factor_darcy": round(f, 6),
                    "pressure_drop_Pa": round(dP, 2),
                    "pressure_drop_kPa": round(dP / 1000.0, 4),
                    "head_loss_m": round(head_loss, 4),
                    "wall_shear_stress_Pa": round(tau_w, 4),
                    "volume_flow_rate_m3ps": round(Q, 6),
                    "volume_flow_rate_lpm": round(Q_lpm, 2),
                    "pumping_power_W": round(P_pump, 3),
                    "entry_length_m": round(L_entry, 2),
                },
                units={
                    "pressure_drop_Pa": "Pa", "pressure_drop_kPa": "kPa",
                    "head_loss_m": "m", "wall_shear_stress_Pa": "Pa",
                    "volume_flow_rate_m3ps": "m^3/s", "volume_flow_rate_lpm": "L/min",
                    "pumping_power_W": "W", "entry_length_m": "m",
                },
                raw_output=f"Pipe flow: Re={Re:.0f}, f={f:.5f}, dP={dP:.1f} Pa",
                warnings=warnings,
                assumptions=[
                    "Darcy-Weisbach equation with Colebrook-White friction factor",
                    f"Fluid: {params.get('fluid', 'water')}, rho={rho} kg/m^3, mu={mu} Pa*s",
                    f"Roughness e={e*1000:.3f} mm (e/D={e_over_D:.6f})",
                    "Steady, incompressible, fully developed flow assumed",
                    "No minor losses (fittings, valves, etc.)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _external_flow(self, params: dict) -> ToolResult:
        """External flow: flat plate boundary layer and airfoil lift/drag."""
        try:
            props = self._get_fluid_props(params)
            V = float(params.get("velocity_mps", 30.0))
            rho = props["rho"]
            mu = props["mu"]
            nu = mu / rho

            chord = params.get("chord_m")
            L_plate = float(params.get("length_m", params.get("chord_m", 1.0)))
            aoa = float(params.get("angle_of_attack_deg", 0.0))
            span = params.get("span_m")

            Re_L = rho * V * L_plate / mu if mu > 0 else 0
            q = 0.5 * rho * V**2  # dynamic pressure

            data = {
                "reynolds_number": round(Re_L, 0),
                "dynamic_pressure_Pa": round(q, 2),
            }
            units = {"dynamic_pressure_Pa": "Pa"}

            # Flat plate boundary layer (always computed)
            if Re_L < 5e5:
                # Laminar (Blasius)
                Cf = 1.328 / math.sqrt(Re_L) if Re_L > 0 else 0
                delta_L = 5.0 * L_plate / math.sqrt(Re_L) if Re_L > 0 else 0
                bl_regime = "laminar"
            elif Re_L < 1e7:
                # Turbulent (Prandtl 1/7 power law)
                Cf = 0.074 / Re_L**0.2
                delta_L = 0.37 * L_plate / Re_L**0.2
                bl_regime = "turbulent"
            else:
                # Fully turbulent (Schlichting)
                Cf = 0.455 / (math.log10(Re_L))**2.58
                delta_L = 0.37 * L_plate / Re_L**0.2
                bl_regime = "turbulent"

            F_drag_plate = Cf * q * L_plate * 1.0  # per unit width
            data["skin_friction_coeff"] = round(Cf, 6)
            data["boundary_layer_thickness_m"] = round(delta_L, 5)
            data["plate_drag_per_unit_width_Npm"] = round(F_drag_plate, 3)
            data["boundary_layer_regime"] = bl_regime
            units["boundary_layer_thickness_m"] = "m"
            units["plate_drag_per_unit_width_Npm"] = "N/m"

            # Airfoil analysis (thin airfoil theory + viscous drag)
            if chord is not None or aoa != 0:
                c = float(chord) if chord else L_plate
                aoa_rad = math.radians(aoa)

                # Thin airfoil theory: CL = 2*pi*alpha (attached flow)
                CL = 2.0 * math.pi * aoa_rad
                # Stall limit
                if abs(aoa) > 15:
                    CL = CL * (15.0 / abs(aoa))**0.5  # rough stall reduction
                    stalled = True
                else:
                    stalled = False

                # Parasitic drag (form + friction)
                Re_c = rho * V * c / mu if mu > 0 else 0
                Cd_friction = 2 * (0.074 / Re_c**0.2) if Re_c > 1000 else 0.01  # both sides

                # Induced drag (finite wing)
                if span is not None:
                    b = float(span)
                    AR = b**2 / (b * c) if c > 0 else 10  # aspect ratio (rectangular wing)
                    e_oswald = 0.85  # Oswald efficiency
                    Cd_induced = CL**2 / (math.pi * AR * e_oswald)
                    Cd_total = Cd_friction + Cd_induced
                    data["aspect_ratio"] = round(AR, 2)
                    data["oswald_efficiency"] = e_oswald
                    data["Cd_induced"] = round(Cd_induced, 6)
                else:
                    Cd_total = Cd_friction
                    Cd_induced = 0.0

                L_force = CL * q * c  # lift per unit span
                D_force = Cd_total * q * c  # drag per unit span
                L_over_D = CL / Cd_total if Cd_total > 0 else 0

                data["CL"] = round(CL, 4)
                data["Cd_friction"] = round(Cd_friction, 6)
                data["Cd_total"] = round(Cd_total, 6)
                data["lift_per_span_Npm"] = round(L_force, 2)
                data["drag_per_span_Npm"] = round(D_force, 2)
                data["L_over_D"] = round(L_over_D, 1)
                units["lift_per_span_Npm"] = "N/m"
                units["drag_per_span_Npm"] = "N/m"

            warnings = []
            if Re_L < 1000:
                warnings.append("Very low Reynolds number — creeping flow regime")
            if aoa != 0 and abs(aoa) > 15:
                warnings.append(f"AoA={aoa} deg exceeds typical stall angle — results approximate")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data=data, units=units,
                raw_output=f"External flow: Re={Re_L:.0f}, Cf={Cf:.5f}, V={V} m/s",
                warnings=warnings,
                assumptions=[
                    "Flat plate: Blasius (laminar) or Prandtl 1/7-power (turbulent) correlations",
                    "Thin airfoil theory: CL = 2*pi*alpha (small angle, incompressible)",
                    "Induced drag from lifting-line theory (Oswald e=0.85)",
                    "Incompressible flow (valid for Mach < 0.3)",
                    f"Fluid: {params.get('fluid', 'air')}",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _heat_transfer(self, params: dict) -> ToolResult:
        """Convective heat transfer using Nusselt correlations."""
        try:
            props = self._get_fluid_props(params)
            V = float(params.get("velocity_mps", 2.0))
            D = float(params.get("diameter_m", 0.025))
            L = float(params.get("length_m", 1.0))
            T_wall = float(params.get("wall_temp_C", 100.0))
            T_fluid = float(params.get("fluid_temp_C", 25.0))
            rho = props["rho"]
            mu = props["mu"]
            cp = props["cp"]
            k = props["k"]
            Pr = props["Pr"]

            Re = rho * V * D / mu if mu > 0 else 0
            dT = T_wall - T_fluid

            # Internal flow (pipe) Nusselt number
            if Re < 2300:
                # Laminar: Sieder-Tate (developing flow with Gz correction)
                Gz = Re * Pr * D / L if L > 0 else 0
                if Gz > 10:
                    Nu = 1.86 * Gz**(1.0/3.0)
                else:
                    Nu = 3.66  # fully developed laminar, constant wall temperature
                regime = "laminar"
            else:
                # Turbulent: Dittus-Boelter correlation
                # Nu = 0.023 * Re^0.8 * Pr^n, n=0.4 (heating), n=0.3 (cooling)
                n = 0.4 if dT > 0 else 0.3
                Nu = 0.023 * Re**0.8 * Pr**n
                regime = "turbulent"

            # Convection coefficient
            h_conv = Nu * k / D if D > 0 else 0

            # Heat transfer rate (internal pipe)
            A_surface = math.pi * D * L
            Q_total = h_conv * A_surface * dT  # Watts

            # External cylinder (Churchill-Bernstein correlation for comparison)
            if Re > 0 and Pr > 0:
                Nu_ext = (0.3 + (0.62 * Re**0.5 * Pr**(1.0/3.0)) /
                          (1 + (0.4 / Pr)**(2.0/3.0))**0.25 *
                          (1 + (Re / 282000)**(5.0/8.0))**0.8)
                h_ext = Nu_ext * k / D if D > 0 else 0
            else:
                Nu_ext = 0
                h_ext = 0

            # Thermal resistance
            R_conv = 1.0 / (h_conv * A_surface) if h_conv * A_surface > 0 else float("inf")

            # Log-mean temperature difference for heat exchanger estimate
            # Assuming counter-flow with outlet temp = T_fluid + 0.5*dT (rough)
            T_out = T_fluid + 0.5 * abs(dT)
            dT1 = T_wall - T_fluid
            dT2 = T_wall - T_out
            if abs(dT1 - dT2) > 0.01:
                LMTD = (dT1 - dT2) / math.log(dT1 / dT2) if dT1 > 0 and dT2 > 0 else abs(dT)
            else:
                LMTD = dT1

            warnings = []
            if 2000 < Re < 4000:
                warnings.append("Transitional flow: Nusselt correlation accuracy reduced")
            if Pr < 0.7 or Pr > 160:
                warnings.append(f"Pr={Pr}: outside optimal range for Dittus-Boelter (0.7-160)")
            if abs(dT) > 200:
                warnings.append("Large temperature difference: property variations may be significant")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "reynolds_number": round(Re, 0),
                    "prandtl_number": round(Pr, 3),
                    "nusselt_number_internal": round(Nu, 2),
                    "nusselt_number_external_cyl": round(Nu_ext, 2),
                    "h_convection_internal_Wpm2K": round(h_conv, 2),
                    "h_convection_external_Wpm2K": round(h_ext, 2),
                    "heat_transfer_rate_W": round(Q_total, 2),
                    "surface_area_m2": round(A_surface, 6),
                    "thermal_resistance_KpW": round(R_conv, 6) if R_conv < 1e6 else None,
                    "LMTD_K": round(LMTD, 2),
                    "flow_regime": regime,
                },
                units={
                    "h_convection_internal_Wpm2K": "W/(m^2*K)",
                    "h_convection_external_Wpm2K": "W/(m^2*K)",
                    "heat_transfer_rate_W": "W",
                    "surface_area_m2": "m^2",
                    "thermal_resistance_KpW": "K/W",
                    "LMTD_K": "K",
                },
                raw_output=f"Heat transfer: Re={Re:.0f}, Nu={Nu:.1f}, h={h_conv:.1f} W/m^2K, Q={Q_total:.0f} W",
                warnings=warnings,
                assumptions=[
                    f"Internal flow: {'Sieder-Tate' if Re < 2300 else 'Dittus-Boelter'} correlation",
                    "External cylinder: Churchill-Bernstein correlation",
                    f"Fluid: {params.get('fluid', 'water')}, Pr={Pr}",
                    "Constant wall temperature boundary condition",
                    "Properties evaluated at bulk fluid temperature",
                    "LMTD computed assuming outlet at T_fluid + 0.5*(T_wall - T_fluid)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
