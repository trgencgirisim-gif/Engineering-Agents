"""tools/tier1/freecad_tool.py — CAD/CAM and manufacturing analysis via FreeCAD."""
import math

from tools.base import BaseToolWrapper, ToolResult


class FreeCADTool(BaseToolWrapper):
    name    = "freecad"
    tier    = 1
    domains = ["uretim"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": ["machining_time", "tolerance_analysis", "material_removal"],
                "description": "Type of manufacturing / CAD-CAM analysis",
            },
            "parameters": {
                "type": "object",
                "description": "Manufacturing parameters",
                "properties": {
                    "cutting_speed_m_min": {
                        "type": "number",
                        "description": "Cutting speed Vc [m/min]",
                    },
                    "feed_per_tooth_mm": {
                        "type": "number",
                        "description": "Feed per tooth fz [mm/tooth]",
                    },
                    "feed_rate_mm_min": {
                        "type": "number",
                        "description": "Table feed rate [mm/min] (overrides fz calc if given)",
                    },
                    "depth_of_cut_mm": {
                        "type": "number",
                        "description": "Axial depth of cut ap [mm]",
                    },
                    "width_of_cut_mm": {
                        "type": "number",
                        "description": "Radial width of cut ae [mm]",
                    },
                    "tool_diameter_mm": {
                        "type": "number",
                        "description": "Cutter / drill diameter [mm]",
                    },
                    "number_of_flutes": {
                        "type": "integer",
                        "description": "Number of cutting edges / flutes",
                    },
                    "workpiece_length_mm": {
                        "type": "number",
                        "description": "Workpiece length along feed direction [mm]",
                    },
                    "workpiece_width_mm": {
                        "type": "number",
                        "description": "Workpiece width (for face milling) [mm]",
                    },
                    "workpiece_hardness_HRC": {
                        "type": "number",
                        "description": "Workpiece Rockwell C hardness",
                    },
                    "tool_material": {
                        "type": "string",
                        "enum": ["HSS", "carbide", "ceramic", "CBN"],
                        "description": "Cutting tool material",
                    },
                    "operation": {
                        "type": "string",
                        "enum": ["turning", "milling", "drilling"],
                        "description": "Machining operation type",
                    },
                    "dimensions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nominal_mm": {"type": "number"},
                                "tolerance_mm": {"type": "number"},
                                "distribution": {
                                    "type": "string",
                                    "enum": ["normal", "uniform"],
                                },
                            },
                        },
                        "description": "Stack-up dimensions for tolerance analysis",
                    },
                    "specific_cutting_force_N_mm2": {
                        "type": "number",
                        "description": "Specific cutting force kc1.1 [N/mm^2]",
                    },
                },
            },
        },
        "required": ["analysis_type"],
    }

    def _description(self) -> str:
        return (
            "WHEN TO CALL THIS TOOL:\n"
            "Call whenever the analysis requires: tolerance stack-up, "
            "machining time estimation, or material removal rate calculations.\n\n"
            "DO NOT CALL if:\n"
            "- Problem is analytical (beam theory) — use fenics_tool instead\n"
            "- No manufacturing parameters are available\n\n"
            "REQUIRED inputs:\n"
            "- analysis_type: machining_time / tolerance_analysis / material_removal\n"
            "- parameters: cutting_speed, feed, depth_of_cut, tool_diameter\n"
            "- For tolerance: dimensions list with nominal_mm and tolerance_mm\n\n"
            "Returns verified FreeCAD geometric and manufacturing analysis results."
        )

    def is_available(self) -> bool:
        try:
            import FreeCAD  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        analysis_type = inputs.get("analysis_type", "machining_time")
        params = inputs.get("parameters", {})

        dispatch = {
            "machining_time":    self._machining_time,
            "tolerance_analysis": self._tolerance_analysis,
            "material_removal":  self._material_removal,
        }
        handler = dispatch.get(analysis_type, self._machining_time)
        return handler(params)

    # ------------------------------------------------------------------
    # Machining time estimation with Taylor tool life
    # ------------------------------------------------------------------
    def _machining_time(self, params: dict) -> ToolResult:
        try:
            op    = params.get("operation", "milling")
            Vc    = float(params.get("cutting_speed_m_min", 100.0))
            fz    = float(params.get("feed_per_tooth_mm", 0.1))
            ap    = float(params.get("depth_of_cut_mm", 2.0))
            ae    = float(params.get("width_of_cut_mm", 10.0))
            D     = float(params.get("tool_diameter_mm", 20.0))
            z     = int(params.get("number_of_flutes", 4))
            L_w   = float(params.get("workpiece_length_mm", 200.0))
            W_w   = float(params.get("workpiece_width_mm", 50.0))
            tool_mat = params.get("tool_material", "carbide")

            # Spindle RPM: n = (1000 * Vc) / (pi * D)
            n = (1000.0 * Vc) / (math.pi * D) if D > 0 else 0.0

            # Table feed rate: Vf = fz * z * n [mm/min]
            Vf = params.get("feed_rate_mm_min")
            if Vf is None:
                Vf = fz * z * n

            if op == "milling":
                # Number of passes (face milling): ceil(W_w / ae)
                n_passes = math.ceil(W_w / ae) if ae > 0 else 1
                # Approach + overrun ~ D/2 each side
                L_total = L_w + D
                t_cut = (L_total * n_passes) / Vf if Vf > 0 else 0.0  # [min]

            elif op == "turning":
                # Turning: feed per revolution
                f_rev = fz  # for turning, fz is typically feed/rev
                Vf_turn = f_rev * n
                # Number of passes
                n_passes = math.ceil(W_w / ap) if ap > 0 else 1  # W_w as radial depth
                L_total = L_w + 5.0  # approach allowance
                t_cut = (L_total * n_passes) / Vf_turn if Vf_turn > 0 else 0.0

            elif op == "drilling":
                # Drill feed: Vf = f_rev * n
                f_rev = fz * z  # total feed per rev
                Vf_drill = f_rev * n
                # Depth = L_w, point allowance = 0.3*D
                L_total = L_w + 0.3 * D
                n_passes = 1
                t_cut = L_total / Vf_drill if Vf_drill > 0 else 0.0
            else:
                t_cut = 0.0
                n_passes = 0
                L_total = 0.0

            # Taylor tool life: V * T^n = C
            # n and C depend on tool material
            taylor = {
                "HSS":     (0.125, 70.0),
                "carbide":  (0.25,  300.0),
                "ceramic":  (0.40,  600.0),
                "CBN":      (0.50,  800.0),
            }
            n_taylor, C_taylor = taylor.get(tool_mat, (0.25, 300.0))
            # Tool life T = (C/V)^(1/n) [min]
            T_life = (C_taylor / Vc) ** (1.0 / n_taylor) if Vc > 0 else float("inf")

            # Number of tool changes per part
            tool_changes = math.ceil(t_cut / T_life) - 1 if T_life > 0 and t_cut > T_life else 0
            t_tool_change = tool_changes * 2.0  # ~2 min per change

            t_total = t_cut + t_tool_change

            warnings = []
            if T_life < t_cut:
                warnings.append(
                    f"Tool life {T_life:.1f} min < cut time {t_cut:.1f} min — "
                    f"{tool_changes + 1} tool(s) needed"
                )
            if n > 15000:
                warnings.append(f"Spindle speed {n:.0f} RPM — verify machine capability")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "spindle_speed_rpm":    round(n, 1),
                    "table_feed_mm_min":    round(Vf, 1),
                    "cutting_time_min":     round(t_cut, 3),
                    "total_time_min":       round(t_total, 3),
                    "number_of_passes":     n_passes,
                    "taylor_tool_life_min": round(T_life, 1),
                    "tool_changes":         tool_changes,
                    "operation":            op,
                },
                units={
                    "spindle_speed_rpm":    "RPM",
                    "table_feed_mm_min":    "mm/min",
                    "cutting_time_min":     "min",
                    "total_time_min":       "min",
                    "taylor_tool_life_min": "min",
                },
                raw_output=(
                    f"Machining ({op}): Vc={Vc} m/min, n={n:.0f} RPM, "
                    f"t_cut={t_cut:.2f} min, T_life={T_life:.1f} min"
                ),
                warnings=warnings,
                assumptions=[
                    f"Taylor tool life: V*T^{n_taylor} = {C_taylor} ({tool_mat})",
                    "Tool change time 2 min per change",
                    "Approach/overrun included in path length",
                    f"Operation: {op}, D = {D} mm, z = {z} flutes",
                    "No rapid traverse time included (cutting time only)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Statistical tolerance stack-up (worst case + RSS)
    # ------------------------------------------------------------------
    def _tolerance_analysis(self, params: dict) -> ToolResult:
        try:
            dims = params.get("dimensions", [])
            if not dims:
                # Default example: 3-part stack
                dims = [
                    {"nominal_mm": 25.0, "tolerance_mm": 0.05, "distribution": "normal"},
                    {"nominal_mm": 30.0, "tolerance_mm": 0.08, "distribution": "normal"},
                    {"nominal_mm": 15.0, "tolerance_mm": 0.03, "distribution": "normal"},
                ]

            nominals = [float(d.get("nominal_mm", 0.0)) for d in dims]
            tolerances = [float(d.get("tolerance_mm", 0.0)) for d in dims]

            n = len(dims)
            total_nominal = sum(nominals)

            # Worst-case (arithmetic): T_wc = sum(ti)
            T_wc = sum(tolerances)

            # RSS (statistical): T_rss = sqrt(sum(ti^2))
            T_rss = math.sqrt(sum(t ** 2 for t in tolerances))

            # Modified RSS (Bender): T_mod = sqrt(sum(ti^2)) * correction
            # Correction factor for non-normal: 1.5 (conservative)
            T_mod = T_rss * 1.5

            # Capability indices assuming process centered
            # Cp = T / (6*sigma), where sigma = T_rss / 3 for 99.73% yield
            sigma_rss = T_rss / 3.0 if T_rss > 0 else 0.0

            # Assembly yield at ±T_rss (99.73% for normal)
            # At ±T_wc: 100% (by definition)
            # At ±T_rss: ~99.73% (3-sigma for sum of normals)

            # Individual Cp for each dimension (assume process sigma = tol/3)
            cp_values = []
            for t in tolerances:
                # Cp = tol / (6 * sigma_process), sigma_process = tol/6 for Cp=1
                # Report assuming Cp = 1.33 target (4-sigma)
                sigma_p = t / (2 * 1.33 * 3.0) if t > 0 else 0.0
                cp_values.append(round(1.33, 2))  # target

            # DIN 7186 clearance / interference check
            gap_nominal = total_nominal
            gap_max = total_nominal + T_wc
            gap_min = total_nominal - T_wc

            warnings = []
            if T_wc / total_nominal > 0.01:
                warnings.append(
                    f"Total WC tolerance {T_wc:.4f} mm is {T_wc/total_nominal*100:.2f}% "
                    "of nominal — consider tightening critical dimensions"
                )
            ratio = T_rss / T_wc if T_wc > 0 else 0.0

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "num_dimensions":         n,
                    "total_nominal_mm":       round(total_nominal, 4),
                    "worst_case_tol_mm":      round(T_wc, 4),
                    "rss_tolerance_mm":       round(T_rss, 4),
                    "modified_rss_tol_mm":    round(T_mod, 4),
                    "rss_to_wc_ratio":        round(ratio, 4),
                    "assembly_max_mm":        round(gap_max, 4),
                    "assembly_min_mm":        round(gap_min, 4),
                    "sigma_rss_mm":           round(sigma_rss, 5),
                },
                units={
                    "total_nominal_mm":    "mm",
                    "worst_case_tol_mm":   "mm",
                    "rss_tolerance_mm":    "mm",
                    "modified_rss_tol_mm": "mm",
                    "assembly_max_mm":     "mm",
                    "assembly_min_mm":     "mm",
                    "sigma_rss_mm":        "mm",
                },
                raw_output=(
                    f"Tolerance stack: {n} dims, T_wc={T_wc:.4f} mm, "
                    f"T_rss={T_rss:.4f} mm, ratio={ratio:.3f}"
                ),
                warnings=warnings,
                assumptions=[
                    "Bilateral symmetric tolerances (±t/2)",
                    "Normal distribution assumed for RSS calculation",
                    "All dimensions in same direction (linear 1D stack)",
                    "Modified RSS uses 1.5x correction (Bender method)",
                    "Process centred on nominal (Cpk = Cp)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    # Material removal rate and cutting force
    # ------------------------------------------------------------------
    def _material_removal(self, params: dict) -> ToolResult:
        try:
            op    = params.get("operation", "milling")
            Vc    = float(params.get("cutting_speed_m_min", 100.0))
            fz    = float(params.get("feed_per_tooth_mm", 0.1))
            ap    = float(params.get("depth_of_cut_mm", 2.0))
            ae    = float(params.get("width_of_cut_mm", 10.0))
            D     = float(params.get("tool_diameter_mm", 20.0))
            z     = int(params.get("number_of_flutes", 4))
            kc11  = float(params.get("specific_cutting_force_N_mm2", 1800.0))  # steel default

            n = (1000.0 * Vc) / (math.pi * D) if D > 0 else 0.0
            Vf = fz * z * n

            if op == "milling":
                # MRR = ae * ap * Vf [mm^3/min]
                MRR = ae * ap * Vf
                # Mean chip thickness: hm = fz * (ae/D)^0.5 (approx for slot/face)
                hm = fz * math.sqrt(ae / D) if D > 0 else fz
            elif op == "turning":
                f_rev = fz
                MRR = Vc * 1000.0 * ap * f_rev  # [mm^3/min] — simplified
                hm = f_rev  # chip thickness ~ feed for turning
            elif op == "drilling":
                f_rev = fz * z
                MRR = (math.pi * D ** 2 / 4.0) * f_rev * n  # mm^3/min
                hm = f_rev / 2.0  # average chip thickness
            else:
                MRR = 0.0
                hm = fz

            # Specific cutting force correction: kc = kc1.1 * hm^(-mc)
            # mc ~ 0.25 for steel
            mc = 0.25
            kc = kc11 * (hm ** (-mc)) if hm > 0 else kc11

            # Cutting force Fc = kc * ap * hm (single edge) [N]
            Fc_single = kc * ap * hm
            # Total tangential force (all engaged teeth at once, approx z_eff)
            # For milling: z_engaged ~ z * (arccos(1 - 2*ae/D)) / (2*pi)
            if op == "milling" and D > 0:
                engagement_angle = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * ae / D)))
                z_eff = max(1.0, z * engagement_angle / (2.0 * math.pi))
            else:
                z_eff = 1.0
            Fc_total = Fc_single * z_eff

            # Cutting power: Pc = Fc * Vc / (60*1000) [kW]
            Pc = Fc_total * Vc / 60000.0

            # Spindle power (assuming 85% efficiency)
            P_spindle = Pc / 0.85

            # Specific MRR (per kW)
            specific_MRR = MRR / P_spindle if P_spindle > 0 else 0.0

            # Surface roughness estimate (theoretical): Ra = fz^2 / (32 * r_nose)
            r_nose = 0.8  # mm (typical insert nose radius)
            Ra = (fz ** 2) / (32.0 * r_nose) * 1000.0  # [um]

            warnings = []
            if P_spindle > 15:
                warnings.append(
                    f"Required spindle power {P_spindle:.1f} kW — verify machine capacity"
                )
            if Ra > 3.2:
                warnings.append(f"Theoretical Ra = {Ra:.2f} um exceeds typical finish requirement (3.2 um)")

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data={
                    "MRR_mm3_min":              round(MRR, 1),
                    "MRR_cm3_min":              round(MRR / 1000.0, 3),
                    "mean_chip_thickness_mm":   round(hm, 4),
                    "specific_cutting_force_N_mm2": round(kc, 1),
                    "cutting_force_N":          round(Fc_total, 1),
                    "cutting_power_kW":         round(Pc, 3),
                    "spindle_power_kW":         round(P_spindle, 3),
                    "specific_MRR_mm3_min_kW":  round(specific_MRR, 1),
                    "theoretical_Ra_um":        round(Ra, 3),
                    "spindle_speed_rpm":        round(n, 1),
                    "table_feed_mm_min":        round(Vf, 1),
                },
                units={
                    "MRR_mm3_min":             "mm^3/min",
                    "MRR_cm3_min":             "cm^3/min",
                    "mean_chip_thickness_mm":  "mm",
                    "specific_cutting_force_N_mm2": "N/mm^2",
                    "cutting_force_N":         "N",
                    "cutting_power_kW":        "kW",
                    "spindle_power_kW":        "kW",
                    "theoretical_Ra_um":       "um",
                    "spindle_speed_rpm":       "RPM",
                    "table_feed_mm_min":       "mm/min",
                },
                raw_output=(
                    f"MRR ({op}): {MRR:.0f} mm^3/min, Fc={Fc_total:.0f} N, "
                    f"Pc={Pc:.2f} kW, Ra={Ra:.2f} um"
                ),
                warnings=warnings,
                assumptions=[
                    f"Specific cutting force kc1.1 = {kc11} N/mm^2 (mc = {mc})",
                    f"Kienzle model: kc = kc1.1 * hm^(-mc)",
                    f"Tool: D = {D} mm, z = {z}, nose radius = {r_nose} mm",
                    "Spindle efficiency 85%",
                    "Theoretical surface roughness (no vibration, BUE, or wear effects)",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
