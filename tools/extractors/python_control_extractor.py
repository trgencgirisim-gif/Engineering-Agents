"""tools/extractors/python_control_extractor.py — Extract control system inputs from text."""
import re
from tools.extractors.base_extractor import BaseInputExtractor


class PythonControlExtractor(BaseInputExtractor):
    solver_name = "python_control"

    def extract(self, text: str, brief: str = "") -> dict | None:
        combined = (brief + " " + text)

        # Detect analysis type
        analysis_type = "stability_margins"
        lower = combined.lower()
        if any(kw in lower for kw in ["step response", "transient", "overshoot", "settling"]):
            analysis_type = "step_response"
        elif any(kw in lower for kw in ["pid", "controller design", "tuning"]):
            analysis_type = "pid_design"
        elif any(kw in lower for kw in ["bode", "frequency response", "nyquist"]):
            analysis_type = "bode_analysis"

        # Extract transfer function coefficients
        # Pattern: G(s) = num / den or tf(num, den)
        num = None
        den = None

        # Try to find explicit coefficient arrays
        num_match = re.search(
            r'num(?:erator)?\s*[=:]\s*\[([\d.,\s]+)\]', combined, re.IGNORECASE
        )
        den_match = re.search(
            r'den(?:ominator)?\s*[=:]\s*\[([\d.,\s]+)\]', combined, re.IGNORECASE
        )

        if num_match:
            num = [float(x.strip()) for x in num_match.group(1).split(",") if x.strip()]
        if den_match:
            den = [float(x.strip()) for x in den_match.group(1).split(",") if x.strip()]

        # Try standard forms: G(s) = K / (tau*s + 1) or K*wn^2 / (s^2 + 2*zeta*wn*s + wn^2)
        if num is None or den is None:
            # Look for gain
            K = self._find_number(combined, [
                r'gain\s*[=:]\s*([\d.]+)',
                r'K\s*[=:]\s*([\d.]+)',
            ], default=1.0)

            # Look for time constant
            tau = self._find_number(combined, [
                r'time\s+constant\s*[=:]\s*([\d.]+)',
                r'tau\s*[=:]\s*([\d.]+)',
            ])

            # Look for natural frequency and damping
            wn = self._find_number(combined, [
                r'natural\s+freq[^=\n]*[=:]\s*([\d.]+)',
                r'wn\s*[=:]\s*([\d.]+)',
                r'omega_n\s*[=:]\s*([\d.]+)',
            ])

            zeta = self._find_number(combined, [
                r'damping\s+ratio\s*[=:]\s*([\d.]+)',
                r'zeta\s*[=:]\s*([\d.]+)',
            ])

            if wn and zeta:
                # Second order: K*wn^2 / (s^2 + 2*zeta*wn*s + wn^2)
                num = [float(K) * wn**2]
                den = [1.0, 2.0 * float(zeta) * float(wn), float(wn)**2]
            elif tau:
                # First order: K / (tau*s + 1)
                num = [float(K)]
                den = [float(tau), 1.0]
            else:
                # Default: simple second order system
                num = [1.0]
                den = [1.0, 3.0, 2.0]

        return {
            "analysis_type": analysis_type,
            "numerator":     num,
            "denominator":   den,
        }
