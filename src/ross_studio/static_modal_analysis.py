from __future__ import annotations

from dataclasses import dataclass, field
from math import pi
from time import perf_counter
from typing import Any, Callable

import numpy as np

from .analysis_backend import RossAnalysisBackend
from .analysis_pipeline import AnalysisAudit, AnalysisPipelineService
from .domain import EngineeringError, RotorProject
from .ross_backend import RossBuildResult


@dataclass(slots=True, frozen=True)
class StaticModalRequest:
    """Numerical request for the dedicated ROSS Static & Modal workspace."""

    speed_rpm: float
    num_modes: int = 24
    campbell_min_rpm: float | None = None
    campbell_max_rpm: float | None = None
    campbell_points: int = 41
    campbell_frequencies: int = 8
    include_static: bool = True

    def validate(self) -> None:
        if self.speed_rpm < 0:
            raise EngineeringError(f"Modal speed must be >= 0 rpm; received {self.speed_rpm:g} rpm.")
        if isinstance(self.num_modes, bool) or self.num_modes < 4 or self.num_modes > 128:
            raise EngineeringError(f"Modal num_modes must be between 4 and 128; received {self.num_modes!r}.")
        if self.num_modes % 2:
            raise EngineeringError(f"Modal num_modes must be even for the qualified ROSS solve; received {self.num_modes}.")
        if isinstance(self.campbell_points, bool) or self.campbell_points < 5 or self.campbell_points > 401:
            raise EngineeringError(
                f"Campbell point count must be between 5 and 401; received {self.campbell_points!r}."
            )
        if isinstance(self.campbell_frequencies, bool) or self.campbell_frequencies < 2 or self.campbell_frequencies > 32:
            raise EngineeringError(
                f"Campbell frequency count must be between 2 and 32; received {self.campbell_frequencies!r}."
            )


@dataclass(slots=True, frozen=True)
class StaticModalModeSummary:
    mode_index: int
    mode_number: int
    mode_type: str
    wn_hz: float
    wd_hz: float
    damping_ratio: float
    log_dec: float
    whirl: str


@dataclass(slots=True)
class StaticModalResult:
    project_name: str
    build: RossBuildResult
    request: StaticModalRequest
    static: Any | None
    modal: Any
    campbell: Any
    campbell_speed_rpm: np.ndarray
    modal_modes: tuple[StaticModalModeSummary, ...]
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)

    @property
    def total_elapsed_s(self) -> float:
        return float(sum(self.stage_elapsed_s.values()))

    def mode_indices(self, mode_type: str) -> tuple[int, ...]:
        expected = mode_type.strip().casefold()
        return tuple(
            item.mode_index
            for item in self.modal_modes
            if item.mode_type.strip().casefold() == expected
        )


ProgressCallback = Callable[[str, str], None]
CancelCallback = Callable[[], bool]


class StaticModalAnalysisService:
    """Dedicated Static/Modal/Campbell execution using one strict ROSS Rotor.

    This service deliberately does not depend on unbalance loads. It owns only the
    native ROSS calls documented in the Static and Modal tutorial: ``run_static()``,
    ``run_modal()`` and ``run_campbell()``. Plot generation is handled separately from
    these retained result objects, so changing tabs, modes, 2D/3D or animation never
    re-solves the rotor.
    """

    def __init__(self, backend: RossAnalysisBackend | None = None) -> None:
        self.backend = backend or RossAnalysisBackend()

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, state: str) -> None:
        if callback is not None:
            callback(stage, state)

    @staticmethod
    def _check_cancel(cancelled: CancelCallback | None) -> None:
        if cancelled is not None and cancelled():
            raise EngineeringError("Static & Modal analysis cancelled by user after the current ROSS stage.")

    @staticmethod
    def _mode_summaries(modal: Any) -> tuple[StaticModalModeSummary, ...]:
        shapes = tuple(modal.shapes)
        whirl = tuple(str(value) for value in modal.whirl_direction())
        rows: list[StaticModalModeSummary] = []
        for index, (wn, wd, damping, log_dec) in enumerate(
            zip(modal.wn, modal.wd, modal.damping_ratio, modal.log_dec)
        ):
            mode_type = str(shapes[index].mode_type) if index < len(shapes) else "Unknown"
            whirl_label = whirl[index] if index < len(whirl) and mode_type == "Lateral" else mode_type
            rows.append(
                StaticModalModeSummary(
                    mode_index=index,
                    mode_number=index + 1,
                    mode_type=mode_type,
                    wn_hz=float(wn) / (2.0 * pi),
                    wd_hz=float(wd) / (2.0 * pi),
                    damping_ratio=float(damping),
                    log_dec=float(log_dec),
                    whirl=whirl_label,
                )
            )
        return tuple(rows)

    @staticmethod
    def _campbell_bounds(project: RotorProject, request: StaticModalRequest) -> tuple[float, float, list[AnalysisAudit]]:
        low, high, audits = AnalysisPipelineService._bearing_envelope_rpm(project)
        requested_low = low if request.campbell_min_rpm is None else float(request.campbell_min_rpm)
        requested_high = high if request.campbell_max_rpm is None else float(request.campbell_max_rpm)
        if requested_high <= requested_low:
            raise EngineeringError(
                f"Campbell maximum speed must be greater than minimum speed; received {requested_low:g}-{requested_high:g} rpm."
            )
        bounded_low = max(low, requested_low)
        bounded_high = min(high, requested_high)
        if bounded_high <= bounded_low:
            raise EngineeringError(
                f"Requested Campbell range {requested_low:g}-{requested_high:g} rpm lies outside the qualified "
                f"bearing K/C envelope {low:g}-{high:g} rpm."
            )
        if bounded_low != requested_low or bounded_high != requested_high:
            audits.append(
                AnalysisAudit(
                    "STATIC_MODAL_CAMPBELL_ENVELOPE",
                    f"Requested Campbell range {requested_low:g}-{requested_high:g} rpm constrained to "
                    f"{bounded_low:g}-{bounded_high:g} rpm by the bearing K/C envelope.",
                    "warning",
                )
            )
        return bounded_low, bounded_high, audits

    def run(
        self,
        project: RotorProject,
        request: StaticModalRequest,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> StaticModalResult:
        project.validate()
        request.validate()
        low_rpm, high_rpm, audits = self._campbell_bounds(project, request)
        case = project.operating_cases[0]
        speed_grid = AnalysisPipelineService._speed_grid(
            low_rpm,
            high_rpm,
            request.campbell_points,
            case.rated_speed_rpm,
        )
        elapsed: dict[str, float] = {}

        def stage(name: str, fn: Callable[[], Any]) -> Any:
            self._check_cancel(cancelled)
            self._emit(progress, name, "running")
            start = perf_counter()
            try:
                value = fn()
            except Exception:
                elapsed[name] = perf_counter() - start
                self._emit(progress, name, "failed")
                raise
            elapsed[name] = perf_counter() - start
            self._emit(progress, name, "completed")
            return value

        build = stage("Strict Rotor", lambda: self.backend.build_rotor(project, strict=True))
        if build.unresolved_positions_mm:
            raise EngineeringError(
                "Static & Modal requires exact ROSS nodes; unresolved positions: "
                + ", ".join(f"{value:g} mm" for value in build.unresolved_positions_mm)
            )

        static = None
        if request.include_static:
            static = stage("Static", lambda: self.backend.run_static_build(build))
            audits.append(
                AnalysisAudit(
                    "ROSS_STATIC_NATIVE",
                    "Static results are the native ROSS StaticResults object returned by Rotor.run_static().",
                    "info",
                )
            )

        modal = stage(
            "Modal",
            lambda: self.backend.run_modal_build(build, request.speed_rpm, num_modes=request.num_modes),
        )
        modes = self._mode_summaries(modal)

        campbell = stage(
            "Campbell",
            lambda: self.backend.run_campbell_build(
                build,
                speed_grid.tolist(),
                frequencies=request.campbell_frequencies,
            ),
        )

        if not np.all(np.isfinite(np.asarray(modal.wd, dtype=float))):
            raise EngineeringError("ROSS modal solution contains non-finite damped natural frequencies.")
        if not np.all(np.isfinite(np.asarray(campbell.wd, dtype=float))):
            raise EngineeringError("ROSS Campbell solution contains non-finite frequencies.")

        audits.extend(
            [
                AnalysisAudit(
                    "ROSS_MODAL_NATIVE",
                    "Modal frequencies, damping and shapes come directly from Rotor.run_modal(); no ROSS Studio eigensolver is used.",
                    "info",
                ),
                AnalysisAudit(
                    "ROSS_CAMPBELL_NATIVE",
                    "Campbell branches come directly from Rotor.run_campbell(); plot harmonics are post-processing only.",
                    "info",
                ),
            ]
        )

        return StaticModalResult(
            project_name=project.name,
            build=build,
            request=request,
            static=static,
            modal=modal,
            campbell=campbell,
            campbell_speed_rpm=speed_grid,
            modal_modes=modes,
            audits=audits,
            stage_elapsed_s=elapsed,
        )


__all__ = [
    "StaticModalAnalysisService",
    "StaticModalModeSummary",
    "StaticModalRequest",
    "StaticModalResult",
]
