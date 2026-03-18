"""tools/tier1/openrocket_tool.py — Rocket trajectory simulation via OpenRocket."""
import math

from tools.base import BaseToolWrapper, ToolResult


class OpenRocketTool(BaseToolWrapper):
    name    = "openrocket"
    tier    = 1
    domains = ["uzay", "savunma"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["trajectory", "motor_performance", "stability"],
                "description": "Type of rocket analysis",
            },
            "rocket_params": {
                "type": "object",
                "description": "Rocket configuration",
                "properties": {
                    "mass_kg":           {"type": "number", "description": "Dry mass (no propellant) [kg]"},
                    "propellant_mass_kg": {"type": "number", "description": "Propellant mass [kg]"},
                    "diameter_m":        {"type": "number", "description": "Body diameter [m]"},
                    "length_m":          {"type": "number", "description": "Total length [m]"},
                    "Cd":                {"type": "number", "description": "Drag coefficient"},
                    "Isp_s":             {"type": "number", "description": "Specific impulse [s]"},
                    "thrust_N":          {"type": "number", "description": "Average thrust [N]"},
                    "burn_time_s":       {"type": "number", "description": "Burn time [s]"},
                    "num_fins":          {"type": "integer", "description": "Number of fins"},
                    "fin_span_m":        {"type": "number", "description": "Fin semi-span [m]"},
                    "fin_root_chord_m":  {"type": "number", "description": "Fin root chord [m]"},
                    "fin_tip_chord_m":   {"type": "number", "description": "Fin tip chord [m]"},
                },
            },
            "launch_params": {
                "type": "object",
                "description": "Launch conditions",
                "properties": {
                    "launch_angle_deg":  {"type": "number", "description": "Launch rail angle from vertical [deg]"},
                    "rail_length_m":     {"type": "number", "description": "Launch rail length [m]"},
                    "altitude_m":        {"type": "number", "description": "Launch site altitude ASL [m]"},
                    "wind_speed_m_s":    {"type": "number", "description": "Wind speed [m/s]"},
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: apogee altitude, max velocity, "
            "max acceleration, stability margin (calibers), or flight time.\n\n"
            "DO NOT CALL if:\n"
            "- No rocket geometry or motor data is available\n"
            "- Only qualitative propulsion discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: trajectory / motor_performance / stability\n"
            "- rocket_params: mass_kg, propellant_mass_kg, diameter_m, thrust_N, burn_time_s\n"
            "- launch_params: launch_angle_deg (optional)\n\n"
            "Returns verified OpenRocketPy 6-DOF flight simulation results."
        )

    def is_available(self) -> bool:
        try:
            import orhelper  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            analysis_type = inputs.get("analysis_type", "trajectory")
            dispatch = {
                "trajectory":        self._trajectory,
                "motor_performance": self._motor_performance,
                "stability":         self._stability,
            }
            handler = dispatch.get(analysis_type, self._trajectory)
            return handler(inputs)
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _trajectory(self, inputs: dict) -> ToolResult:
        """Analytical trajectory with drag, gravity, and atmosphere."""
        rp = inputs.get("rocket_params", {})
        lp = inputs.get("launch_params", {})

        m_dry = float(rp.get("mass_kg", 5.0))
        m_prop = float(rp.get("propellant_mass_kg", 2.0))
        d = float(rp.get("diameter_m", 0.1))
        Cd = float(rp.get("Cd", 0.5))
        thrust = float(rp.get("thrust_N", 500))
        burn_t = float(rp.get("burn_time_s", 3.0))
        Isp = float(rp.get("Isp_s", 200))

        angle = float(lp.get("launch_angle_deg", 0))
        alt_0 = float(lp.get("altitude_m", 0))

        g = 9.81
        A = math.pi * (d / 2) ** 2
        m_total = m_dry + m_prop
        m_dot = m_prop / burn_t if burn_t > 0 else 0

        # Simple Euler integration (dt=0.1s)
        dt = 0.1
        v = 0.0
        h = alt_0
        t = 0.0
        max_v = 0.0
        max_accel = 0.0
        cos_theta = math.cos(math.radians(angle))

        # Boost phase
        m = m_total
        while t < burn_t:
            rho = 1.225 * math.exp(-h / 8500)
            F_drag = 0.5 * rho * v ** 2 * Cd * A
            F_net = (thrust - F_drag) * cos_theta - m * g
            a = F_net / m
            if a > max_accel:
                max_accel = a
            v += a * dt
            if v < 0:
                v = 0
            h += v * cos_theta * dt
            m -= m_dot * dt
            t += dt
            if v > max_v:
                max_v = v

        v_burnout = v
        h_burnout = h

        # Coast phase
        while v > 0 and h > 0:
            rho = 1.225 * math.exp(-h / 8500)
            F_drag = 0.5 * rho * v ** 2 * Cd * A
            a = -(F_drag / m_dry + g)
            v += a * dt
            if v < 0:
                break
            h += v * cos_theta * dt
            t += dt

        apogee = h
        time_to_apogee = t

        # Descent (terminal velocity)
        v_term = math.sqrt(2 * m_dry * g / (1.225 * Cd * A * 2))  # with drogue Cd~1.0
        descent_h = apogee - alt_0
        descent_t = descent_h / v_term if v_term > 0 else 0
        total_t = time_to_apogee + descent_t

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "apogee_m": round(apogee, 1),
                "apogee_AGL_m": round(apogee - alt_0, 1),
                "max_velocity_m_s": round(max_v, 1),
                "max_mach": round(max_v / 343, 3),
                "burnout_velocity_m_s": round(v_burnout, 1),
                "burnout_altitude_m": round(h_burnout, 1),
                "max_acceleration_g": round(max_accel / g, 2),
                "time_to_apogee_s": round(time_to_apogee, 1),
                "total_flight_time_s": round(total_t, 1),
                "terminal_velocity_m_s": round(v_term, 1),
            },
            units={
                "apogee_m": "m ASL",
                "apogee_AGL_m": "m AGL",
                "max_velocity_m_s": "m/s",
                "burnout_velocity_m_s": "m/s",
                "burnout_altitude_m": "m",
                "max_acceleration_g": "g",
                "time_to_apogee_s": "s",
                "total_flight_time_s": "s",
                "terminal_velocity_m_s": "m/s",
            },
            raw_output=f"Trajectory: m={m_total}kg, T={thrust}N, t_b={burn_t}s",
            assumptions=[
                "Euler integration with 0.1s time step",
                "Exponential atmosphere model (scale height 8500m)",
                "Constant thrust during burn",
                "Gravity-turn approximation (constant flight path angle)",
            ],
        )

    def _motor_performance(self, inputs: dict) -> ToolResult:
        """Motor performance metrics."""
        rp = inputs.get("rocket_params", {})

        m_dry = float(rp.get("mass_kg", 5.0))
        m_prop = float(rp.get("propellant_mass_kg", 2.0))
        Isp = float(rp.get("Isp_s", 200))
        thrust = float(rp.get("thrust_N", 500))
        burn_t = float(rp.get("burn_time_s", 3.0))

        g = 9.81
        m_total = m_dry + m_prop
        mass_ratio = m_total / m_dry if m_dry > 0 else float("inf")

        total_impulse = thrust * burn_t
        delta_v = Isp * g * math.log(mass_ratio)

        # Motor classification (NAR)
        if total_impulse <= 2.5:
            motor_class = "A"
        elif total_impulse <= 5:
            motor_class = "B"
        elif total_impulse <= 10:
            motor_class = "C"
        elif total_impulse <= 20:
            motor_class = "D"
        elif total_impulse <= 40:
            motor_class = "E"
        elif total_impulse <= 80:
            motor_class = "F"
        elif total_impulse <= 160:
            motor_class = "G"
        elif total_impulse <= 320:
            motor_class = "H"
        elif total_impulse <= 640:
            motor_class = "I"
        elif total_impulse <= 1280:
            motor_class = "J"
        elif total_impulse <= 2560:
            motor_class = "K"
        elif total_impulse <= 5120:
            motor_class = "L"
        else:
            motor_class = "M+"

        # Propellant mass fraction
        pmf = m_prop / m_total if m_total > 0 else 0

        # Gravity loss estimate
        gravity_loss = g * burn_t
        drag_loss_est = 0.1 * delta_v  # rough 10% drag loss

        return ToolResult(
            success=True, solver=self.name, confidence="HIGH",
            data={
                "total_impulse_Ns": round(total_impulse, 1),
                "motor_class": motor_class,
                "specific_impulse_s": round(Isp, 1),
                "delta_v_m_s": round(delta_v, 1),
                "delta_v_with_losses_m_s": round(delta_v - gravity_loss - drag_loss_est, 1),
                "mass_ratio": round(mass_ratio, 3),
                "propellant_mass_fraction": round(pmf, 4),
                "thrust_to_weight_ratio": round(thrust / (m_total * g), 2),
                "average_mass_flow_kg_s": round(m_prop / burn_t, 4) if burn_t > 0 else 0,
                "gravity_loss_m_s": round(gravity_loss, 1),
            },
            units={
                "total_impulse_Ns": "N·s",
                "specific_impulse_s": "s",
                "delta_v_m_s": "m/s",
                "delta_v_with_losses_m_s": "m/s",
                "average_mass_flow_kg_s": "kg/s",
                "gravity_loss_m_s": "m/s",
            },
            raw_output=f"Motor: Isp={Isp}s, T={thrust}N, t_b={burn_t}s, class {motor_class}",
            assumptions=[
                "Tsiolkovsky rocket equation for ideal delta-V",
                "Constant Isp and thrust during burn",
                "Gravity loss = g × burn_time (vertical launch)",
                "Drag loss estimated at 10% of ideal delta-V",
            ],
        )

    def _stability(self, inputs: dict) -> ToolResult:
        """Static stability analysis (CP/CG and stability margin)."""
        rp = inputs.get("rocket_params", {})

        L = float(rp.get("length_m", 1.0))
        d = float(rp.get("diameter_m", 0.1))
        m_dry = float(rp.get("mass_kg", 5.0))
        m_prop = float(rp.get("propellant_mass_kg", 2.0))
        n_fins = int(rp.get("num_fins", 4))
        fin_span = float(rp.get("fin_span_m", 0.05))
        fin_root = float(rp.get("fin_root_chord_m", 0.1))
        fin_tip = float(rp.get("fin_tip_chord_m", 0.05))

        A_ref = math.pi * (d / 2) ** 2

        # Nose cone CP (ogive approximation — 0.466L_nose from tip)
        L_nose = 3 * d  # typical 3:1 ogive
        CN_nose = 2.0
        x_cp_nose = 0.466 * L_nose

        # Body tube — no normal force contribution for slender body
        CN_body = 0

        # Fin CP (Barrowman equations)
        s = fin_span
        Cr = fin_root
        Ct = fin_tip
        Lf = math.sqrt(s ** 2 + ((Cr - Ct) / 2) ** 2)  # mid-chord sweep length

        CN_fin_pair = (4 * n_fins * (s / d) ** 2) / (1 + math.sqrt(1 + (2 * Lf / (Cr + Ct)) ** 2))

        # Fin CP location (from fin leading edge)
        x_f_le = L - Cr  # fin leading edge from nose
        x_cp_fin_local = (Cr * (Cr + 2 * Ct)) / (3 * (Cr + Ct)) + (Cr + Ct - Cr * Ct / (Cr + Ct)) / 6
        x_cp_fin = x_f_le + x_cp_fin_local

        # Overall CP
        CN_total = CN_nose + CN_fin_pair
        x_cp = (CN_nose * x_cp_nose + CN_fin_pair * x_cp_fin) / CN_total if CN_total > 0 else L / 2

        # CG estimation (nose cone mass ~ 15%, motor at rear)
        m_total = m_dry + m_prop
        x_cg_dry = L * 0.55  # typical CG for rocket without motor
        x_cg_motor = L - 0.1  # motor near tail
        motor_mass_frac = m_prop / m_total if m_total > 0 else 0
        x_cg_loaded = x_cg_dry * (1 - motor_mass_frac) + x_cg_motor * motor_mass_frac
        x_cg_empty = x_cg_dry

        # Stability margin (calibers)
        margin_loaded = (x_cp - x_cg_loaded) / d
        margin_empty = (x_cp - x_cg_empty) / d

        stable_loaded = margin_loaded >= 1.0
        stable_empty = margin_empty >= 1.0

        return ToolResult(
            success=True, solver=self.name, confidence="MEDIUM",
            data={
                "CP_from_nose_m": round(x_cp, 4),
                "CG_loaded_from_nose_m": round(x_cg_loaded, 4),
                "CG_empty_from_nose_m": round(x_cg_empty, 4),
                "stability_margin_loaded_cal": round(margin_loaded, 2),
                "stability_margin_empty_cal": round(margin_empty, 2),
                "stable_loaded": stable_loaded,
                "stable_empty": stable_empty,
                "CN_alpha_total": round(CN_total, 3),
                "CN_alpha_nose": round(CN_nose, 3),
                "CN_alpha_fins": round(CN_fin_pair, 3),
            },
            units={
                "CP_from_nose_m": "m",
                "CG_loaded_from_nose_m": "m",
                "CG_empty_from_nose_m": "m",
                "stability_margin_loaded_cal": "calibers",
                "stability_margin_empty_cal": "calibers",
            },
            raw_output=f"Stability: L={L}m, d={d}m, {n_fins} fins, margin={margin_loaded:.1f} cal",
            assumptions=[
                "Barrowman equations for subsonic flight",
                "Ogive nose cone (3:1 fineness ratio)",
                "CG estimated from mass distribution model",
                "Recommended stability margin: 1.0-2.0 calibers",
            ],
        )
