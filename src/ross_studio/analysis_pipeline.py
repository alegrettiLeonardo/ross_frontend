from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, pi, radians, sin
from time import perf_counter
from typing import Any, Callable

import numpy as np

from .analysis_backend import RossAnalysisBackend
from .domain import EngineeringError, LoadSpec, ProbeSpec, RotorProject
from .ross_backend import RossBuildResult


@dataclass(slots=True, frozen=True)
class AnalysisPolicy:
    """Numerical policy for the qualified 0.8 engineering pipeline."""

    modal_num_modes: int = 12
    campbell_frequencies: int = 6
    campbell_points: int = 37
    response_points: int = 73
    critical_dedup_rpm: float = 5.0


@dataclass(slots=True, frozen=True)
class PipelineEvent:
    stage: str
    state: str
    index: int
    total: int
    message: str
    elapsed_s: float = 0.0


@dataclass(slots=True, frozen=True)
class AnalysisAudit:
    code: str
    message: str
    severity: str = "info"


@dataclass(slots=True, frozen=True)
class ModalModeSummary:
    mode: int
    wn_hz: float
    wd_hz: float
    damping_ratio: float
    log_dec: float
    whirl: str


@dataclass(slots=True, frozen=True)
class CriticalSpeedSummary:
    mode: int
    speed_rpm: float
    frequency_hz: float
    damping_ratio: float
    log_dec: float
    whirl: str
    method: str = "ROSS Campbell 1X crossing"


@dataclass(slots=True, frozen=True)
class ProbeResponseSummary:
    name: str
    node: int
    position_mm: float
    coordinate: int
    orientation_deg: float
    peak_speed_rpm: float
    peak_amplitude_m: float
    peak_phase_deg: float
    rated_speed_rpm: float
    rated_amplitude_m: float
    rated_phase_deg: float
    amplitude_m: tuple[float, ...]
    phase_deg: tuple[float, ...]

    @property
    def peak_amplitude_um(self) -> float:
        return self.peak_amplitude_m * 1e6

    @property
    def rated_amplitude_um(self) -> float:
        return self.rated_amplitude_m * 1e6


@dataclass(slots=True)
class AnalysisPipelineResult:
    project_name: str
    build: RossBuildResult
    static: Any
    modal: Any
    critical_native: Any | None
    campbell: Any
    unbalance: Any
    speed_rpm: np.ndarray
    modal_modes: list[ModalModeSummary]
    critical_speeds: list[CriticalSpeedSummary]
    probe_responses: list[ProbeResponseSummary]
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)

    @property
    def total_elapsed_s(self) -> float:
        return float(sum(self.stage_elapsed_s.values()))

    @property
    def first_critical_rpm(self) -> float | None:
        return self.critical_speeds[0].speed_rpm if self.critical_speeds else None

    @property
    def second_critical_rpm(self) -> float | None:
        return self.critical_speeds[1].speed_rpm if len(self.critical_speeds) > 1 else None

    @property
    def max_probe_amplitude_um(self) -> float | None:
        if not self.probe_responses:
            return None
        return max(item.peak_amplitude_um for item in self.probe_responses)

    @property
    def min_modal_damping_ratio(self) -> float | None:
        if not self.modal_modes:
            return None
        return min(item.damping_ratio for item in self.modal_modes)


ProgressCallback = Callable[[PipelineEvent], None]
CancelCallback = Callable[[], bool]


class AnalysisPipelineService:
    """Orchestrate a single strict ROSS rotor through the real analysis chain.

    The model is built exactly once. All subsequent ROSS calls operate on the same
    qualified Rotor instance so topology, masses, bearings and support link nodes
    cannot drift between analyses.
    """

    STAGES = (
        "Strict Rotor",
        "Static",
        "Modal",
        "Critical Speeds",
        "Campbell",
        "Unbalance Response",
        "Probes",
        "Results",
    )

    def __init__(self, backend: RossAnalysisBackend | None = None, policy: AnalysisPolicy | None = None) -> None:
        self.backend = backend or RossAnalysisBackend()
        self.policy = policy or AnalysisPolicy()

    @staticmethod
    def _emit(callback: ProgressCallback | None, event: PipelineEvent) -> None:
        if callback is not None:
            callback(event)

    @staticmethod
    def _check_cancel(cancelled: CancelCallback | None) -> None:
        if cancelled is not None and cancelled():
            raise EngineeringError("Analysis cancelled by user after the current ROSS stage.")

    @staticmethod
    def _bearing_envelope_rpm(project: RotorProject) -> tuple[float, float, list[AnalysisAudit]]:
        case = project.operating_cases[0]
        low = float(case.speed_min_rpm)
        high = float(case.speed_max_rpm)
        audits: list[AnalysisAudit] = []
        tables = [bearing.coefficients for bearing in project.bearings if bearing.coefficients]
        if tables:
            table_low = max(min(point.rpm for point in points) for points in tables)
            table_high = min(max(point.rpm for point in points) for points in tables)
            requested_low, requested_high = low, high
            low = max(low, table_low)
            high = min(high, table_high)
            if low > requested_low + 1e-9 or high < requested_high - 1e-9:
                audits.append(AnalysisAudit(
                    "BEARING_KC_ENVELOPE",
                    f"Dynamic sweep constrained from {requested_low:g}-{requested_high:g} rpm to "
                    f"{low:g}-{high:g} rpm so ROSS does not extrapolate the imported bearing K/C tables.",
                    "warning",
                ))
        if high <= low:
            raise EngineeringError(f"No valid dynamic speed interval remains after bearing K/C limits: {low:g}-{high:g} rpm.")
        return low, high, audits

    @staticmethod
    def _speed_grid(low_rpm: float, high_rpm: float, points: int, rated_rpm: float) -> np.ndarray:
        if points < 2:
            raise EngineeringError("Analysis speed grid requires at least two points.")
        grid = np.linspace(low_rpm, high_rpm, points, dtype=float)
        if low_rpm - 1e-9 <= rated_rpm <= high_rpm + 1e-9:
            grid = np.unique(np.append(grid, float(rated_rpm)))
        return np.sort(grid)

    @staticmethod
    def _whirl_label(value: float) -> str:
        if not np.isfinite(value):
            return "Non-lateral"
        if value < 0.25:
            return "Forward"
        if value > 0.75:
            return "Backward"
        return "Mixed"

    @staticmethod
    def _modal_summary(modal: Any) -> list[ModalModeSummary]:
        whirl = modal.whirl_direction()
        rows: list[ModalModeSummary] = []
        for i, (wn, wd, damping, log_dec) in enumerate(
            zip(modal.wn, modal.wd, modal.damping_ratio, modal.log_dec), 1
        ):
            rows.append(ModalModeSummary(
                mode=i,
                wn_hz=float(wn) / (2.0 * pi),
                wd_hz=float(wd) / (2.0 * pi),
                damping_ratio=float(damping),
                log_dec=float(log_dec),
                whirl=str(whirl[i - 1]),
            ))
        return rows

    def _critical_from_campbell(self, campbell: Any) -> list[CriticalSpeedSummary]:
        speed = np.asarray(campbell.speed_range, dtype=float)
        wd = np.asarray(campbell.wd, dtype=float)
        damping = np.asarray(campbell.damping_ratio, dtype=float)
        log_dec = np.asarray(campbell.log_dec, dtype=float)
        whirl = np.asarray(campbell.whirl_values, dtype=float)
        crossings: list[CriticalSpeedSummary] = []

        for mode in range(wd.shape[1]):
            delta = wd[:, mode] - speed
            for i in range(len(speed) - 1):
                f0, f1 = delta[i], delta[i + 1]
                if not (np.isfinite(f0) and np.isfinite(f1)):
                    continue
                if f0 == 0.0:
                    alpha = 0.0
                elif f0 * f1 > 0.0:
                    continue
                elif f1 == f0:
                    alpha = 0.5
                else:
                    alpha = float(-f0 / (f1 - f0))
                if not 0.0 <= alpha <= 1.0:
                    continue
                omega = float(speed[i] + alpha * (speed[i + 1] - speed[i]))
                damping_i = float(damping[i, mode] + alpha * (damping[i + 1, mode] - damping[i, mode]))
                log_dec_i = float(log_dec[i, mode] + alpha * (log_dec[i + 1, mode] - log_dec[i, mode]))
                whirl_value = float(whirl[i, mode] if alpha < 0.5 else whirl[i + 1, mode])
                crossings.append(CriticalSpeedSummary(
                    mode=mode + 1,
                    speed_rpm=omega * 60.0 / (2.0 * pi),
                    frequency_hz=omega / (2.0 * pi),
                    damping_ratio=damping_i,
                    log_dec=log_dec_i,
                    whirl=self._whirl_label(whirl_value),
                ))

        crossings.sort(key=lambda row: row.speed_rpm)
        deduped: list[CriticalSpeedSummary] = []
        for row in crossings:
            if deduped and abs(row.speed_rpm - deduped[-1].speed_rpm) <= self.policy.critical_dedup_rpm:
                if abs(row.damping_ratio) < abs(deduped[-1].damping_ratio):
                    deduped[-1] = row
                continue
            deduped.append(row)
        return deduped

    @staticmethod
    def _unbalance_kg_m(load: LoadSpec) -> float:
        unit = str(load.metadata.get("magnitude_unit", "kg*m")).replace(" ", "").lower()
        factors = {
            "kg*m": 1.0,
            "kg.m": 1.0,
            "kgm": 1.0,
            "kg*mm": 1e-3,
            "kg.mm": 1e-3,
            "g*mm": 1e-6,
            "g.mm": 1e-6,
        }
        if unit not in factors:
            raise EngineeringError(f"Unsupported unbalance unit {unit!r} for {load.name!r}.")
        return float(load.magnitude) * factors[unit]

    @staticmethod
    def _project_probe(response: Any, rotor: Any, node: int, spec: ProbeSpec) -> np.ndarray:
        ndof = int(rotor.number_dof)
        x = np.asarray(response.forced_resp[node * ndof + 0, :], dtype=complex)
        y = np.asarray(response.forced_resp[node * ndof + 1, :], dtype=complex)
        angle = radians(float(spec.orientation_deg))
        if spec.coordinate == 1:
            return x * cos(angle) + y * sin(angle)
        if spec.coordinate == 2:
            return y * cos(angle) - x * sin(angle)
        raise EngineeringError(
            f"Probe {spec.name!r} uses legacy coordinate {spec.coordinate}; only lateral coordinates 1 and 2 are qualified."
        )

    def _probe_summaries(
        self,
        project: RotorProject,
        build: RossBuildResult,
        response: Any,
        speed_rpm: np.ndarray,
    ) -> list[ProbeResponseSummary]:
        rated_rpm = float(project.operating_cases[0].rated_speed_rpm)
        rated_index = int(np.argmin(np.abs(speed_rpm - rated_rpm)))
        rows: list[ProbeResponseSummary] = []
        for spec in project.probes:
            node = build.node_insertion_plan.node_for(spec.position_mm)
            if node is None:
                raise EngineeringError(f"Probe {spec.name!r} at {spec.position_mm:g} mm has no exact analysis node.")
            projected = self._project_probe(response, build.rotor, node, spec)
            magnitude = np.abs(projected)
            phase = np.degrees(np.angle(projected))
            peak_index = int(np.nanargmax(magnitude))
            rows.append(ProbeResponseSummary(
                name=spec.name,
                node=node,
                position_mm=float(spec.position_mm),
                coordinate=int(spec.coordinate),
                orientation_deg=float(spec.orientation_deg),
                peak_speed_rpm=float(speed_rpm[peak_index]),
                peak_amplitude_m=float(magnitude[peak_index]),
                peak_phase_deg=float(phase[peak_index]),
                rated_speed_rpm=float(speed_rpm[rated_index]),
                rated_amplitude_m=float(magnitude[rated_index]),
                rated_phase_deg=float(phase[rated_index]),
                amplitude_m=tuple(float(v) for v in magnitude),
                phase_deg=tuple(float(v) for v in phase),
            ))
        return rows

    def run(
        self,
        project: RotorProject,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancelCallback | None = None,
    ) -> AnalysisPipelineResult:
        project.validate()
        case = project.operating_cases[0]
        low_rpm, high_rpm, audits = self._bearing_envelope_rpm(project)
        campbell_speed_rpm = self._speed_grid(low_rpm, high_rpm, self.policy.campbell_points, case.rated_speed_rpm)
        response_speed_rpm = self._speed_grid(low_rpm, high_rpm, self.policy.response_points, case.rated_speed_rpm)
        stage_elapsed: dict[str, float] = {}
        total = len(self.STAGES)

        def stage(index: int, name: str, message: str, fn: Callable[[], Any]) -> Any:
            self._check_cancel(cancelled)
            self._emit(progress, PipelineEvent(name, "running", index, total, message))
            start = perf_counter()
            try:
                value = fn()
            except Exception as exc:
                elapsed = perf_counter() - start
                self._emit(progress, PipelineEvent(name, "failed", index, total, str(exc), elapsed))
                raise
            elapsed = perf_counter() - start
            stage_elapsed[name] = elapsed
            self._emit(progress, PipelineEvent(name, "completed", index, total, message, elapsed))
            return value

        build = stage(1, "Strict Rotor", "Building one qualified ROSS Rotor with strict=True", lambda: self.backend.build_rotor(project, strict=True))
        static = stage(2, "Static", "ROSS gravity/static solution", lambda: self.backend.run_static_build(build))
        audits.append(AnalysisAudit(
            "ROSS_STATIC_SUPPORT_POLICY",
            "ROSS 2.3 run_static() computes gravity reactions with rigidized shaft bearing supports; dynamic flexible-support K/C remains active in modal/response analyses.",
            "info",
        ))
        modal = stage(
            3,
            "Modal",
            f"ROSS modal solution at rated speed {case.rated_speed_rpm:g} rpm",
            lambda: self.backend.run_modal_build(build, case.rated_speed_rpm, num_modes=self.policy.modal_num_modes),
        )
        modal_modes = self._modal_summary(modal)

        # Critical speeds are extracted from a ROSS Campbell sweep rather than
        # Rotor.run_critical_speed(), because the native Newton initializer calls
        # run_modal(0). The OP-W60 imported K/C tables begin at 900 rpm; using the
        # valid bearing-data envelope avoids silent spline extrapolation below it.
        campbell_holder: dict[str, Any] = {}

        def critical_stage() -> list[CriticalSpeedSummary]:
            campbell = self.backend.run_campbell_build(
                build,
                campbell_speed_rpm.tolist(),
                frequencies=self.policy.campbell_frequencies,
            )
            campbell_holder["result"] = campbell
            return self._critical_from_campbell(campbell)

        critical = stage(
            4,
            "Critical Speeds",
            f"ROSS modal sweep + synchronous 1X crossings inside {low_rpm:g}-{high_rpm:g} rpm",
            critical_stage,
        )
        audits.append(AnalysisAudit(
            "CRITICAL_METHOD",
            "Critical speeds use 1X crossings of the real ROSS Campbell branches inside the qualified K/C speed envelope; native run_critical_speed() is intentionally not used because it initializes at 0 rad/s.",
            "info",
        ))
        campbell = stage(
            5,
            "Campbell",
            f"Qualified ROSS Campbell result with {len(campbell_speed_rpm)} speed stations",
            lambda: campbell_holder["result"],
        )

        unbalance_loads = [load for load in project.loads if load.kind.strip().casefold() == "unbalance"]
        if not unbalance_loads:
            raise EngineeringError("The selected pipeline requires at least one unbalance load.")
        unbalance_nodes: list[int] = []
        unbalance_magnitude: list[float] = []
        unbalance_phase: list[float] = []
        for load in unbalance_loads:
            node = build.node_insertion_plan.node_for(load.position_mm)
            if node is None:
                raise EngineeringError(f"Unbalance {load.name!r} at {load.position_mm:g} mm has no exact analysis node.")
            unbalance_nodes.append(node)
            unbalance_magnitude.append(self._unbalance_kg_m(load))
            unbalance_phase.append(radians(float(load.phase_deg)))
        audits.append(AnalysisAudit(
            "UNBALANCE_INPUT_UNITS",
            "; ".join(
                f"{load.name}: {load.magnitude:g} {load.metadata.get('magnitude_unit', 'kg*m')} at x={load.position_mm:g} mm"
                for load in unbalance_loads
            ),
            "info",
        ))

        response = stage(
            6,
            "Unbalance Response",
            f"ROSS synchronous response at {len(response_speed_rpm)} speed stations for {len(unbalance_nodes)} unbalance load(s)",
            lambda: self.backend.run_unbalance_build(
                build,
                unbalance_nodes,
                unbalance_magnitude,
                unbalance_phase,
                response_speed_rpm.tolist(),
            ),
        )
        probes = stage(
            7,
            "Probes",
            f"Projecting {len(project.probes)} legacy probe channels from the complex ROSS response",
            lambda: self._probe_summaries(project, build, response, response_speed_rpm),
        )
        stage(8, "Results", "Packaging traceable engineering summaries for GUI/results", lambda: True)

        if not np.all(np.isfinite(np.asarray(modal.wd, dtype=float))):
            raise EngineeringError("Modal solution contains non-finite damped natural frequencies.")
        if not np.all(np.isfinite(np.asarray(campbell.wd, dtype=float))):
            raise EngineeringError("Campbell solution contains non-finite frequencies.")
        if not np.all(np.isfinite(np.abs(np.asarray(response.forced_resp)))):
            raise EngineeringError("Unbalance response contains non-finite complex amplitudes.")

        return AnalysisPipelineResult(
            project_name=project.name,
            build=build,
            static=static,
            modal=modal,
            critical_native=None,
            campbell=campbell,
            unbalance=response,
            speed_rpm=response_speed_rpm,
            modal_modes=modal_modes,
            critical_speeds=critical,
            probe_responses=probes,
            audits=audits,
            stage_elapsed_s=stage_elapsed,
        )


__all__ = [
    "AnalysisAudit",
    "AnalysisPipelineResult",
    "AnalysisPipelineService",
    "AnalysisPolicy",
    "CriticalSpeedSummary",
    "ModalModeSummary",
    "PipelineEvent",
    "ProbeResponseSummary",
]
