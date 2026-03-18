"""tools/tier1/sumo_tool.py — Traffic simulation and vehicle dynamics via SUMO."""
import math

from tools.base import BaseToolWrapper, ToolResult


class SUMOTool(BaseToolWrapper):
    name    = "sumo"
    tier    = 1
    domains = ["otomotiv"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["traffic_flow", "vehicle_dynamics", "intersection_analysis"],
                "description": "Type of traffic / vehicle dynamics analysis",
            },
            "parameters": {
                "type": "object",
                "description": "Traffic and vehicle parameters",
                "properties": {
                    "density_veh_km": {
                        "type": "number",
                        "description": "Traffic density [vehicles/km]",
                    },
                    "free_flow_speed_km_h": {
                        "type": "number",
                        "description": "Free-flow speed Vf [km/h]",
                    },
                    "jam_density_veh_km": {
                        "type": "number",
                        "description": "Jam density k_j [vehicles/km]",
                    },
                    "num_lanes": {
                        "type": "integer",
                        "description": "Number of lanes",
                    },
                    "vehicle_mass_kg": {
                        "type": "number",
                        "description": "Vehicle mass [kg]",
                    },
                    "wheelbase_m": {
                        "type": "number",
                        "description": "Wheelbase length [m]",
                    },
                    "speed_m_s": {
                        "type": "number",
                        "description": "Vehicle speed [m/s]",
                    },
                    "steering_angle_deg": {
                        "type": "number",
                        "description": "Front wheel steering angle [deg]",
                    },
                    "CG_height_m": {
                        "type": "number",
                        "description": "Centre of gravity height [m]",
                    },
                    "front_cornering_stiffness_N_rad": {
                        "type": "number",
                        "description": "Front axle cornering stiffness C_f [N/rad]",
                    },
                    "rear_cornering_stiffness_N_rad": {
                        "type": "number",
                        "description": "Rear axle cornering stiffness C_r [N/rad]",
                    },
                    "dist_CG_front_m": {
                        "type": "number",
                        "description": "Distance from CG to front axle [m]",
                    },
                    "dist_CG_rear_m": {
                        "type": "number",
                        "description": "Distance from CG to rear axle [m]",
                    },
                    "cycle_length_s": {
                        "type": "number",
                        "description": "Signal cycle length [s]",
                    },
                    "green_time_s": {
                        "type": "number",
                        "description": "Effective green time [s]",
                    },
                    "arrival_rate_veh_h": {
                        "type": "number",
                        "description": "Arrival flow rate [veh/h]",
                    },
                    "saturation_flow_veh_h": {
                        "type": "number",
                        "description": "Saturation flow rate [veh/h], default 1800",
                    },
                    "num_phases": {
                        "type": "integer",
                        "description": "Number of signal phases",
                    },
                    "lost_time_per_phase_s": {
                        "type": "number",
                        "description": "Start-up lost time per phase [s]",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "Performs traffic and vehicle dynamics analysis: macroscopic traffic flow "
            "using the Greenshields model (speed-density-flow fundamental diagram), "
            "bicycle-model vehicle lateral dynamics with understeer gradient computation, "
            "and signalised intersection analysis using the Webster delay formula. "
            "Accepts traffic densities, vehicle parameters, and signal timing data. "
            "Use for traffic impact assessment, vehicle handling evaluation, or "
            "intersection level-of-service estimation."
        )

    def is_available(self) -> bool:
        try:
            import traci  # noqa: F401  (SUMO TraCI Python interface)
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "traffic_flow")
        params = inputs.get("parameters", {})

        dispatch = {
            "traffic_flow":         self._traffic_flow,
            "vehicle_dynamics":     self._vehicle_dynamics,
            "intersection_analysis": self._intersection_analysis,
        }
        handler = dispatch.get(analysis_type, self._traffic_flow)
        return handler(params)

    # ------------------------------------------------------------------
    # Greenshields macroscopic traffic flow model
    # ------------------------------------------------------------------
    def _traffic_flow(self, params: dict) -> ToolResult:
        try:
            k     = float(params.get("density_veh_km", 30.0))
            Vf    = float(params.get("free_flow_speed_km_h", 100.0))
            k_j   = float(params.get("jam_density_veh_km", 150.0))
            lanes = int(params.get("num_lanes", 2))

            if k < 0 or k_j <= 0 or Vf <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Density, jam density, and free-flow speed must be positive",
                )

            # Greenshields linear model: V = Vf * (1 - k/k_j)
            V = Vf * (1.0 - k / k_j) if k <= k_j else 0.0
            V = max(V, 0.0)

            # Flow: q = k * V [veh/h]
            q = k * V

            # Capacity (max flow): at k_c = k_j/2, V_c = Vf/2
            k_c = k_j / 2.0
            V_c = Vf / 2.0
            q_max = k_c * V_c  # = Vf * k_j / 4

            # Per-lane values
            q_per_lane = q / lanes
            q_max_per_lane = q_max / lanes

            # Volume-to-capacity ratio
            vc_ratio = q / q_max if q_max > 0 else 0.0

            # Level of service (HCM freeway criteria, approximate)
            if vc_ratio <= 0.35:
                los = "A"
            elif vc_ratio <= 0.55:
                los = "B"
            elif vc_ratio <= 0.77:
                los = "C"
            elif vc_ratio <= 0.92:
                los = "D"
            elif vc_ratio <= 1.0:
                los = "E"
            else:
                los = "F"

            # Space mean speed to time mean speed correction
            # V_t = V_s + sigma^2 / V_s (approximate, assume sigma = 0.15*V)
            sigma_v = 0.15 * V if V > 0 else 0.0
            V_time = V + (sigma_v ** 2 / V) if V > 0 else 0.0

            # Spacing and headway
            spacing_m = 1000.0 / k if k > 0 else float("inf")
            headway_s = 3600.0 / q if q > 0 else float("inf")

            # Wave speed (kinematic wave): c = dq/dk = Vf*(1 - 2k/k_j)
            c_wave = Vf * (1.0 - 2.0 * k / k_j)

            warnings = []
            if k > k_j:
                warnings.append(f"Density {k} veh/km exceeds jam density {k_j} veh/km")
            if vc_ratio > 0.85:
                warnings.append(f"V/C = {vc_ratio:.2f} — approaching or at capacity, expect delays")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "speed_km_h":             round(V, 2),
                    "flow_veh_h":             round(q, 1),
                    "flow_per_lane_veh_h":    round(q_per_lane, 1),
                    "capacity_veh_h":         round(q_max, 1),
                    "capacity_per_lane_veh_h": round(q_max_per_lane, 1),
                    "vc_ratio":               round(vc_ratio, 4),
                    "level_of_service":       los,
                    "critical_density_veh_km": round(k_c, 1),
                    "critical_speed_km_h":    round(V_c, 2),
                    "spacing_m":              round(spacing_m, 2),
                    "headway_s":              round(headway_s, 2),
                    "wave_speed_km_h":        round(c_wave, 2),
                    "time_mean_speed_km_h":   round(V_time, 2),
                },
                units={
                    "speed_km_h":           "km/h",
                    "flow_veh_h":           "veh/h",
                    "flow_per_lane_veh_h":  "veh/h",
                    "capacity_veh_h":       "veh/h",
                    "critical_density_veh_km": "veh/km",
                    "critical_speed_km_h":  "km/h",
                    "spacing_m":            "m",
                    "headway_s":            "s",
                    "wave_speed_km_h":      "km/h",
                    "time_mean_speed_km_h": "km/h",
                },
                raw_output=(
                    f"Greenshields: k={k} veh/km, V={V:.1f} km/h, "
                    f"q={q:.0f} veh/h, LOS={los}"
                ),
                warnings=warnings,
                assumptions=[
                    f"Greenshields linear model: V = Vf*(1 - k/k_j), Vf={Vf} km/h, k_j={k_j} veh/km",
                    "Single regime (no multi-regime Greenberg/Underwood)",
                    f"Number of lanes = {lanes} (uniform cross-section)",
                    "Level of service based on HCM freeway V/C thresholds",
                    "Speed variance estimated as 15% of mean for V_t correction",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Bicycle model vehicle dynamics
    # ------------------------------------------------------------------
    def _vehicle_dynamics(self, params: dict) -> ToolResult:
        try:
            m     = float(params.get("vehicle_mass_kg", 1500.0))
            L     = float(params.get("wheelbase_m", 2.7))
            V     = float(params.get("speed_m_s", 20.0))
            delta  = float(params.get("steering_angle_deg", 5.0))
            h_cg  = float(params.get("CG_height_m", 0.55))
            C_f   = float(params.get("front_cornering_stiffness_N_rad", 80000.0))
            C_r   = float(params.get("rear_cornering_stiffness_N_rad", 85000.0))
            a     = float(params.get("dist_CG_front_m", 1.2))
            b     = float(params.get("dist_CG_rear_m", 1.5))
            g     = 9.81

            delta_rad = math.radians(delta)

            # Kinematic steering (low speed): R = L / tan(delta)
            R_kin = L / math.tan(delta_rad) if delta_rad != 0 else float("inf")

            # Understeer gradient: K_us = (m/(L)) * (b/C_f - a/C_r)  [rad/m/s^2]
            # Actually: K_us = m * (b*C_r - a*C_f) / (L * C_f * C_r) ... but sign convention:
            # Standard: K_us = m/(L^2) * (a/C_r - b/C_f) ... use Milliken convention
            # K_us = (m*a)/(L*C_r) - (m*b)/(L*C_f) ... wait, let's use consistent formulation
            # Understeer gradient K = W_f/C_f - W_r/C_r where W_f = m*g*b/L, W_r = m*g*a/L
            W_f = m * g * b / L
            W_r = m * g * a / L
            K_us = W_f / C_f - W_r / C_r  # [rad/(m/s^2)] — positive = understeer

            # Characteristic / critical speed
            if K_us > 0:
                # Understeer: characteristic speed
                V_char = math.sqrt(L * g / K_us) if K_us > 0 else float("inf")
                stability = "understeer"
            elif K_us < 0:
                # Oversteer: critical speed
                V_crit = math.sqrt(-L * g / K_us)
                V_char = V_crit
                stability = "oversteer"
            else:
                V_char = float("inf")
                stability = "neutral"

            # Steady-state yaw rate: r = V / (L * (1 + K_us * V^2 / (L*g))) * delta
            denom_ss = L + K_us * V ** 2 / g
            if abs(denom_ss) > 1e-6:
                r_ss = V * delta_rad / denom_ss
            else:
                r_ss = float("inf")

            # Steady-state lateral acceleration
            a_lat = V * r_ss if r_ss != float("inf") else float("inf")

            # Turning radius (dynamic)
            R_dyn = V / r_ss if r_ss != 0 and r_ss != float("inf") else float("inf")

            # Yaw natural frequency (bicycle model)
            # wn^2 = (C_f*C_r*L^2) / (m*Iz*V^2) + (C_f*a - C_r*b)/Iz ... simplified
            # Use approximate: wn = sqrt((C_f + C_r)/(m*V)) for moderate speeds
            Iz = m * (L * 0.4) ** 2  # rough yaw inertia estimate
            if V > 0.1:
                wn_yaw = math.sqrt(
                    (C_f * C_r * L ** 2) / (Iz * m * V ** 2)
                    * (1.0 + K_us * V ** 2 / (L * g))
                )
            else:
                wn_yaw = 0.0

            # Lateral load transfer in a turn
            F_lat = m * a_lat if a_lat != float("inf") else 0.0
            dF_z = m * a_lat * h_cg / L if a_lat != float("inf") else 0.0  # simplified

            # Rollover threshold: a_y_max ~ g * track_width / (2 * h_cg)
            track = 1.55  # assume typical track width [m]
            a_roll = g * track / (2.0 * h_cg)

            warnings = []
            if stability == "oversteer" and V > V_char:
                warnings.append(
                    f"Speed {V:.1f} m/s exceeds critical speed {V_char:.1f} m/s — "
                    "unstable oversteer"
                )
            if a_lat != float("inf") and abs(a_lat) > 0.8 * g:
                warnings.append(
                    f"Lateral acceleration {a_lat:.2f} m/s^2 ({a_lat/g:.2f} g) — "
                    "near tyre grip limit"
                )

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "understeer_gradient_rad_per_ms2": round(K_us, 6),
                    "understeer_gradient_deg_per_g":   round(math.degrees(K_us) * g, 3),
                    "stability_type":                  stability,
                    "characteristic_speed_m_s":        round(V_char, 2) if V_char != float("inf") else "inf",
                    "characteristic_speed_km_h":       round(V_char * 3.6, 1) if V_char != float("inf") else "inf",
                    "yaw_rate_rad_s":                  round(r_ss, 4) if r_ss != float("inf") else "inf",
                    "yaw_rate_deg_s":                  round(math.degrees(r_ss), 2) if r_ss != float("inf") else "inf",
                    "lateral_accel_m_s2":              round(a_lat, 3) if a_lat != float("inf") else "inf",
                    "lateral_accel_g":                 round(a_lat / g, 4) if a_lat != float("inf") else "inf",
                    "kinematic_radius_m":              round(R_kin, 2) if R_kin != float("inf") else "inf",
                    "dynamic_radius_m":                round(R_dyn, 2) if R_dyn != float("inf") else "inf",
                    "yaw_natural_freq_rad_s":          round(wn_yaw, 3),
                    "rollover_threshold_g":            round(a_roll / g, 3),
                    "lateral_load_transfer_N":         round(dF_z, 1) if a_lat != float("inf") else 0.0,
                },
                units={
                    "understeer_gradient_deg_per_g": "deg/g",
                    "characteristic_speed_m_s":      "m/s",
                    "characteristic_speed_km_h":     "km/h",
                    "yaw_rate_rad_s":                "rad/s",
                    "yaw_rate_deg_s":                "deg/s",
                    "lateral_accel_m_s2":            "m/s^2",
                    "kinematic_radius_m":            "m",
                    "dynamic_radius_m":              "m",
                    "yaw_natural_freq_rad_s":        "rad/s",
                    "lateral_load_transfer_N":       "N",
                },
                raw_output=(
                    f"Bicycle model: V={V} m/s, delta={delta} deg, "
                    f"K_us={math.degrees(K_us)*g:.2f} deg/g, {stability}"
                ),
                warnings=warnings,
                assumptions=[
                    "Linear bicycle model (small slip angles)",
                    "Constant cornering stiffness (linear tyre region)",
                    f"Yaw inertia Iz estimated as m*(0.4*L)^2 = {Iz:.0f} kg.m^2",
                    f"Track width assumed {track} m for rollover estimate",
                    "No aerodynamic effects, no suspension compliance",
                    "Steady-state cornering (no transient manoeuvre)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Signalised intersection (Webster delay formula)
    # ------------------------------------------------------------------
    def _intersection_analysis(self, params: dict) -> ToolResult:
        try:
            C     = float(params.get("cycle_length_s", 90.0))
            g     = float(params.get("green_time_s", 35.0))
            q     = float(params.get("arrival_rate_veh_h", 800.0))
            s     = float(params.get("saturation_flow_veh_h", 1800.0))
            n_ph  = int(params.get("num_phases", 2))
            L_ph  = float(params.get("lost_time_per_phase_s", 3.0))

            # Green ratio
            lam = g / C  # effective green ratio

            # Degree of saturation (X): X = q / (s * lambda)
            cap = s * lam  # capacity of the approach [veh/h]
            X = q / cap if cap > 0 else float("inf")

            # Webster's minimum delay per vehicle [s]:
            # d = C*(1-lambda)^2 / (2*(1-lambda*X)) + X^2 / (2*q*(1-X)) - 0.65*(C/q^2)^(1/3)*X^(2+5*lambda)

            # Uniform delay (d1)
            denom1 = 1.0 - lam * min(X, 1.0)
            d1 = C * (1.0 - lam) ** 2 / (2.0 * max(denom1, 0.01))

            # Overflow delay (d2)
            if X < 1.0:
                d2 = X ** 2 / (2.0 * (q / 3600.0) * (1.0 - X))
            else:
                # Oversaturated: use deterministic queue accumulation
                d2 = (X - 1.0) * C / 2.0 * 15.0  # 15 min analysis period approximation
                d2 = min(d2, 300.0)  # cap

            # Webster correction term
            d3 = 0.65 * (C / max(q, 1) ** 2) ** (1.0 / 3.0) * X ** (2.0 + 5.0 * lam)

            d_webster = max(d1 + d2 - d3, 0.0)

            # HCM simplified: d = d1*PF + d2 + d3 (PF=1 for fixed signals)
            d_HCM = d1 + d2  # simplified (no d3 incremental)

            # Webster optimal cycle length
            # C_opt = (1.5*L + 5) / (1 - sum(y_i))
            L_total = n_ph * L_ph
            y = q / s  # flow ratio for this approach
            # Assume critical y_sum ~ y * n_phases / some factor ... simplified single approach
            y_sum = min(y, 0.95)
            C_opt = (1.5 * L_total + 5.0) / (1.0 - y_sum) if y_sum < 1.0 else 120.0
            C_opt = max(min(C_opt, 180.0), 30.0)

            # Queue length estimate (uniform arrival): max queue = q * r / 3600
            # where r = C - g (red time)
            r = C - g
            queue_max = q * r / 3600.0  # vehicles
            queue_avg = queue_max / 2.0

            # Level of service (HCM signalised intersection)
            if d_webster <= 10:
                los = "A"
            elif d_webster <= 20:
                los = "B"
            elif d_webster <= 35:
                los = "C"
            elif d_webster <= 55:
                los = "D"
            elif d_webster <= 80:
                los = "E"
            else:
                los = "F"

            # Capacity utilisation
            reserve_cap = cap - q  # veh/h

            warnings = []
            if X > 1.0:
                warnings.append(
                    f"Degree of saturation X = {X:.2f} > 1.0 — oversaturated, "
                    "queues will grow indefinitely"
                )
            if X > 0.85 and X <= 1.0:
                warnings.append(
                    f"X = {X:.2f} approaching capacity — sensitive to demand fluctuations"
                )
            if C > 150:
                warnings.append("Cycle length > 150 s — poor pedestrian service")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "webster_delay_s":          round(d_webster, 2),
                    "uniform_delay_s":          round(d1, 2),
                    "overflow_delay_s":         round(d2, 2),
                    "degree_of_saturation":     round(X, 4),
                    "capacity_veh_h":           round(cap, 1),
                    "reserve_capacity_veh_h":   round(reserve_cap, 1),
                    "green_ratio":              round(lam, 4),
                    "level_of_service":         los,
                    "optimal_cycle_length_s":   round(C_opt, 1),
                    "max_queue_veh":            round(queue_max, 1),
                    "avg_queue_veh":            round(queue_avg, 1),
                    "red_time_s":               round(r, 1),
                },
                units={
                    "webster_delay_s":        "s/veh",
                    "uniform_delay_s":        "s/veh",
                    "overflow_delay_s":       "s/veh",
                    "capacity_veh_h":         "veh/h",
                    "reserve_capacity_veh_h": "veh/h",
                    "optimal_cycle_length_s": "s",
                    "max_queue_veh":          "veh",
                    "avg_queue_veh":          "veh",
                    "red_time_s":             "s",
                },
                raw_output=(
                    f"Webster: C={C} s, g={g} s, q={q} veh/h, "
                    f"X={X:.3f}, d={d_webster:.1f} s, LOS={los}"
                ),
                warnings=warnings,
                assumptions=[
                    "Webster delay formula for fixed-time signal control",
                    f"Saturation flow s = {s} veh/h (default or user-supplied)",
                    f"Lost time {L_ph} s/phase x {n_ph} phases = {L_total} s/cycle",
                    "Uniform arrival distribution (no platoon effects, PF = 1.0)",
                    "Single approach analysis — extend for full intersection",
                    "Optimal cycle from Webster formula: C_opt = (1.5L + 5)/(1 - Y)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
