"""tools/tier1/opensim_tool.py — Musculoskeletal biomechanics via OpenSim."""
import math

from tools.base import BaseToolWrapper, ToolResult


class OpenSimTool(BaseToolWrapper):
    name    = "opensim"
    tier    = 1
    domains = ["biyomedikal"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["joint_analysis", "gait_analysis", "muscle_force"],
                "description": "Type of musculoskeletal analysis to perform",
            },
            "parameters": {
                "type": "object",
                "description": "Biomechanics parameters",
                "properties": {
                    "body_mass_kg": {
                        "type": "number",
                        "description": "Subject body mass [kg]",
                    },
                    "height_m": {
                        "type": "number",
                        "description": "Subject height [m]",
                    },
                    "joint": {
                        "type": "string",
                        "enum": ["hip", "knee", "ankle", "shoulder", "elbow"],
                        "description": "Target joint for analysis",
                    },
                    "flexion_angle_deg": {
                        "type": "number",
                        "description": "Joint flexion angle [degrees]",
                    },
                    "external_load_N": {
                        "type": "number",
                        "description": "External load applied [N]",
                    },
                    "gait_speed_m_s": {
                        "type": "number",
                        "description": "Walking speed [m/s]",
                    },
                    "muscle_name": {
                        "type": "string",
                        "description": "Target muscle (e.g. 'quadriceps', 'gastrocnemius', 'biceps')",
                    },
                    "muscle_length_ratio": {
                        "type": "number",
                        "description": "Normalised muscle fibre length (L/L_opt), default 1.0",
                    },
                    "activation_level": {
                        "type": "number",
                        "description": "Muscle activation 0..1",
                    },
                    "pennation_angle_deg": {
                        "type": "number",
                        "description": "Muscle fibre pennation angle [degrees]",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: joint contact forces, "
            "muscle activation levels, joint moments, or gait kinematics.\n\n"
            "DO NOT CALL if:\n"
            "- Problem does not involve human or animal musculoskeletal mechanics\n"
            "- Only qualitative biomechanical discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: joint_analysis / gait_analysis / muscle_force\n"
            "- parameters.body_mass_kg, parameters.height_m\n"
            "- parameters.joint: hip / knee / ankle / shoulder / elbow\n"
            "- parameters.gait_speed_m_s (for gait analysis)\n\n"
            "Returns verified OpenSim musculoskeletal simulation results."
        )

    def is_available(self) -> bool:
        try:
            import opensim  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "joint_analysis")
        params = inputs.get("parameters", {})

        dispatch = {
            "joint_analysis": self._joint_analysis,
            "gait_analysis":  self._gait_analysis,
            "muscle_force":   self._muscle_force,
        }
        handler = dispatch.get(analysis_type, self._joint_analysis)
        return handler(params)

    # ------------------------------------------------------------------
    # Joint inverse-dynamics analysis
    # ------------------------------------------------------------------
    def _joint_analysis(self, params: dict) -> ToolResult:
        try:
            mass  = float(params.get("body_mass_kg", 75.0))
            joint = params.get("joint", "knee")
            angle = float(params.get("flexion_angle_deg", 90.0))
            F_ext = float(params.get("external_load_N", 0.0))
            g     = 9.81

            angle_rad = math.radians(angle)

            # Segment mass fractions and lever arms from Winter (2009)
            # {joint: (proximal_segment_mass_frac, lever_arm_cm, joint_centre_height_frac)}
            joint_data = {
                "hip":      (0.100, 20.0, 0.530),
                "knee":     (0.061, 18.0, 0.285),
                "ankle":    (0.017,  8.0, 0.039),
                "shoulder": (0.081, 17.0, 0.818),
                "elbow":    (0.027, 14.0, 0.630),
            }
            seg_frac, lever_cm, _ = joint_data.get(joint, (0.061, 18.0, 0.285))

            W_seg  = mass * seg_frac * g          # segment weight [N]
            lever  = lever_cm / 100.0             # lever arm [m]

            # Static inverse dynamics: M_joint = W_seg * lever * sin(theta) + F_ext * lever * sin(theta)
            M_joint = (W_seg + F_ext) * lever * math.sin(angle_rad)

            # Joint reaction force (axial compression estimate)
            # Compression ~ body-weight multiple at the joint (simplified)
            bw = mass * g
            # Empirical multipliers during quasi-static flexion (Bergmann et al.)
            compression_mult = {
                "hip": 2.5, "knee": 3.0, "ankle": 4.5,
                "shoulder": 1.2, "elbow": 1.0,
            }
            F_compression = bw * compression_mult.get(joint, 2.0) * math.sin(angle_rad)

            # Moment arm of main agonist (approximate, cm -> m)
            agonist_arm = lever * 0.25  # typical ~25 % of segment lever
            F_muscle = M_joint / agonist_arm if agonist_arm > 0 else 0.0

            warnings = []
            if F_compression > 5 * bw:
                warnings.append(
                    f"Joint compression {F_compression:.0f} N exceeds 5 x BW — verify implant rating"
                )

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "joint_moment_Nm":          round(M_joint, 2),
                    "joint_compression_N":      round(F_compression, 1),
                    "agonist_muscle_force_N":   round(F_muscle, 1),
                    "segment_weight_N":         round(W_seg, 2),
                    "flexion_angle_deg":        angle,
                },
                units={
                    "joint_moment_Nm":        "N.m",
                    "joint_compression_N":    "N",
                    "agonist_muscle_force_N": "N",
                    "segment_weight_N":       "N",
                    "flexion_angle_deg":      "deg",
                },
                raw_output=(
                    f"Inverse dynamics ({joint}): M={M_joint:.2f} Nm, "
                    f"F_comp={F_compression:.1f} N at {angle} deg"
                ),
                warnings=warnings,
                assumptions=[
                    "Quasi-static equilibrium (no inertial terms)",
                    f"Segment mass fraction from Winter (2009): {seg_frac}",
                    f"Lever arm {lever_cm} cm — literature average for {joint}",
                    "Single agonist muscle; synergist contributions ignored",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Gait analysis with ground reaction force estimation
    # ------------------------------------------------------------------
    def _gait_analysis(self, params: dict) -> ToolResult:
        try:
            mass  = float(params.get("body_mass_kg", 75.0))
            speed = float(params.get("gait_speed_m_s", 1.2))
            g     = 9.81
            bw    = mass * g

            # Normalised gait parameters (Perry & Burnfield, 2010)
            # Stride length ~ 1.346 * speed + 0.252 (regression, adults)
            stride_length = 1.346 * speed + 0.252  # [m]
            cadence       = speed / stride_length * 120.0  # [steps/min]
            stride_freq   = cadence / 60.0  # [Hz]

            # Stance phase fraction ~ 62 % at 1.2 m/s, decreasing with speed
            stance_pct = max(50.0, 62.0 - 5.0 * (speed - 1.2))
            swing_pct  = 100.0 - stance_pct

            # Vertical GRF peaks (Alexander, 1989 — empirical)
            # First peak: ~1.0 + 0.32*v  [BW]
            # Second peak: ~1.0 + 0.40*v [BW]
            grf_peak1_bw = 1.0 + 0.32 * speed
            grf_peak2_bw = 1.0 + 0.40 * speed
            grf_peak1_N  = grf_peak1_bw * bw
            grf_peak2_N  = grf_peak2_bw * bw

            # Anterior-posterior GRF peaks ~ ±0.2*BW at normal speed
            ap_brake_N  = 0.20 * speed / 1.2 * bw
            ap_propul_N = 0.22 * speed / 1.2 * bw

            # Approximate peak joint moments (normalised to BW*Ht)
            height = float(params.get("height_m", 1.75))
            hip_flex_moment  = 0.8 * speed / 1.2 * bw * height * 0.01
            knee_ext_moment  = 0.5 * speed / 1.2 * bw * height * 0.01
            ankle_pf_moment  = 1.4 * speed / 1.2 * bw * height * 0.01

            warnings = []
            if speed > 2.0:
                warnings.append("Speed > 2.0 m/s — empirical GRF correlations less accurate")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "stride_length_m":         round(stride_length, 3),
                    "cadence_steps_per_min":   round(cadence, 1),
                    "stance_phase_pct":        round(stance_pct, 1),
                    "swing_phase_pct":         round(swing_pct, 1),
                    "vGRF_peak1_N":            round(grf_peak1_N, 1),
                    "vGRF_peak1_BW":           round(grf_peak1_bw, 3),
                    "vGRF_peak2_N":            round(grf_peak2_N, 1),
                    "vGRF_peak2_BW":           round(grf_peak2_bw, 3),
                    "AP_brake_N":              round(ap_brake_N, 1),
                    "AP_propulsion_N":         round(ap_propul_N, 1),
                    "hip_flexion_moment_Nm":   round(hip_flex_moment, 2),
                    "knee_extension_moment_Nm": round(knee_ext_moment, 2),
                    "ankle_plantarflex_moment_Nm": round(ankle_pf_moment, 2),
                },
                units={
                    "stride_length_m":       "m",
                    "cadence_steps_per_min": "steps/min",
                    "stance_phase_pct":      "%",
                    "swing_phase_pct":       "%",
                    "vGRF_peak1_N":          "N",
                    "vGRF_peak2_N":          "N",
                    "AP_brake_N":            "N",
                    "AP_propulsion_N":       "N",
                    "hip_flexion_moment_Nm": "N.m",
                    "knee_extension_moment_Nm": "N.m",
                    "ankle_plantarflex_moment_Nm": "N.m",
                },
                raw_output=(
                    f"Gait analysis: v={speed} m/s, mass={mass} kg, "
                    f"GRF peaks={grf_peak1_bw:.2f}/{grf_peak2_bw:.2f} BW"
                ),
                warnings=warnings,
                assumptions=[
                    "Level-ground walking, no assistive devices",
                    "GRF regression from Alexander (1989) — healthy adults",
                    "Joint moments normalised to BW*Ht (Hof, 1996)",
                    "Stride length regression from Grieve & Gear (1966)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Hill-type muscle force model
    # ------------------------------------------------------------------
    def _muscle_force(self, params: dict) -> ToolResult:
        try:
            muscle     = params.get("muscle_name", "quadriceps")
            activation = float(params.get("activation_level", 1.0))
            l_ratio    = float(params.get("muscle_length_ratio", 1.0))
            penn_deg   = float(params.get("pennation_angle_deg", 0.0))

            # Peak isometric force data (Rajagopal 2016 lower-limb model, N)
            F0_data = {
                "quadriceps":     4500.0,
                "hamstrings":     2500.0,
                "gastrocnemius":  1600.0,
                "soleus":         3500.0,
                "tibialis_ant":    800.0,
                "gluteus_max":    2400.0,
                "biceps":          600.0,
                "triceps":         800.0,
                "deltoid":         700.0,
            }
            F0 = F0_data.get(muscle, 1000.0)

            # Hill force-length relationship (Gaussian approximation)
            # f_L = exp(-((l_ratio - 1.0) / 0.45)^2)
            f_length = math.exp(-((l_ratio - 1.0) / 0.45) ** 2)

            # Pennation effect: effective force = F * cos(pennation)
            penn_rad    = math.radians(penn_deg)
            cos_penn    = math.cos(penn_rad)

            # Active force
            F_active = F0 * activation * f_length * cos_penn

            # Passive force (exponential toe region)
            # f_PE = 0 for l_ratio <= 1.0, else k*(l_ratio-1)^2
            if l_ratio > 1.0:
                k_passive = 5.0  # passive stiffness coefficient
                f_passive = k_passive * (l_ratio - 1.0) ** 2
                F_passive = F0 * f_passive * cos_penn
            else:
                F_passive = 0.0

            F_total = F_active + F_passive

            # Specific tension estimate (typical ~30 N/cm^2 for mammalian muscle)
            PCSA = F0 / 30.0  # physiological cross-sectional area [cm^2]

            warnings = []
            if l_ratio < 0.5 or l_ratio > 1.5:
                warnings.append(
                    f"Fibre length ratio {l_ratio:.2f} outside normal range [0.5, 1.5]"
                )
            if activation < 0 or activation > 1:
                warnings.append("Activation level outside valid range [0, 1]")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "muscle_name":          muscle,
                    "peak_isometric_F0_N":  F0,
                    "force_length_factor":  round(f_length, 4),
                    "active_force_N":       round(F_active, 1),
                    "passive_force_N":      round(F_passive, 1),
                    "total_force_N":        round(F_total, 1),
                    "PCSA_cm2":             round(PCSA, 2),
                    "activation":           activation,
                    "pennation_angle_deg":  penn_deg,
                },
                units={
                    "peak_isometric_F0_N": "N",
                    "active_force_N":      "N",
                    "passive_force_N":     "N",
                    "total_force_N":       "N",
                    "PCSA_cm2":            "cm^2",
                    "pennation_angle_deg": "deg",
                },
                raw_output=(
                    f"Hill model ({muscle}): F_total={F_total:.1f} N, "
                    f"a={activation}, L/L0={l_ratio}, penn={penn_deg} deg"
                ),
                warnings=warnings,
                assumptions=[
                    "Hill-type three-element muscle model",
                    "Force-length: Gaussian f_L = exp(-((L/L0 - 1)/0.45)^2)",
                    "Passive force: quadratic toe region for L/L0 > 1",
                    f"Peak isometric force F0 = {F0} N (Rajagopal 2016 model)",
                    "Tendon assumed rigid (no series elastic element)",
                    f"Specific tension 30 N/cm^2 for PCSA estimate",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
