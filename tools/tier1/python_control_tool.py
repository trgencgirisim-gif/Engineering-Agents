"""tools/tier1/python_control_tool.py — Control system analysis via python-control."""
from tools.base import BaseToolWrapper, ToolResult


class PythonControlTool(BaseToolWrapper):
    name    = "python_control"
    tier    = 1
    domains = ["kontrol", "sistem", "robotik", "otomotiv", "savunma"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["stability_margins", "step_response", "pid_design", "bode_analysis"],
            },
            "numerator":   {"type": "array", "items": {"type": "number"},
                            "description": "Transfer function numerator coefficients [b0, b1, ...]"},
            "denominator": {"type": "array", "items": {"type": "number"},
                            "description": "Transfer function denominator coefficients [a0, a1, ...]"},
        },
        "required": ["analysis_type", "numerator", "denominator"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: gain margin, phase margin, "
            "stability assessment, step response overshoot, or settling time.\n\n"
            "DO NOT CALL if:\n"
            "- No transfer function can be derived from the brief\n"
            "- Only a qualitative stability discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: stability_margins / step_response / pid_design\n"
            "- numerator: transfer function numerator coefficients [b0, b1, ...]\n"
            "- denominator: transfer function denominator coefficients [a0, a1, ...]\n\n"
            "Returns verified control analysis. Phase margin below 45 deg must be flagged HIGH risk. "
            "is_stable=False must be flagged CRITICAL. "
            "Guessing stability without computing margins is a quality failure."
        )

    def is_available(self) -> bool:
        try:
            import control  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        try:
            import control
            import numpy as np

            num  = inputs["numerator"]
            den  = inputs["denominator"]
            sys_ = control.tf(num, den)

            # Stability margins
            gm, pm, wg, wp = control.margin(sys_)
            gm_dB = 20 * np.log10(gm) if gm and gm > 0 else -999.0

            # Step response
            T_sim = np.linspace(0, max(10.0 / (wp + 0.01) if wp else 10.0, 0.1), 500)
            t, y  = control.step_response(sys_, T_sim)
            ss    = float(y[-1]) if len(y) else 1.0

            if abs(ss) > 1e-12:
                overshoot = (float(np.max(y)) - ss) / abs(ss) * 100
                settled   = np.where(np.abs(y - ss) <= 0.02 * abs(ss))[0]
                t_settle  = float(t[settled[0]]) if len(settled) else float(t[-1])
            else:
                overshoot, t_settle = 0.0, 0.0

            is_stable = bool(pm > 0 and gm > 1)

            warnings = []
            if not is_stable:
                warnings.append("System is UNSTABLE — PM <= 0 or GM <= 1")
            elif pm < 30:
                warnings.append(f"Phase margin {pm:.1f} deg < 30 deg — poorly damped")
            elif pm < 45:
                warnings.append(f"Phase margin {pm:.1f} deg < 45 deg — recommended minimum is 45 deg")
            if gm_dB < 6:
                warnings.append(f"Gain margin {gm_dB:.1f} dB < 6 dB — sensitive to parameter variation")
            if overshoot > 20:
                warnings.append(f"Step overshoot {overshoot:.1f}% > 20%")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "gain_margin_dB":              round(gm_dB, 3),
                    "phase_margin_deg":            round(float(pm), 3),
                    "gain_crossover_freq_rad_s":   round(float(wp), 4) if wp else 0.0,
                    "phase_crossover_freq_rad_s":  round(float(wg), 4) if wg else 0.0,
                    "is_stable":                   is_stable,
                    "step_overshoot_pct":          round(overshoot, 2),
                    "settling_time_2pct_s":        round(t_settle, 4),
                    "steady_state_value":          round(ss, 6),
                },
                units={
                    "gain_margin_dB":             "dB",
                    "phase_margin_deg":           "deg",
                    "gain_crossover_freq_rad_s":  "rad/s",
                    "phase_crossover_freq_rad_s": "rad/s",
                    "step_overshoot_pct":         "%",
                    "settling_time_2pct_s":       "s",
                },
                raw_output=f"python-control: tf({num}, {den})",
                warnings=warnings,
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
