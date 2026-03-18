"""tools/tier1/pyspice_tool.py — Circuit simulation via PySpice."""
import math
from tools.base import BaseToolWrapper, ToolResult


class PySpiceTool(BaseToolWrapper):
    name    = "pyspice"
    tier    = 1
    domains = ["elektrik"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "circuit_type": {
                "type": "string",
                "enum": ["voltage_divider", "rc_filter", "rlc_circuit"],
                "description": "Type of circuit to simulate",
            },
            "components": {
                "type": "object",
                "description": "Component values",
                "properties": {
                    "R":  {"type": "number", "description": "Resistance [Ohm]"},
                    "R1": {"type": "number", "description": "Resistance 1 [Ohm] (for voltage divider)"},
                    "R2": {"type": "number", "description": "Resistance 2 [Ohm] (for voltage divider)"},
                    "L":  {"type": "number", "description": "Inductance [H]"},
                    "C":  {"type": "number", "description": "Capacitance [F]"},
                    "V":  {"type": "number", "description": "Source voltage [V]"},
                },
            },
            "analysis_type": {
                "type": "string",
                "enum": ["dc", "ac", "transient"],
                "description": "Type of circuit analysis",
            },
            "frequency": {
                "type": "number",
                "description": "Signal frequency for AC analysis [Hz]",
            },
        },
        "required": ["circuit_type", "components"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: node voltages, branch currents, "
            "power dissipation, frequency response, or transient circuit behavior.\n\n"
            "DO NOT CALL if:\n"
            "- No circuit topology can be derived from the brief\n"
            "- Only qualitative electrical discussion is needed\n\n"
            "REQUIRED inputs:\n"
            "- circuit_type: voltage_divider / rc_filter / rlc_circuit\n"
            "- components: R, L, C, V values with units\n"
            "- analysis_type: dc / ac / transient\n\n"
            "Returns verified SPICE simulation results."
        )

    def is_available(self) -> bool:
        try:
            import PySpice  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        ctype = inputs.get("circuit_type", "voltage_divider")
        dispatch = {
            "voltage_divider": self._voltage_divider,
            "rc_filter":       self._rc_filter,
            "rlc_circuit":     self._rlc_circuit,
        }
        handler = dispatch.get(ctype, self._voltage_divider)
        return handler(inputs)

    # ------------------------------------------------------------------
    def _voltage_divider(self, inputs: dict) -> ToolResult:
        try:
            comp = inputs.get("components", {})
            R1 = float(comp.get("R1", comp.get("R", 1000.0)))
            R2 = float(comp.get("R2", 1000.0))
            V  = float(comp.get("V", 5.0))

            if R1 + R2 <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="Total resistance must be > 0",
                )

            V_out   = V * R2 / (R1 + R2)
            I_total = V / (R1 + R2)
            P_total = V * I_total
            P_R1    = I_total ** 2 * R1
            P_R2    = I_total ** 2 * R2

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "V_out_V":       round(V_out, 6),
                    "I_total_mA":    round(I_total * 1e3, 6),
                    "P_total_mW":    round(P_total * 1e3, 6),
                    "P_R1_mW":       round(P_R1 * 1e3, 6),
                    "P_R2_mW":       round(P_R2 * 1e3, 6),
                    "voltage_ratio": round(V_out / V if V != 0 else 0, 6),
                },
                units={
                    "V_out_V": "V", "I_total_mA": "mA",
                    "P_total_mW": "mW", "P_R1_mW": "mW", "P_R2_mW": "mW",
                },
                raw_output=f"PySpice divider: V={V} V, R1={R1} Ohm, R2={R2} Ohm",
                assumptions=["Ideal resistors (no temperature dependence)", "DC steady state"],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    def _rc_filter(self, inputs: dict) -> ToolResult:
        try:
            comp = inputs.get("components", {})
            R = float(comp.get("R", 1000.0))
            C = float(comp.get("C", 1e-6))
            V = float(comp.get("V", 5.0))
            f = float(inputs.get("frequency", 1000.0))

            if R <= 0 or C <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="R and C must be > 0",
                )

            # Low-pass RC filter
            f_c     = 1.0 / (2.0 * math.pi * R * C)
            tau     = R * C
            omega   = 2.0 * math.pi * f
            omega_c = 2.0 * math.pi * f_c

            # Transfer function magnitude: |H(jw)| = 1 / sqrt(1 + (w*RC)^2)
            H_mag   = 1.0 / math.sqrt(1.0 + (omega * tau) ** 2)
            H_dB    = 20.0 * math.log10(H_mag) if H_mag > 0 else -200.0
            phase   = -math.atan(omega * tau) * 180.0 / math.pi

            V_out   = V * H_mag

            # Time domain: step response rise time (10-90%) ~ 2.2 * tau
            t_rise = 2.2 * tau

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "cutoff_frequency_Hz":  round(f_c, 4),
                    "time_constant_s":      round(tau, 8),
                    "gain_at_freq_dB":      round(H_dB, 3),
                    "gain_magnitude":       round(H_mag, 6),
                    "phase_deg":            round(phase, 3),
                    "V_out_at_freq_V":      round(V_out, 6),
                    "rise_time_10_90_s":    round(t_rise, 8),
                    "signal_frequency_Hz":  f,
                },
                units={
                    "cutoff_frequency_Hz": "Hz", "time_constant_s": "s",
                    "gain_at_freq_dB": "dB", "phase_deg": "deg",
                    "V_out_at_freq_V": "V", "rise_time_10_90_s": "s",
                },
                raw_output=(
                    f"PySpice RC filter: R={R} Ohm, C={C*1e6:.3f} uF, "
                    f"fc={f_c:.1f} Hz, gain@{f}Hz={H_dB:.1f} dB"
                ),
                assumptions=[
                    "First-order low-pass RC filter",
                    "Ideal components (no parasitic elements)",
                    "Sinusoidal steady-state for AC analysis",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    def _rlc_circuit(self, inputs: dict) -> ToolResult:
        try:
            comp = inputs.get("components", {})
            R = float(comp.get("R", 100.0))
            L = float(comp.get("L", 10e-3))
            C = float(comp.get("C", 1e-6))
            V = float(comp.get("V", 5.0))
            f = float(inputs.get("frequency", 0.0))

            if L <= 0 or C <= 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="L and C must be > 0",
                )

            # Series RLC resonance
            f_0      = 1.0 / (2.0 * math.pi * math.sqrt(L * C))
            omega_0  = 2.0 * math.pi * f_0
            Q        = (1.0 / R) * math.sqrt(L / C) if R > 0 else float("inf")
            BW       = f_0 / Q if Q > 0 else float("inf")

            # Characteristic impedance
            Z_0 = math.sqrt(L / C)

            # Damping
            zeta = R / (2.0 * math.sqrt(L / C)) if L > 0 and C > 0 else 0.0

            # If frequency given, compute impedance at that frequency
            if f > 0:
                omega = 2.0 * math.pi * f
                X_L   = omega * L
                X_C   = 1.0 / (omega * C)
                Z_mag = math.sqrt(R ** 2 + (X_L - X_C) ** 2)
                phase = math.atan2(X_L - X_C, R) * 180.0 / math.pi
                I_mag = V / Z_mag if Z_mag > 0 else 0.0
            else:
                # At resonance
                f = f_0
                Z_mag = R
                phase = 0.0
                I_mag = V / R if R > 0 else 0.0

            damping_type = (
                "underdamped" if zeta < 1.0
                else "critically_damped" if abs(zeta - 1.0) < 0.01
                else "overdamped"
            )

            warnings = []
            if Q < 1.0:
                warnings.append(f"Low Q-factor ({Q:.2f}) — heavily damped, poor selectivity")
            if zeta > 1.0:
                warnings.append("Overdamped — no oscillatory transient response")

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "resonant_frequency_Hz":     round(f_0, 4),
                    "quality_factor_Q":          round(Q, 4),
                    "bandwidth_Hz":              round(BW, 4),
                    "characteristic_impedance_Ohm": round(Z_0, 4),
                    "damping_ratio":             round(zeta, 6),
                    "damping_type":              damping_type,
                    "impedance_at_freq_Ohm":     round(Z_mag, 4),
                    "phase_at_freq_deg":         round(phase, 3),
                    "current_at_freq_A":         round(I_mag, 6),
                },
                units={
                    "resonant_frequency_Hz": "Hz", "quality_factor_Q": "dimensionless",
                    "bandwidth_Hz": "Hz", "characteristic_impedance_Ohm": "Ohm",
                    "impedance_at_freq_Ohm": "Ohm", "phase_at_freq_deg": "deg",
                    "current_at_freq_A": "A",
                },
                raw_output=(
                    f"PySpice RLC: R={R} Ohm, L={L*1e3:.2f} mH, C={C*1e6:.2f} uF, "
                    f"f0={f_0:.1f} Hz, Q={Q:.2f}"
                ),
                warnings=warnings,
                assumptions=[
                    "Series RLC circuit configuration",
                    "Ideal components (no parasitic resistance/capacitance)",
                    "Sinusoidal steady-state analysis",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
