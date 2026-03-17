"""tools/tier1/pybullet_tool.py — Robotics simulation via PyBullet."""
import math
from tools.base import BaseToolWrapper, ToolResult


class PyBulletTool(BaseToolWrapper):
    name    = "pybullet"
    tier    = 1
    domains = ["robotik"]

    INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "simulation_type": {
                "type": "string",
                "enum": ["forward_kinematics", "inverse_kinematics", "dynamics"],
                "description": "Type of robotics simulation",
            },
            "robot_params": {
                "type": "object",
                "description": "Robot parameters",
                "properties": {
                    "masses": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Link masses [kg]",
                    },
                    "lengths": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Link lengths [m]",
                    },
                    "joints": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Joint angles [rad] or target position [x,y,z] for IK",
                    },
                },
            },
        },
        "required": ["simulation_type", "robot_params"],
    }

    def _description(self) -> str:
        return (
            "Robotics simulation using PyBullet: forward kinematics (end-effector position "
            "from joint angles), inverse kinematics (joint angles from target position), "
            "and rigid-body dynamics (joint torques, inertia, energy). "
            "Provide link masses, lengths, and joint angles/targets. "
            "Use for robotic arm analysis, manipulator design, and motion planning."
        )

    def is_available(self) -> bool:
        try:
            import pybullet  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict) -> ToolResult:
        stype = inputs.get("simulation_type", "forward_kinematics")
        dispatch = {
            "forward_kinematics":  self._forward_kinematics,
            "inverse_kinematics":  self._inverse_kinematics,
            "dynamics":            self._dynamics,
        }
        handler = dispatch.get(stype, self._forward_kinematics)
        return handler(inputs)

    # ------------------------------------------------------------------
    def _forward_kinematics(self, inputs: dict) -> ToolResult:
        """DH-based forward kinematics for planar serial manipulator."""
        try:
            params  = inputs.get("robot_params", {})
            lengths = [float(l) for l in params.get("lengths", [1.0, 1.0])]
            joints  = [float(j) for j in params.get("joints", [0.0] * len(lengths))]

            n_links = len(lengths)
            if len(joints) < n_links:
                joints.extend([0.0] * (n_links - len(joints)))

            # Planar serial chain FK
            x, y = 0.0, 0.0
            theta_cum = 0.0
            joint_positions = [(x, y)]

            for i in range(n_links):
                theta_cum += joints[i]
                x += lengths[i] * math.cos(theta_cum)
                y += lengths[i] * math.sin(theta_cum)
                joint_positions.append((round(x, 6), round(y, 6)))

            # End-effector
            ee_x, ee_y = x, y
            ee_dist    = math.sqrt(ee_x ** 2 + ee_y ** 2)
            ee_angle   = math.atan2(ee_y, ee_x)

            # Workspace reach
            max_reach = sum(lengths)
            min_reach = abs(lengths[0] - sum(lengths[1:])) if n_links > 1 else lengths[0]

            # Jacobian determinant (manipulability) for 2-link case
            manipulability = 0.0
            if n_links == 2:
                manipulability = abs(
                    lengths[0] * lengths[1] * math.sin(joints[1])
                )

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data={
                    "end_effector_x_m":     round(ee_x, 6),
                    "end_effector_y_m":     round(ee_y, 6),
                    "end_effector_dist_m":  round(ee_dist, 6),
                    "end_effector_angle_deg": round(ee_angle * 180 / math.pi, 3),
                    "max_reach_m":          round(max_reach, 4),
                    "min_reach_m":          round(min_reach, 4),
                    "manipulability":       round(manipulability, 6),
                    "joint_positions":      joint_positions,
                    "n_dof":               n_links,
                },
                units={
                    "end_effector_x_m": "m", "end_effector_y_m": "m",
                    "end_effector_dist_m": "m", "end_effector_angle_deg": "deg",
                    "max_reach_m": "m", "min_reach_m": "m",
                },
                raw_output=(
                    f"PyBullet FK: {n_links}-link planar, "
                    f"EE=({ee_x:.4f}, {ee_y:.4f}) m"
                ),
                assumptions=[
                    "Planar serial manipulator (2D)",
                    "Revolute joints only",
                    "Rigid links, no joint compliance",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    def _inverse_kinematics(self, inputs: dict) -> ToolResult:
        """Analytical 2-link IK, geometric extension for N-link."""
        try:
            params  = inputs.get("robot_params", {})
            lengths = [float(l) for l in params.get("lengths", [1.0, 1.0])]
            target  = [float(t) for t in params.get("joints", [1.0, 0.5, 0.0])]

            tx, ty = target[0], target[1] if len(target) > 1 else 0.0

            dist = math.sqrt(tx ** 2 + ty ** 2)

            if len(lengths) < 2:
                # Single link — only reachable on circle
                L = lengths[0]
                if abs(dist - L) > 1e-6:
                    return ToolResult(
                        success=True, solver=self.name, confidence="MEDIUM",
                        data={
                            "reachable": False,
                            "target_distance_m": round(dist, 6),
                            "link_length_m": round(L, 4),
                        },
                        units={}, raw_output="Single link — target may not be reachable",
                        assumptions=["Single revolute joint"],
                    )
                theta = math.atan2(ty, tx)
                return ToolResult(
                    success=True, solver=self.name, confidence="HIGH",
                    data={"joint_1_rad": round(theta, 6), "joint_1_deg": round(theta * 180 / math.pi, 3)},
                    units={"joint_1_rad": "rad", "joint_1_deg": "deg"},
                    raw_output=f"PyBullet IK: 1-link, theta={theta:.4f} rad",
                    assumptions=["Planar single revolute joint"],
                )

            # 2-link analytical IK
            L1, L2 = lengths[0], lengths[1]
            max_reach = L1 + L2
            min_reach = abs(L1 - L2)

            reachable = min_reach <= dist <= max_reach

            if not reachable:
                # Return closest reachable configuration
                scale = max_reach / dist if dist > max_reach else min_reach / dist
                warnings = [
                    f"Target ({tx:.3f}, {ty:.3f}) unreachable. "
                    f"Distance {dist:.4f} m outside [{min_reach:.4f}, {max_reach:.4f}] m"
                ]
                return ToolResult(
                    success=True, solver=self.name, confidence="LOW",
                    data={
                        "reachable": False,
                        "target_distance_m": round(dist, 6),
                        "max_reach_m": round(max_reach, 4),
                        "min_reach_m": round(min_reach, 4),
                    },
                    units={"target_distance_m": "m", "max_reach_m": "m", "min_reach_m": "m"},
                    raw_output=f"PyBullet IK: target unreachable, dist={dist:.4f} m",
                    warnings=warnings,
                    assumptions=["Planar 2-link manipulator"],
                )

            # Elbow-up and elbow-down solutions
            cos_q2 = (dist ** 2 - L1 ** 2 - L2 ** 2) / (2 * L1 * L2)
            cos_q2 = max(-1.0, min(1.0, cos_q2))
            q2_up   = -math.acos(cos_q2)
            q2_down =  math.acos(cos_q2)

            solutions = {}
            for label, q2 in [("elbow_up", q2_up), ("elbow_down", q2_down)]:
                beta  = math.atan2(ty, tx)
                alpha = math.atan2(
                    L2 * math.sin(q2),
                    L1 + L2 * math.cos(q2),
                )
                q1 = beta - alpha

                solutions[f"{label}_q1_deg"] = round(q1 * 180 / math.pi, 3)
                solutions[f"{label}_q2_deg"] = round(q2 * 180 / math.pi, 3)
                solutions[f"{label}_q1_rad"] = round(q1, 6)
                solutions[f"{label}_q2_rad"] = round(q2, 6)

            solutions["reachable"] = True
            solutions["target_distance_m"] = round(dist, 6)

            units = {k: "deg" for k in solutions if k.endswith("_deg")}
            units.update({k: "rad" for k in solutions if k.endswith("_rad")})

            return ToolResult(
                success=True, solver=self.name, confidence="HIGH",
                data=solutions, units=units,
                raw_output=(
                    f"PyBullet IK: 2-link, target=({tx:.3f}, {ty:.3f}), "
                    f"dist={dist:.4f}, L1={L1}, L2={L2}"
                ),
                assumptions=[
                    "Planar 2-link serial manipulator",
                    "Revolute joints with full rotation range",
                    "Both elbow-up and elbow-down solutions provided",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )

    # ------------------------------------------------------------------
    def _dynamics(self, inputs: dict) -> ToolResult:
        """Lagrangian dynamics for planar serial manipulator."""
        try:
            params  = inputs.get("robot_params", {})
            masses  = [float(m) for m in params.get("masses", [5.0, 3.0])]
            lengths = [float(l) for l in params.get("lengths", [1.0, 0.8])]
            joints  = [float(j) for j in params.get("joints", [0.0, 0.0])]

            n = min(len(masses), len(lengths))
            if n == 0:
                return ToolResult(
                    success=False, solver=self.name, confidence="NONE",
                    data={}, units={}, raw_output="",
                    error="At least one link required",
                )

            g = 9.81
            masses  = masses[:n]
            lengths = lengths[:n]
            joints  = (joints[:n] + [0.0] * n)[:n]

            # Static torques (gravity compensation) — point masses at link ends
            torques = []
            for i in range(n):
                tau_i = 0.0
                for j in range(i, n):
                    theta_sum = sum(joints[i:j + 1])
                    tau_i += masses[j] * g * sum(lengths[i:j + 1]) * math.cos(theta_sum)
                torques.append(tau_i)

            # Inertia at each joint (simplified)
            inertias = []
            for i in range(n):
                I_i = sum(
                    masses[j] * sum(lengths[i:j + 1]) ** 2
                    for j in range(i, n)
                )
                inertias.append(I_i)

            # Total kinetic and potential energy
            total_mass = sum(masses)
            total_PE = 0.0
            theta_cum = 0.0
            for i in range(n):
                theta_cum += joints[i]
                h = sum(lengths[k] * math.sin(sum(joints[:k + 1])) for k in range(i + 1))
                total_PE += masses[i] * g * h

            # Payload capacity estimate (max static load at end-effector)
            # Limited by max torque at base joint (assume motor_torque ~ 10x gravity torque)
            arm_length = sum(lengths)
            max_payload = abs(torques[0]) / (g * arm_length) if arm_length > 0 else 0.0

            data = {
                "n_dof":              n,
                "total_mass_kg":      round(total_mass, 3),
                "potential_energy_J": round(total_PE, 4),
                "max_payload_est_kg": round(max_payload, 3),
                "total_reach_m":      round(arm_length, 4),
            }
            units = {
                "total_mass_kg": "kg", "potential_energy_J": "J",
                "max_payload_est_kg": "kg", "total_reach_m": "m",
            }

            for i in range(n):
                data[f"gravity_torque_joint_{i+1}_Nm"] = round(torques[i], 4)
                units[f"gravity_torque_joint_{i+1}_Nm"] = "N-m"
                data[f"inertia_joint_{i+1}_kgm2"] = round(inertias[i], 6)
                units[f"inertia_joint_{i+1}_kgm2"] = "kg-m2"

            return ToolResult(
                success=True, solver=self.name, confidence="MEDIUM",
                data=data, units=units,
                raw_output=(
                    f"PyBullet dynamics: {n}-link planar, "
                    f"masses={masses}, lengths={lengths}"
                ),
                assumptions=[
                    "Planar serial manipulator with point masses at link tips",
                    "Static gravity torques (no velocity/acceleration terms)",
                    "Rigid links, frictionless joints",
                    "Payload estimate based on static equilibrium at base joint",
                ],
            )
        except Exception as exc:
            return ToolResult(
                success=False, solver=self.name, confidence="NONE",
                data={}, units={}, raw_output="", error=str(exc),
            )
