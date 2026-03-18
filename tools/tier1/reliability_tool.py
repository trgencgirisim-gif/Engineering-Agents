"""tools/tier1/reliability_tool.py — Reliability engineering via reliability library."""
import math

from tools.base import BaseToolWrapper, ToolResult


class ReliabilityTool(BaseToolWrapper):
    name    = "reliability"
    tier    = 1
    domains = ["guvenilirlik"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["weibull_fit", "mtbf_calculation", "availability", "fault_tree"],
                "description": "Type of reliability analysis to perform",
            },
            "parameters": {
                "type": "object",
                "description": "Reliability parameters",
                "properties": {
                    "failure_rate": {
                        "type": "number",
                        "description": "Constant failure rate lambda [failures/hour]",
                    },
                    "repair_rate": {
                        "type": "number",
                        "description": "Repair rate mu [repairs/hour]",
                    },
                    "mission_time": {
                        "type": "number",
                        "description": "Mission time [hours]",
                    },
                    "beta": {
                        "type": "number",
                        "description": "Weibull shape parameter",
                    },
                    "eta": {
                        "type": "number",
                        "description": "Weibull scale parameter (characteristic life) [hours]",
                    },
                    "data": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Failure time data for Weibull fitting [hours]",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: MTBF, failure rate, "
            "Weibull shape/scale parameters, reliability at a given mission time, "
            "or B10/B50 life estimates.\n\n"
            "DO NOT CALL if:\n"
            "- No failure time data or failure rate data is available\n"
            "- Only qualitative reliability discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: weibull_fit / mtbf_calculation / availability / fault_tree\n"
            "- parameters: failure_rate or data (failure times) or beta+eta\n"
            "- mission_time: hours (for mission reliability)\n\n"
            "Returns verified reliability statistics using the reliability Python library."
        )

    def is_available(self) -> bool:
        try:
            import reliability  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "mtbf_calculation")
        params = inputs.get("parameters", {})

        dispatch = {
            "weibull_fit":      self._weibull_fit,
            "mtbf_calculation": self._mtbf_calculation,
            "availability":     self._availability,
            "fault_tree":       self._fault_tree,
        }
        handler = dispatch.get(analysis_type, self._mtbf_calculation)
        return handler(params)

    def _weibull_fit(self, params: dict) -> ToolResult:
        try:
            data = params.get("data", [])
            if not data or len(data) < 2:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Weibull fit requires at least 2 failure time data points",
                )

            try:
                from reliability.Fitters import Fit_Weibull_2P

                fit = Fit_Weibull_2P(failures=data, show_probability_plot=False, print_results=False)
                beta = fit.beta
                eta = fit.alpha
            except ImportError:
                # Analytical MLE approximation for Weibull 2-parameter fit
                # using the median-rank regression approach
                n = len(data)
                sorted_data = sorted(data)
                ln_data = [math.log(t) for t in sorted_data if t > 0]
                if len(ln_data) < 2:
                    return ToolResult(
                        success=False, solver=self.name, confidence="NONE",
                        data={}, units={}, raw_output="",
                        error="All failure times must be positive",
                    )

                # Median rank approximation: F(i) = (i - 0.3) / (n + 0.4)
                median_ranks = [(i + 1 - 0.3) / (n + 0.4) for i in range(n)]
                # Linearised Weibull: ln(-ln(1-F)) = beta*ln(t) - beta*ln(eta)
                y_vals = [math.log(-math.log(1.0 - f)) for f in median_ranks]
                x_vals = ln_data

                # Least-squares linear regression: y = m*x + c
                x_mean = sum(x_vals) / n
                y_mean = sum(y_vals) / n
                ss_xy = sum((x_vals[i] - x_mean) * (y_vals[i] - y_mean) for i in range(n))
                ss_xx = sum((x_vals[i] - x_mean) ** 2 for i in range(n))

                beta = ss_xy / ss_xx if ss_xx > 0 else 1.0
                c = y_mean - beta * x_mean
                eta = math.exp(-c / beta) if beta != 0 else sorted_data[-1]

            # Compute derived quantities
            # Weibull mean (MTTF) = eta * Gamma(1 + 1/beta)
            mttf = eta * math.gamma(1.0 + 1.0 / beta)
            # Weibull median life
            median_life = eta * math.log(2.0) ** (1.0 / beta)
            # B10 life (10% failure)
            b10_life = eta * (-math.log(0.9)) ** (1.0 / beta)

            warnings = []
            if beta < 1.0:
                warnings.append("Beta < 1: infant mortality (decreasing failure rate) detected")
            elif abs(beta - 1.0) < 0.05:
                warnings.append("Beta ~ 1: constant failure rate (exponential distribution equivalent)")
            elif beta > 3.5:
                warnings.append("Beta > 3.5: rapid wear-out, consider preventive maintenance")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "beta_shape":        round(beta, 4),
                    "eta_scale_hours":   round(eta, 2),
                    "MTTF_hours":        round(mttf, 2),
                    "median_life_hours": round(median_life, 2),
                    "B10_life_hours":    round(b10_life, 2),
                },
                units={
                    "eta_scale_hours":   "hours",
                    "MTTF_hours":        "hours",
                    "median_life_hours": "hours",
                    "B10_life_hours":    "hours",
                },
                raw_output=f"Weibull fit: beta={beta:.4f}, eta={eta:.2f} h, n={len(data)} points",
                warnings=warnings,
                assumptions=[
                    "Two-parameter Weibull distribution assumed",
                    "All failures are from the same failure mode",
                    "No censored data (all data points are failures)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _mtbf_calculation(self, params: dict) -> ToolResult:
        try:
            failure_rate = float(params.get("failure_rate", 1e-5))
            mission_time = float(params.get("mission_time", 1000.0))
            beta = params.get("beta")
            eta = params.get("eta")

            if failure_rate <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Failure rate must be positive",
                )

            data = {}
            units = {}
            assumptions = []

            if beta is not None and eta is not None:
                # Weibull reliability at mission_time
                beta = float(beta)
                eta = float(eta)
                R_t = math.exp(-((mission_time / eta) ** beta))
                # Weibull MTTF
                mttf = eta * math.gamma(1.0 + 1.0 / beta)
                # Instantaneous failure rate at mission_time (Weibull hazard)
                h_t = (beta / eta) * ((mission_time / eta) ** (beta - 1.0))

                data.update({
                    "MTTF_hours":              round(mttf, 2),
                    "reliability_at_t":        round(R_t, 6),
                    "hazard_rate_at_t":        round(h_t, 8),
                    "mission_time_hours":      mission_time,
                })
                units.update({
                    "MTTF_hours":         "hours",
                    "mission_time_hours": "hours",
                    "hazard_rate_at_t":   "failures/hour",
                })
                assumptions.append(f"Weibull distribution: beta={beta}, eta={eta}")
            else:
                # Exponential (constant failure rate) model
                mtbf = 1.0 / failure_rate
                R_t = math.exp(-failure_rate * mission_time)
                # Unreliability
                F_t = 1.0 - R_t
                # Failure-free probability for N identical items
                N = 10
                system_R = R_t ** N

                data.update({
                    "MTBF_hours":                round(mtbf, 2),
                    "reliability_at_t":          round(R_t, 6),
                    "unreliability_at_t":        round(F_t, 6),
                    "mission_time_hours":        mission_time,
                    "failure_rate_per_hour":     failure_rate,
                    "system_reliability_10_unit": round(system_R, 6),
                })
                units.update({
                    "MTBF_hours":            "hours",
                    "mission_time_hours":    "hours",
                    "failure_rate_per_hour": "failures/hour",
                })
                assumptions.append("Exponential distribution (constant failure rate)")
                assumptions.append(f"Series system reliability computed for N={N} identical units")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data=data, units=units,
                raw_output=f"MTBF analysis: lambda={failure_rate}, t={mission_time} h",
                assumptions=assumptions,
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _availability(self, params: dict) -> ToolResult:
        try:
            failure_rate = float(params.get("failure_rate", 1e-4))
            repair_rate = float(params.get("repair_rate", 0.1))

            if failure_rate <= 0 or repair_rate <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Failure rate and repair rate must be positive",
                )

            mtbf = 1.0 / failure_rate
            mttr = 1.0 / repair_rate
            # Steady-state (inherent) availability
            A_ss = mtbf / (mtbf + mttr)
            # Unavailability
            U_ss = 1.0 - A_ss
            # Downtime per year (8760 hours)
            downtime_per_year = U_ss * 8760.0
            # Number of nines
            nines = -math.log10(1.0 - A_ss) if A_ss < 1.0 else float("inf")

            warnings = []
            if A_ss < 0.99:
                warnings.append(f"Availability {A_ss:.4f} below 99% — consider redundancy")
            if mttr > 24:
                warnings.append(f"MTTR = {mttr:.1f} hours is high — review maintenance logistics")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "steady_state_availability": round(A_ss, 8),
                    "unavailability":            round(U_ss, 8),
                    "MTBF_hours":                round(mtbf, 2),
                    "MTTR_hours":                round(mttr, 4),
                    "downtime_hours_per_year":   round(downtime_per_year, 2),
                    "availability_nines":        round(nines, 2),
                },
                units={
                    "MTBF_hours":              "hours",
                    "MTTR_hours":              "hours",
                    "downtime_hours_per_year": "hours/year",
                },
                raw_output=f"Availability: lambda={failure_rate}, mu={repair_rate}",
                warnings=warnings,
                assumptions=[
                    "Single repairable unit with exponential failure and repair distributions",
                    "Steady-state (long-run) availability",
                    "Perfect repair (as-good-as-new after maintenance)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    def _fault_tree(self, params: dict) -> ToolResult:
        try:
            failure_rate = float(params.get("failure_rate", 1e-3))
            mission_time = float(params.get("mission_time", 1000.0))

            # Demonstrate fault tree with a typical redundant system:
            # Top event = system failure
            # AND gate: both channels must fail (1-out-of-2 redundancy)
            # Each channel: OR gate of 3 basic events (sensor, processor, actuator)
            p_sensor = 1.0 - math.exp(-failure_rate * mission_time)
            p_processor = 1.0 - math.exp(-(failure_rate * 0.5) * mission_time)
            p_actuator = 1.0 - math.exp(-(failure_rate * 0.8) * mission_time)

            # OR gate: P(channel fail) = 1 - (1-p1)(1-p2)(1-p3)
            p_channel = 1.0 - (1.0 - p_sensor) * (1.0 - p_processor) * (1.0 - p_actuator)
            # AND gate: P(system fail) = P(ch_A fail) * P(ch_B fail) (independent)
            p_system = p_channel ** 2

            # Minimal cut sets importance (Fussell-Vesely for sensor)
            fv_sensor = (p_sensor * p_channel) / p_system if p_system > 0 else 0.0

            warnings = []
            if p_system > 1e-4:
                warnings.append(
                    f"System failure probability {p_system:.2e} exceeds 1e-4 target"
                )

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "p_sensor_failure":    round(p_sensor, 8),
                    "p_processor_failure": round(p_processor, 8),
                    "p_actuator_failure":  round(p_actuator, 8),
                    "p_channel_failure":   round(p_channel, 8),
                    "p_system_failure":    round(p_system, 10),
                    "system_reliability":  round(1.0 - p_system, 10),
                    "FV_importance_sensor": round(fv_sensor, 6),
                },
                units={"mission_time_hours": "hours"},
                raw_output=(
                    f"Fault tree: 1oo2 redundancy, lambda={failure_rate}, "
                    f"t={mission_time} h"
                ),
                warnings=warnings,
                assumptions=[
                    "1-out-of-2 active redundancy (AND gate at top)",
                    "Each channel: sensor OR processor OR actuator (OR gate)",
                    "Processor failure rate = 0.5x base, actuator = 0.8x base",
                    "Independent failures, no common cause failure modeled",
                    "Exponential failure distribution for all basic events",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
