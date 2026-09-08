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
            f"{len(build.disk_elements)} disks, {getattr(rotor, 'ndof', '?')} DOF.",
        )

        audit = {
            "reference": project.reference,
            "backend": self.name,
            "backend_version": self.version,
            "node_by_position_mm": {str(k): v for k, v in build.node_by_position_mm.items()},
            "counts": {
                "shaft_elements": len(build.shaft_elements),
                "bearings": len(build.bearing_elements),
                "disks": len(build.disk_elements),
                "point_masses": len(build.point_mass_elements),
                "ndof": getattr(rotor, "ndof", None),
            },
        }
        (run_dir / "model.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "project.json").write_text(self.render_input(project), encoding="utf-8")

        sections: dict[str, str] = {"ross_model.json": json.dumps(audit, indent=2, ensure_ascii=False) + "\n"}
        data: dict[str, Any] = {"model": audit}
        critical_points = []
        num_modes = self._num_modes(rotor, project.analyses.modes)

        if project.analyses.static:
            self._emit(progress, log, "Running ROSS static analysis...")
            result = rotor.run_static()
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
            json.dumps(result_payload, indent=2, ensure_ascii=False), encoding="utf-8"
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
