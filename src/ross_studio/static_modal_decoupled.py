from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

import numpy as np

from .analysis_backend import RossAnalysisBackend
from .analysis_pipeline import AnalysisAudit, AnalysisPipelineService
from .domain import EngineeringError, RotorProject
from .ross_backend import RossBuildResult
from .static_modal_analysis import StaticModalAnalysisService, StaticModalModeSummary


ProgressCallback = Callable[[str, str], None]
CancelCallback = Callable[[], bool]


@dataclass(slots=True, frozen=True)
class ModalAnalysisRequest:
    """Independent numerical request for native ROSS modal + Campbell analysis."""

    speed_rpm: float
    num_modes: int = 24
    campbell_min_rpm: float | None = None
    campbell_max_rpm: float | None = None
    campbell_points: int = 41
    campbell_frequencies: int = 8

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

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.speed_rpm), 12),
            int(self.num_modes),
            None if self.campbell_min_rpm is None else round(float(self.campbell_min_rpm), 12),
            None if self.campbell_max_rpm is None else round(float(self.campbell_max_rpm), 12),
            int(self.campbell_points),
            int(self.campbell_frequencies),
        )


@dataclass(slots=True)
class StaticAnalysisResult:
    project_name: str
    build: RossBuildResult
    static: Any
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)

    @property
    def total_elapsed_s(self) -> float:
        return float(sum(self.stage_elapsed_s.values()))


@dataclass(slots=True)
class ModalAnalysisResult:
    project_name: str
    build: RossBuildResult
    request: ModalAnalysisRequest
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


class _IndependentRossService:
    def __init__(self, backend: RossAnalysisBackend | None = None) -> None:
        self.backend = backend or RossAnalysisBackend()

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, state: str) -> None:
        if callback is not None:
            callback(stage, state)

    @staticmethod
    def _check_cancel(cancelled: CancelCallback | None, label: str) -> None:
        if cancelled is not None and cancelled():
            raise EngineeringError(f"{label} analysis cancelled by user after the current ROSS stage.")

    def _stage(
        self,
        elapsed: dict[str, float],
        name: str,
        fn: Callable[[], Any],
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCallback | None,
        label: str,
    ) -> Any:
        self._check_cancel(cancelled, label)
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

    @staticmethod
    def _validate_exact_nodes(build: RossBuildResult, label: str) -> None:
        if build.unresolved_positions_mm:
            raise EngineeringError(
                f"{label} requires exact ROSS nodes; unresolved positions: "
                + ", ".join(f"{value:g} mm" for value in build.unresolved_positions_mm)
            )


class StaticAnalysisService(_IndependentRossService):
    """Own exactly one independent native ``Rotor.run_static()`` transaction."""

    def run(
        self,
        project: RotorProject,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> StaticAnalysisResult:
        project.validate()
        elapsed: dict[str, float] = {}
        build = self._stage(
            elapsed,
            "Static · Strict Rotor",
            lambda: self.backend.build_rotor(project, strict=True),
            progress=progress,
            cancelled=cancelled,
            label="Static",
        )
        self._validate_exact_nodes(build, "Static")
        static = self._stage(
            elapsed,
            "Static · Solve",
            lambda: self.backend.run_static_build(build),
            progress=progress,
            cancelled=cancelled,
            label="Static",
        )
        return StaticAnalysisResult(
            project_name=project.name,
            build=build,
            static=static,
            audits=[
                AnalysisAudit(
                    "ROSS_STATIC_NATIVE_020",
                    "Independent Static transaction: results come directly from Rotor.run_static(); Modal/Campbell are not executed.",
                    "info",
                )
            ],
            stage_elapsed_s=elapsed,
        )


class ModalAnalysisService(_IndependentRossService):
    """Own one independent native ``run_modal()`` + ``run_campbell()`` transaction."""

    def run(
        self,
        project: RotorProject,
        request: ModalAnalysisRequest,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> ModalAnalysisResult:
        project.validate()
        request.validate()
        low_rpm, high_rpm, audits = StaticModalAnalysisService._campbell_bounds(project, request)
        case = project.operating_cases[0]
        speed_grid = AnalysisPipelineService._speed_grid(
            low_rpm,
            high_rpm,
            request.campbell_points,
            case.rated_speed_rpm,
        )
        elapsed: dict[str, float] = {}
        build = self._stage(
            elapsed,
            "Modal · Strict Rotor",
            lambda: self.backend.build_rotor(project, strict=True),
            progress=progress,
            cancelled=cancelled,
            label="Modal",
        )
        self._validate_exact_nodes(build, "Modal")
        modal = self._stage(
            elapsed,
            "Modal · Solve",
            lambda: self.backend.run_modal_build(build, request.speed_rpm, num_modes=request.num_modes),
            progress=progress,
            cancelled=cancelled,
            label="Modal",
        )
        modes = StaticModalAnalysisService._mode_summaries(modal)
        campbell = self._stage(
            elapsed,
            "Campbell · Solve",
            lambda: self.backend.run_campbell_build(
                build,
                speed_grid.tolist(),
                frequencies=request.campbell_frequencies,
            ),
            progress=progress,
            cancelled=cancelled,
            label="Modal",
        )
        if not np.all(np.isfinite(np.asarray(modal.wd, dtype=float))):
            raise EngineeringError("ROSS modal solution contains non-finite damped natural frequencies.")
        if not np.all(np.isfinite(np.asarray(campbell.wd, dtype=float))):
            raise EngineeringError("ROSS Campbell solution contains non-finite frequencies.")
        audits.extend(
            [
                AnalysisAudit(
                    "ROSS_MODAL_NATIVE_020",
                    "Independent Modal transaction: frequencies, damping and shapes come directly from Rotor.run_modal(); Static is not executed.",
                    "info",
                ),
                AnalysisAudit(
                    "ROSS_CAMPBELL_NATIVE_020",
                    "Campbell is retained with the Modal transaction and comes directly from Rotor.run_campbell(); plot harmonics are post-processing only.",
                    "info",
                ),
            ]
        )
        return ModalAnalysisResult(
            project_name=project.name,
            build=build,
            request=request,
            modal=modal,
            campbell=campbell,
            campbell_speed_rpm=speed_grid,
            modal_modes=modes,
            audits=audits,
            stage_elapsed_s=elapsed,
        )


__all__ = [
    "ModalAnalysisRequest",
    "ModalAnalysisResult",
    "ModalAnalysisService",
    "StaticAnalysisResult",
    "StaticAnalysisService",
]
