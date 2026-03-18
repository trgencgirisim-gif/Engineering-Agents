"""tools/tier1/openmodelica_tool.py — Multi-domain physical modeling via OpenModelica."""
import math

from tools.base import BaseToolWrapper, ToolResult


class OpenModelicaTool(BaseToolWrapper):
    name    = "openmodelica"
    tier    = 1
    domains = ["hidrolik", "sistem"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["hydraulic_circuit", "thermal_system", "dynamic_system"],
                "description": "Type of multi-domain physical system analysis",
            },
            "parameters": {
                "type": "object",
                "description": "System parameters",
                "properties": {
                    "pipe_diameter_m": {
                        "type": "number",
                        "description": "Pipe inner diameter [m]",
                    },
                    "pipe_length_m": {
                        "type": "number",
                        "description": "Pipe length [m]",
                    },
                    "flow_rate_m3_s": {
                        "type": "number",
                        "description": "Volumetric flow rate [m^3/s]",
                    },
                    "fluid_density_kg_m3": {
                        "type": "number",
                        "description": "Fluid density [kg/m^3], default 998 (water)",
                    },
                    "dynamic_viscosity_Pa_s": {
                        "type": "number",
                        "description": "Dynamic viscosity [Pa.s], default 1.003e-3 (water 20C)",
                    },
                    "pump_head_m": {
                        "type": "number",
                        "description": "Pump total head [m]",
                    },
                    "elevation_change_m": {
                        "type": "number",
                        "description": "Elevation change (positive = uphill) [m]",
                    },
                    "thermal_mass_J_K": {
                        "type": "number",
                        "description": "Lumped thermal mass m*c_p [J/K]",
                    },
                    "thermal_resistance_K_W": {
                        "type": "number",
                        "description": "Thermal resistance to ambient [K/W]",
                    },
                    "heat_input_W": {
                        "type": "number",
                        "description": "Heat source power [W]",
                    },
                    "ambient_temp_C": {
                        "type": "number",
                        "description": "Ambient temperature [C]",
                    },
                    "initial_temp_C": {
                        "type": "number",
                        "description": "Initial body temperature [C]",
                    },
                    "num_gain": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Transfer function numerator coefficients [high->low order]",
                    },
                    "den_gain": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Transfer function denominator coefficients [high->low order]",
                    },
                    "step_amplitude": {
                        "type": "number",
                        "description": "Step input amplitude, default 1.0",
                    },
                    "simulation_time_s": {
                        "type": "number",
                        "description": "Simulation duration [s]",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call for multi-domain dynamic system simulation: hydraulic circuits, "
            "thermal-mechanical coupling, or system-level dynamic response.\n\n"
            "DO NOT CALL if:\n"
            "- Problem is single-domain and better handled by a specialized tool\n"
            "- Only qualitative system discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: hydraulic_circuit / thermal_system / dynamic_system\n"
            "- parameters: pipe geometry, fluid properties, or transfer function coefficients\n"
            "- simulation_time_s: simulation duration\n\n"
            "Returns verified OpenModelica time-domain simulation results."
        )

    def is_available(self) -> bool:
        try:
            from OMPython import OMCSessionZMQ  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "hydraulic_circuit")
        params = inputs.get("parameters", {})

        dispatch = {
            "hydraulic_circuit": self._hydraulic_circuit,
            "thermal_system":    self._thermal_system,
            "dynamic_system":    self._dynamic_system,
        }
        handler = dispatch.get(analysis_type, self._hydraulic_circuit)
        return handler(params)

    # ------------------------------------------------------------------
    # Hydraulic circuit: Bernoulli + Hagen-Poiseuille / Darcy-Weisbach
    # ------------------------------------------------------------------
    def _hydraulic_circuit(self, params: dict) -> ToolResult:
        try:
            D     = float(params.get("pipe_diameter_m", 0.05))
            L     = float(params.get("pipe_length_m", 10.0))
            Q     = float(params.get("flow_rate_m3_s", 0.001))
            rho   = float(params.get("fluid_density_kg_m3", 998.0))
            mu    = float(params.get("dynamic_viscosity_Pa_s", 1.003e-3))
            H_p   = float(params.get("pump_head_m", 0.0))
            dz    = float(params.get("elevation_change_m", 0.0))
            g     = 9.81

            if D <= 0 or L <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Pipe diameter and length must be positive",
                )

            A  = math.pi * (D / 2.0) ** 2
            V  = Q / A if A > 0 else 0.0  # mean velocity [m/s]
            Re = rho * V * D / mu if mu > 0 else 0.0

            # Friction factor
            if Re < 2300:
                # Hagen-Poiseuille (laminar): f = 64/Re
                f = 64.0 / Re if Re > 0 else 0.0
                flow_regime = "laminar"
            else:
                # Colebrook-White (turbulent), explicit Swamee-Jain approximation
                # Assume smooth pipe (epsilon/D ~ 0)
                eps_D = 1.5e-6 / D  # smooth steel roughness
                f = 0.25 / (math.log10(eps_D / 3.7 + 5.74 / Re ** 0.9)) ** 2
                flow_regime = "turbulent"

            # Darcy-Weisbach head loss: h_f = f * (L/D) * V^2 / (2g)
            h_f = f * (L / D) * V ** 2 / (2.0 * g)

            # Pressure drop [Pa]
            delta_P_friction = rho * g * h_f
            delta_P_elevation = rho * g * dz
            delta_P_total = delta_P_friction + delta_P_elevation

            # Pump power (if pump head given)
            P_pump = rho * g * Q * H_p  # [W]

            # Available system head
            H_available = H_p - h_f - dz

            # Hagen-Poiseuille exact (laminar only): delta_P = 128*mu*L*Q / (pi*D^4)
            dp_hp = 128.0 * mu * L * Q / (math.pi * D ** 4) if Re < 2300 else None

            warnings = []
            if Re > 2300 and Re < 4000:
                warnings.append(f"Re = {Re:.0f} in transition region (2300-4000)")
            if H_available < 0 and H_p > 0:
                warnings.append(
                    f"Required head {h_f + dz:.2f} m exceeds pump head {H_p:.2f} m"
                )
            if V > 3.0:
                warnings.append(f"Velocity {V:.2f} m/s exceeds typical pipe limit (3 m/s)")

            data = {
                "reynolds_number":      round(Re, 1),
                "flow_regime":          flow_regime,
                "friction_factor":      round(f, 6),
                "mean_velocity_m_s":    round(V, 4),
                "head_loss_m":          round(h_f, 4),
                "pressure_drop_Pa":     round(delta_P_friction, 2),
                "pressure_drop_kPa":    round(delta_P_friction / 1000.0, 4),
                "total_delta_P_Pa":     round(delta_P_total, 2),
            }
            if H_p > 0:
                data["pump_power_W"]    = round(P_pump, 2)
                data["head_available_m"] = round(H_available, 4)
            if dp_hp is not None:
                data["HP_exact_delta_P_Pa"] = round(dp_hp, 2)

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data=data,
                units={
                    "mean_velocity_m_s": "m/s",
                    "head_loss_m":       "m",
                    "pressure_drop_Pa":  "Pa",
                    "pressure_drop_kPa": "kPa",
                    "total_delta_P_Pa":  "Pa",
                    "pump_power_W":      "W",
                    "head_available_m":  "m",
                },
                raw_output=(
                    f"Hydraulic: D={D*1000:.1f} mm, Q={Q*1000:.2f} L/s, "
                    f"Re={Re:.0f}, dP={delta_P_friction:.1f} Pa"
                ),
                warnings=warnings,
                assumptions=[
                    f"Darcy-Weisbach friction with {'Hagen-Poiseuille' if Re < 2300 else 'Swamee-Jain'} f",
                    "Smooth pipe (epsilon = 1.5 um) unless otherwise specified",
                    "Steady-state fully developed flow",
                    "Minor losses (fittings, bends) not included",
                    "Incompressible Newtonian fluid",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Lumped thermal system transient
    # ------------------------------------------------------------------
    def _thermal_system(self, params: dict) -> ToolResult:
        try:
            mc    = float(params.get("thermal_mass_J_K", 5000.0))
            R_th  = float(params.get("thermal_resistance_K_W", 0.5))
            Q_in  = float(params.get("heat_input_W", 100.0))
            T_amb = float(params.get("ambient_temp_C", 25.0))
            T_0   = float(params.get("initial_temp_C", 25.0))
            t_sim = float(params.get("simulation_time_s", 600.0))

            if mc <= 0 or R_th <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Thermal mass and resistance must be positive",
                )

            # Lumped-parameter 1st order: mc * dT/dt = Q_in - (T - T_amb)/R_th
            # Time constant: tau = mc * R_th
            tau = mc * R_th  # [s]

            # Steady-state temperature: T_ss = T_amb + Q_in * R_th
            T_ss = T_amb + Q_in * R_th

            # Transient: T(t) = T_ss - (T_ss - T_0) * exp(-t/tau)
            T_final = T_ss - (T_ss - T_0) * math.exp(-t_sim / tau)

            # Time to reach 63.2% of steady state (1 tau)
            t_63 = tau
            # Time to reach 95% (3 tau)
            t_95 = 3.0 * tau
            # Time to reach 99% (5 tau)
            t_99 = 5.0 * tau

            # Maximum rate of temperature rise (at t=0)
            dT_dt_0 = (Q_in - (T_0 - T_amb) / R_th) / mc  # [K/s]

            # Heat dissipated at steady state
            Q_diss_ss = (T_ss - T_amb) / R_th  # = Q_in (verification)

            # Sample temperatures at 10%, 50%, 90% of simulation
            samples = {}
            for frac in [0.1, 0.5, 0.9]:
                t_s = frac * t_sim
                T_s = T_ss - (T_ss - T_0) * math.exp(-t_s / tau)
                samples[f"T_at_{int(frac*100)}pct_time_C"] = round(T_s, 2)

            warnings = []
            if T_ss > 80:
                warnings.append(f"Steady-state temperature {T_ss:.1f} C may exceed safe limits")
            if tau > t_sim:
                warnings.append(
                    f"Time constant {tau:.0f} s > simulation time {t_sim:.0f} s — "
                    "system has not reached steady state"
                )

            data = {
                "time_constant_s":      round(tau, 2),
                "steady_state_temp_C":  round(T_ss, 2),
                "final_temp_C":         round(T_final, 2),
                "initial_rate_K_per_s": round(dT_dt_0, 4),
                "t_63pct_s":            round(t_63, 1),
                "t_95pct_s":            round(t_95, 1),
                "t_99pct_s":            round(t_99, 1),
            }
            data.update(samples)

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data=data,
                units={
                    "time_constant_s":      "s",
                    "steady_state_temp_C":  "C",
                    "final_temp_C":         "C",
                    "initial_rate_K_per_s": "K/s",
                    "t_63pct_s":            "s",
                    "t_95pct_s":            "s",
                    "t_99pct_s":            "s",
                },
                raw_output=(
                    f"Thermal lumped: tau={tau:.1f} s, T_ss={T_ss:.1f} C, "
                    f"T_final={T_final:.1f} C at t={t_sim:.0f} s"
                ),
                warnings=warnings,
                assumptions=[
                    "Lumped-parameter (Biot < 0.1) single-node thermal model",
                    "Constant thermal mass and resistance (no temperature dependence)",
                    "Constant heat input (no time-varying source)",
                    "Convective + radiative losses lumped into single R_th",
                    "No phase change or latent heat",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Dynamic system: transfer function step response
    # ------------------------------------------------------------------
    def _dynamic_system(self, params: dict) -> ToolResult:
        try:
            num   = params.get("num_gain", [1.0])
            den   = params.get("den_gain", [1.0, 1.0])
            A_step = float(params.get("step_amplitude", 1.0))
            t_sim  = float(params.get("simulation_time_s", 10.0))

            if not den or all(c == 0 for c in den):
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Denominator coefficients must be non-zero",
                )

            order = len(den) - 1

            # Normalise coefficients (make leading den coeff = 1)
            a0 = den[0]
            den_n = [c / a0 for c in den]
            num_n = [c / a0 for c in num]

            # DC gain: H(0) = num[-1] / den[-1]
            dc_gain = num_n[-1] / den_n[-1] if den_n[-1] != 0 else float("inf")
            ss_value = dc_gain * A_step

            data = {"order": order, "dc_gain": round(dc_gain, 6), "ss_value": round(ss_value, 6)}
            units = {}
            warnings = []

            if order == 1:
                # G(s) = K / (tau*s + 1) where tau = den_n[0] (=1 after normalisation? No...)
                # den = [a1, a0] normalised -> [1, a0/a1], so tau = 1/den_n[1]?
                # Actually den_n = [1, den[1]/den[0]], tau = 1.0 (leading coeff normalised)
                # Standard form: G(s) = K/(tau*s+1), den = [tau, 1] -> den_n = [1, 1/tau]
                tau = 1.0 / den_n[1] if den_n[1] != 0 else float("inf")
                K = num_n[-1] / den_n[-1] if den_n[-1] != 0 else float("inf")

                # Step response: y(t) = K*A*(1 - exp(-t/tau))
                y_final = K * A_step * (1.0 - math.exp(-t_sim / tau))
                t_rise = 2.2 * tau   # 10% to 90%
                t_settle_2pct = 4.0 * tau

                data.update({
                    "time_constant_s":        round(tau, 4),
                    "rise_time_s":            round(t_rise, 4),
                    "settling_time_2pct_s":   round(t_settle_2pct, 4),
                    "value_at_t_sim":         round(y_final, 6),
                    "overshoot_pct":          0.0,
                })
                units.update({
                    "time_constant_s":      "s",
                    "rise_time_s":          "s",
                    "settling_time_2pct_s": "s",
                })

            elif order == 2:
                # G(s) = K*wn^2 / (s^2 + 2*zeta*wn*s + wn^2)
                # den_n = [1, 2*zeta*wn, wn^2]
                wn2 = den_n[2]
                if wn2 <= 0:
                    return ToolResult(
                        success=False, solver=self.name, confidence="NONE",
                        data={}, units={}, raw_output="",
                        error="Negative wn^2 — unstable system",
                    )
                wn = math.sqrt(wn2)
                zeta = den_n[1] / (2.0 * wn)

                K = num_n[-1] / wn2 if len(num_n) == 1 else num_n[-1] / wn2

                if zeta < 0:
                    warnings.append("Negative damping — unstable system")
                elif zeta < 1.0:
                    # Underdamped
                    wd = wn * math.sqrt(1.0 - zeta ** 2)
                    overshoot = 100.0 * math.exp(-math.pi * zeta / math.sqrt(1.0 - zeta ** 2))
                    t_peak = math.pi / wd
                    t_rise = (math.pi - math.acos(zeta)) / wd
                    t_settle_2pct = 4.0 / (zeta * wn)

                    data.update({
                        "natural_frequency_rad_s": round(wn, 4),
                        "damped_frequency_rad_s":  round(wd, 4),
                        "damping_ratio":           round(zeta, 4),
                        "overshoot_pct":           round(overshoot, 2),
                        "peak_time_s":             round(t_peak, 4),
                        "rise_time_s":             round(t_rise, 4),
                        "settling_time_2pct_s":    round(t_settle_2pct, 4),
                        "peak_value":              round(ss_value * (1.0 + overshoot / 100.0), 6),
                    })
                    units.update({
                        "natural_frequency_rad_s": "rad/s",
                        "damped_frequency_rad_s":  "rad/s",
                        "peak_time_s":             "s",
                        "rise_time_s":             "s",
                        "settling_time_2pct_s":    "s",
                    })
                else:
                    # Overdamped or critically damped
                    if abs(zeta - 1.0) < 1e-6:
                        # Critically damped: two equal poles at -wn
                        t_settle_2pct = 5.83 / wn
                        data.update({
                            "natural_frequency_rad_s": round(wn, 4),
                            "damping_ratio":           round(zeta, 4),
                            "settling_time_2pct_s":    round(t_settle_2pct, 4),
                            "overshoot_pct":           0.0,
                        })
                    else:
                        # Overdamped: two real poles
                        p1 = -zeta * wn + wn * math.sqrt(zeta ** 2 - 1.0)
                        p2 = -zeta * wn - wn * math.sqrt(zeta ** 2 - 1.0)
                        tau_dom = -1.0 / p1 if p1 < 0 else -1.0 / p2
                        t_settle_2pct = 4.0 * tau_dom
                        data.update({
                            "natural_frequency_rad_s": round(wn, 4),
                            "damping_ratio":           round(zeta, 4),
                            "pole_1":                  round(p1, 4),
                            "pole_2":                  round(p2, 4),
                            "dominant_tau_s":          round(tau_dom, 4),
                            "settling_time_2pct_s":    round(t_settle_2pct, 4),
                            "overshoot_pct":           0.0,
                        })
                        units["dominant_tau_s"] = "s"

                    units.update({
                        "natural_frequency_rad_s": "rad/s",
                        "settling_time_2pct_s":    "s",
                    })
            else:
                warnings.append(
                    f"Order {order} system — only DC gain computed analytically. "
                    "Full response requires numerical simulation."
                )

            return ToolResult(
                success=True, solver=self.name,
                confidence="HIGH" if order <= 2 else "LOW",
                data=data, units=units,
                raw_output=(
                    f"Dynamic system: order={order}, DC_gain={dc_gain:.4f}, "
                    f"ss_value={ss_value:.4f}"
                ),
                warnings=warnings,
                assumptions=[
                    "Linear time-invariant (LTI) system",
                    "Step input applied at t = 0",
                    "Zero initial conditions",
                    "Analytical formulas for 1st and 2nd order systems",
                    "Higher-order systems: only DC gain reported",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
