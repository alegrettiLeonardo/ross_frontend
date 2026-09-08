from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from ...domain import RotorProject
from ..base import AnalysisResult, ProgressCallback
from ..coordinates import rpm_to_rad_s
from .builder import RossModelBuilder
from .results import campbell_summary, critical_speed_summary, modal_summary, static_summary


class RossBackend:
    name = "ross"

    def __init__(self, builder: RossModelBuilder | None = None, run_root: str | Path | None = None):
        self.builder = builder or RossModelBuilder()
        self.rs = self.builder.rs
        self.run_root = Path(run_root) if run_root is not None else Path.home() / ".ross_frontend" / "runs"

    @property
    def version(self) -> str:
        return str(getattr(self.rs, "__version__", "unknown"))

    @staticmethod
    def _emit(progress: ProgressCallback | None, lines: list[str], message: str) -> None:
        lines.append(message)
        if progress is not None:
            progress(message)

    def render_input(self, project: RotorProject) -> str:
        project.validate()
        payload = project.to_dict()
        payload["backend"] = {"name": self.name, "version": self.version}
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _speed_range(start_rpm: float, final_rpm: float, step_rpm: float) -> list[float]:
        speeds = []
        value = start_rpm
        while value < final_rpm - 1e-9:
            speeds.append(value)
            value += step_rpm
        speeds.append(final_rpm)
        return [rpm_to_rad_s(v) for v in speeds]

    @staticmethod
    def _num_modes(rotor: Any, requested: int) -> int:
        target = max(2, 2 * int(requested))
        ndof = int(getattr(rotor, "ndof", target + 2))
        limit = max(2, ndof - 2)
        target = min(target, limit)
        return target if target % 2 == 0 else target - 1

    @staticmethod
    def _realization_audit(project: RotorProject, build) -> dict[str, Any]:
        """Describe adapter choices that are mathematically equivalent but not 1:1 classes."""

        return {
            "flexible_supports": {
                "domain_count": len(project.supports),
                "ross_topology": (
                    "BearingElement(rotor_n, n_link=housing) + "
                    "PointMass(housing, mx=my=mz=mass) + "
                    "BearingElement(housing)->ground"
                ),
                "housing_link_nodes": {
                    str(index): node for index, node in build.support_link_node_by_bearing.items()
                },
                "housing_mass_elements": len(build.support_mass_elements),
                "lateral_housing_mass_source": "SupportSpec.mass_kg mapped to x/y",
                "support_link_axial_completion": (
                    "PointMass mz=mass_kg is a ROSS 3-DOF n_link numerical completion; "
                    "the axial housing DOF has zero K/C and zero off-diagonal M coupling to the lateral subsystem"
                ),
                "reason": (
                    "Canonical ROSS 2.3.0 linked-bearing/support topology. Positive mz prevents a singular global "
                    "mass matrix while leaving the historical RotorDin lateral x/z dynamics unchanged."
                ),
            },
            "concentrated_masses": {
                "domain_count": len(project.point_masses),
                "ross_carrier_count": len(build.point_mass_elements),
                "ross_realization": "DiskElement(m=mass, Id=0, Ip=0)",
                "reason": (
                    "ROSS 2.3.0 PointMass positioning assumes a bearing at the same station; "
                    "the zero-inertia disk carrier preserves translational mass with zero rotary inertia/gyroscopic moment."
                ),
            },
            "ump": {
                "dynamic_rotor": "UmpRotor" if project.ump_regions else "native Rotor",
                "static_rotor": "base_rotor without UMP",
                "matrix_identity": "K_effective = K_ROSS - K_UMP" if project.ump_regions else "K_effective = K_ROSS",
                "shaft_elements_modified": False,
                "rhs_force_used": False,
            },
        }

    def _write_ump_audit(self, run_dir: Path, project: RotorProject, build, audit_frequency_rpm: float) -> dict[str, Any]:
        import numpy as np

        rotor = build.rotor
        frequency = rpm_to_rad_s(audit_frequency_rpm)
        k_without = np.asarray(rotor.K_without_ump(frequency), dtype=float)
        k_ump = np.asarray(build.K_ump, dtype=float)
        k_effective = np.asarray(rotor.K(frequency), dtype=float)
        residual = k_effective - (k_without - k_ump)
        identity_error = float(np.max(np.abs(residual))) if residual.size else 0.0

        payload = dict(build.ump_audit)
        payload.update(
            {
                "audit_frequency_rpm": float(audit_frequency_rpm),
                "audit_frequency_rad_s": float(frequency),
                "regions": [asdict(region) for region in project.ump_regions],
                "matrix_identity": "K_effective = K_without_ump - K_ump",
                "matrix_identity_max_abs_error": identity_error,
                "K_ump_frobenius_norm": float(np.linalg.norm(k_ump)),
                "static_and_stiffness_map_rotor": "base_rotor_without_ump",
            }
        )
        (run_dir / "ump_audit.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        np.savez_compressed(
            run_dir / "K_without_ump.npz",
            matrix=k_without,
            frequency_rpm=float(audit_frequency_rpm),
            frequency_rad_s=float(frequency),
        )
        np.savez_compressed(run_dir / "K_ump.npz", matrix=k_ump)
        np.savez_compressed(
            run_dir / "K_effective.npz",
            matrix=k_effective,
            frequency_rpm=float(audit_frequency_rpm),
            frequency_rad_s=float(frequency),
        )
        return payload

    def run(self, project: RotorProject, progress: ProgressCallback | None = None) -> AnalysisResult:
        project.validate()
        self.run_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_ref = re.sub(r"[^A-Za-z0-9_.-]+", "_", project.reference.strip() or "calculation")[:80]
        run_dir = self.run_root / f"{stamp}_{safe_ref}"
        run_dir.mkdir(parents=False, exist_ok=False)

        log: list[str] = []
        self._emit(progress, log, f"ROSS {self.version}: building rotor model...")
        build = self.builder.build(project)
        rotor = build.rotor
        self._emit(
            progress,
            log,
            f"Model built: {len(build.shaft_elements)} shaft elements, {len(build.bearing_elements)} bearings, "
            f"{len(build.disk_elements)} disks, {len(build.point_mass_elements)} concentrated mass(es), "
            f"{len(build.support_mass_elements)} housing mass(es), {getattr(rotor, 'ndof', '?')} DOF.",
        )
        if project.ump_regions:
            self._emit(
                progress,
                log,
                f"UMP active: {len(project.ump_regions)} region(s), {len(build.ump_contributions)} element contribution(s); "
                "dynamic K = K_ROSS - K_UMP.",
            )

        audit = {
            "reference": project.reference,
            "backend": self.name,
            "backend_version": self.version,
            "node_by_position_mm": {str(k): v for k, v in build.node_by_position_mm.items()},
            "counts": {
                "shaft_elements": len(build.shaft_elements),
                "bearings": len(build.bearing_elements),
                "domain_disks": len(build.disk_elements),
                "domain_point_masses": len(build.point_mass_elements),
                "support_housing_masses": len(build.support_mass_elements),
                "ross_disk_elements": len(build.disk_elements) + len(build.point_mass_elements),
                "ross_point_mass_elements": len(build.support_mass_elements),
                "ndof": getattr(rotor, "ndof", None),
                "ump_regions": len(project.ump_regions),
                "ump_element_contributions": len(build.ump_contributions),
            },
            "realizations": self._realization_audit(project, build),
            "ump": build.ump_audit,
        }
        (run_dir / "model.json").write_text(
            json.dumps(audit, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        (run_dir / "project.json").write_text(self.render_input(project), encoding="utf-8")

        sections: dict[str, str] = {
            "ross_model.json": json.dumps(audit, indent=2, ensure_ascii=False, default=str) + "\n"
        }
        data: dict[str, Any] = {"model": audit}
        if project.ump_regions:
            ump_audit = self._write_ump_audit(run_dir, project, build, project.analyses.modal_speed_rpm)
            data["ump"] = ump_audit
            sections["ump_audit.json"] = json.dumps(
                ump_audit, indent=2, ensure_ascii=False, default=str
            ) + "\n"

        critical_points = []
        num_modes = self._num_modes(rotor, project.analyses.modes)

        if project.analyses.static:
            self._emit(progress, log, "Running ROSS static analysis without UMP, matching RotorDin mkb intent...")
            result = build.base_rotor.run_static()
            summary = static_summary(result)
            data["static"] = summary
            sections["static.json"] = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

        if project.analyses.modal:
            self._emit(progress, log, f"Running modal analysis at {project.analyses.modal_speed_rpm:g} rpm...")
            result = rotor.run_modal(speed=rpm_to_rad_s(project.analyses.modal_speed_rpm), num_modes=num_modes)
            summary = modal_summary(result)
            data["modal"] = summary
            sections["modal.json"] = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

        if project.analyses.critical_speed:
            self._emit(progress, log, "Running critical-speed analysis...")
            result = rotor.run_critical_speed(num_modes=num_modes)
            summary, critical_points = critical_speed_summary(result)
            data["critical_speed"] = summary
            sections["critical_speed.json"] = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

        if project.analyses.campbell:
            self._emit(
                progress,
                log,
                f"Running Campbell analysis from {project.analyses.campbell_initial_rpm:g} to "
                f"{project.analyses.campbell_final_rpm:g} rpm...",
            )
            speed_range = self._speed_range(
                project.analyses.campbell_initial_rpm,
                project.analyses.campbell_final_rpm,
                project.analyses.campbell_step_rpm,
            )
            result = rotor.run_campbell(speed_range=speed_range, frequencies=project.analyses.modes)
            summary = campbell_summary(result)
            data["campbell"] = summary
            sections["campbell.json"] = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

        self._emit(progress, log, "ROSS analysis completed.")
        stdout = "\n".join(log) + "\n"
        (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        result_payload = {
            "backend": self.name,
            "backend_version": self.version,
            "critical_speeds": [asdict(p) for p in critical_points],
            "data": data,
        }
        (run_dir / "results.json").write_text(
            json.dumps(result_payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        return AnalysisResult(
            backend=self.name,
            backend_version=self.version,
            run_dir=run_dir,
            stdout=stdout,
            sections=sections,
            data=data,
            critical_speeds=critical_points,
        )
