from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, pi, radians
from time import perf_counter
from typing import Any, Callable, Iterable

import numpy as np

from .analysis_backend import RossAnalysisBackend, RossAppliedUnbalance, RossUnbalanceInput
from .analysis_pipeline import AnalysisAudit, AnalysisPipelineService
from .domain import EngineeringError, RotorProject
from .ross_backend import RossBuildResult


ProgressCallback = Callable[[str, str], None]
CancelCallback = Callable[[], bool]


@dataclass(slots=True, frozen=True)
class NativeProbe:
    """Exact-node probe description retained with a native ROSS result."""

    node: int
    orientation_deg: float
    tag: str


def _validate_sweep(low: float, high: float, points: int, label: str) -> None:
    if not (isfinite(low) and isfinite(high)) or low < 0 or high <= low:
        raise EngineeringError(f"{label} sweep must satisfy 0 <= min < max; received {low!r}-{high!r} rpm.")
    if isinstance(points, bool) or points < 3 or points > 5001:
        raise EngineeringError(f"{label} points must be between 3 and 5001; received {points!r}.")


@dataclass(slots=True, frozen=True)
class FrequencyResponseRequest:
    min_rpm: float
    max_rpm: float
    points: int = 101
    input_position_mm: float = 0.0
    input_dof: int = 1
    output_position_mm: float = 0.0
    output_dof: int = 1
    modes: tuple[int, ...] | None = None
    free_free: bool = False

    def validate(self) -> None:
        _validate_sweep(self.min_rpm, self.max_rpm, self.points, "Frequency response")
        for label, value in (("input", self.input_position_mm), ("output", self.output_position_mm)):
            if not isfinite(value) or value < 0:
                raise EngineeringError(f"Frequency-response {label} position must be >= 0 mm; received {value!r}.")
        for label, value in (("input", self.input_dof), ("output", self.output_dof)):
            if isinstance(value, bool) or int(value) not in range(6):
                raise EngineeringError(f"Frequency-response {label} DOF must be 0..5; received {value!r}.")
        if self.modes is not None and any(int(mode) < 0 for mode in self.modes):
            raise EngineeringError("Frequency-response modal reduction indices must be non-negative.")

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.min_rpm), 9), round(float(self.max_rpm), 9), int(self.points),
            round(float(self.input_position_mm), 9), int(self.input_dof),
            round(float(self.output_position_mm), 9), int(self.output_dof),
            None if self.modes is None else tuple(int(v) for v in self.modes), bool(self.free_free),
        )


@dataclass(slots=True, frozen=True)
class UnbalanceResponseRequest:
    min_rpm: float
    max_rpm: float
    points: int = 101
    modes: tuple[int, ...] | None = None
    load_names: tuple[str, ...] | None = None

    def validate(self) -> None:
        _validate_sweep(self.min_rpm, self.max_rpm, self.points, "Unbalance response")
        if self.modes is not None and any(int(mode) < 0 for mode in self.modes):
            raise EngineeringError("Unbalance-response modal reduction indices must be non-negative.")

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.min_rpm), 9), round(float(self.max_rpm), 9), int(self.points),
            None if self.modes is None else tuple(int(v) for v in self.modes),
            None if self.load_names is None else tuple(self.load_names),
        )


@dataclass(slots=True, frozen=True)
class TimeResponseRequest:
    speed_start_rpm: float
    speed_end_rpm: float
    duration_s: float = 1.0
    samples: int = 1001
    method: str = "newmark"
    include_project_unbalance: bool = True
    include_gravity: bool = False
    harmonic_position_mm: float | None = None
    harmonic_omega_rad_s: float = 0.0
    harmonic_x_n: float = 0.0
    harmonic_y_n: float = 0.0
    harmonic_phase_deg: float = 0.0

    def validate(self) -> None:
        if min(self.speed_start_rpm, self.speed_end_rpm) < 0:
            raise EngineeringError("Time-response speed must be >= 0 rpm.")
        if not isfinite(self.duration_s) or self.duration_s <= 0:
            raise EngineeringError(f"Time-response duration must be > 0 s; received {self.duration_s!r}.")
        if isinstance(self.samples, bool) or self.samples < 5 or self.samples > 200_000:
            raise EngineeringError(f"Time-response samples must be between 5 and 200000; received {self.samples!r}.")
        method = self.method.strip().casefold()
        if method not in {"default", "newmark"}:
            raise EngineeringError(f"Time-response method must be 'default' or 'newmark'; received {self.method!r}.")
        if method == "default" and abs(self.speed_end_rpm - self.speed_start_rpm) > 1e-12:
            raise EngineeringError("Variable-speed time response requires the ROSS Newmark method.")
        harmonic_active = abs(self.harmonic_x_n) > 0 or abs(self.harmonic_y_n) > 0
        if harmonic_active:
            if self.harmonic_position_mm is None or self.harmonic_position_mm < 0:
                raise EngineeringError("Active harmonic force requires a valid exact-node position in mm.")
            if not isfinite(self.harmonic_omega_rad_s) or self.harmonic_omega_rad_s < 0:
                raise EngineeringError("Harmonic angular frequency must be >= 0 rad/s.")
        if not (self.include_project_unbalance or self.include_gravity or harmonic_active):
            raise EngineeringError("Time response requires project unbalance, gravity or a harmonic force.")

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.speed_start_rpm), 9), round(float(self.speed_end_rpm), 9),
            round(float(self.duration_s), 12), int(self.samples), self.method.strip().casefold(),
            bool(self.include_project_unbalance), bool(self.include_gravity),
            None if self.harmonic_position_mm is None else round(float(self.harmonic_position_mm), 9),
            round(float(self.harmonic_omega_rad_s), 12), round(float(self.harmonic_x_n), 12),
            round(float(self.harmonic_y_n), 12), round(float(self.harmonic_phase_deg), 9),
        )


@dataclass(slots=True, frozen=True)
class HarmonicBalanceRequest:
    speed_rpm: float
    duration_s: float = 1.0
    samples: int = 1001
    n_harmonics: int = 3
    gravity: bool = False
    include_project_unbalance: bool = True
    direct_position_mm: float | None = None
    direct_magnitudes_n: tuple[float, ...] = ()
    direct_phases_deg: tuple[float, ...] = ()
    direct_harmonics: tuple[int, ...] = ()

    def validate(self) -> None:
        if not isfinite(self.speed_rpm) or self.speed_rpm < 0:
            raise EngineeringError(f"HBM speed must be >= 0 rpm; received {self.speed_rpm!r}.")
        if not isfinite(self.duration_s) or self.duration_s <= 0:
            raise EngineeringError("HBM duration must be > 0 s.")
        if isinstance(self.samples, bool) or self.samples < 9 or self.samples > 200_000:
            raise EngineeringError("HBM samples must be between 9 and 200000.")
        if isinstance(self.n_harmonics, bool) or self.n_harmonics < 1 or self.n_harmonics > 32:
            raise EngineeringError("HBM n_harmonics must be between 1 and 32.")
        lengths = (len(self.direct_magnitudes_n), len(self.direct_phases_deg), len(self.direct_harmonics))
        if len(set(lengths)) != 1:
            raise EngineeringError(
                "HBM direct magnitudes, phases and harmonic-order lists must have equal lengths; "
                f"received {lengths}."
            )
        if self.direct_magnitudes_n:
            if self.direct_position_mm is None or self.direct_position_mm < 0:
                raise EngineeringError("HBM direct harmonic forces require an exact-node position in mm.")
            if any(order < 1 or order > self.n_harmonics for order in self.direct_harmonics):
                raise EngineeringError("HBM direct harmonic orders must lie between 1 and n_harmonics.")
        if not self.include_project_unbalance and not self.direct_magnitudes_n:
            raise EngineeringError("HBM requires project unbalance or at least one direct harmonic force.")

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.speed_rpm), 9), round(float(self.duration_s), 12), int(self.samples),
            int(self.n_harmonics), bool(self.gravity), bool(self.include_project_unbalance),
            None if self.direct_position_mm is None else round(float(self.direct_position_mm), 9),
            tuple(round(float(v), 12) for v in self.direct_magnitudes_n),
            tuple(round(float(v), 9) for v in self.direct_phases_deg), tuple(int(v) for v in self.direct_harmonics),
        )


@dataclass(slots=True, frozen=True)
class UCSRequest:
    stiffness_start_exp: float = 6.0
    stiffness_end_exp: float = 11.0
    num: int = 20
    num_modes: int = 16
    synchronous: bool = False

    def validate(self) -> None:
        if not (isfinite(self.stiffness_start_exp) and isfinite(self.stiffness_end_exp)):
            raise EngineeringError("UCS stiffness exponents must be finite.")
        if self.stiffness_end_exp <= self.stiffness_start_exp:
            raise EngineeringError("UCS stiffness end exponent must be greater than start exponent.")
        if isinstance(self.num, bool) or self.num < 3 or self.num > 200:
            raise EngineeringError("UCS stiffness sample count must be between 3 and 200.")
        if isinstance(self.num_modes, bool) or self.num_modes < 4 or self.num_modes > 128:
            raise EngineeringError("UCS num_modes must be between 4 and 128.")
        if self.num_modes % 2:
            raise EngineeringError("UCS num_modes must be even.")

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.stiffness_start_exp), 9), round(float(self.stiffness_end_exp), 9),
            int(self.num), int(self.num_modes), bool(self.synchronous),
        )


@dataclass(slots=True, frozen=True)
class ClearanceRequest:
    speed_rpm: float
    band_percent: float = 10.0
    points: int = 21
    modes: tuple[int, ...] | None = None

    def validate(self) -> None:
        if not isfinite(self.speed_rpm) or self.speed_rpm <= 0:
            raise EngineeringError("Clearance operating speed must be > 0 rpm.")
        if not isfinite(self.band_percent) or self.band_percent < 0 or self.band_percent > 100:
            raise EngineeringError("Clearance frequency band must be between 0 and 100 percent.")
        if isinstance(self.points, bool) or self.points < 1 or self.points > 401:
            raise EngineeringError("Clearance frequency points must be between 1 and 401.")

    def cache_key(self) -> tuple[object, ...]:
        return (
            round(float(self.speed_rpm), 9), round(float(self.band_percent), 9), int(self.points),
            None if self.modes is None else tuple(int(v) for v in self.modes),
        )


class _ResultTiming:
    @property
    def total_elapsed_s(self) -> float:
        return float(sum(self.stage_elapsed_s.values()))


@dataclass(slots=True)
class FrequencyResponseAnalysisResult(_ResultTiming):
    project_name: str
    build: RossBuildResult
    request: FrequencyResponseRequest
    native: Any
    speed_rpm: np.ndarray
    input_node: int
    output_node: int
    input_global_dof: int
    output_global_dof: int
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class UnbalanceResponseAnalysisResult(_ResultTiming):
    project_name: str
    build: RossBuildResult
    request: UnbalanceResponseRequest
    native: Any
    speed_rpm: np.ndarray
    probes: tuple[NativeProbe, ...]
    unbalance_inputs: tuple[RossAppliedUnbalance, ...]
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class TimeResponseAnalysisResult(_ResultTiming):
    project_name: str
    build: RossBuildResult
    request: TimeResponseRequest
    native: Any
    time_s: np.ndarray
    speed_rpm: np.ndarray
    probes: tuple[NativeProbe, ...]
    force_peak_n: float
    unbalance_inputs: tuple[RossAppliedUnbalance, ...]
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class HarmonicBalanceAnalysisResult(_ResultTiming):
    project_name: str
    build: RossBuildResult
    request: HarmonicBalanceRequest
    native: Any
    probes: tuple[NativeProbe, ...]
    harmonic_forces: tuple[dict[str, Any], ...]
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class UCSAnalysisResult(_ResultTiming):
    project_name: str
    build: RossBuildResult
    request: UCSRequest
    native: Any
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ClearanceAnalysisResult(_ResultTiming):
    project_name: str
    build: RossBuildResult
    request: ClearanceRequest
    native: Any
    unbalance_inputs: tuple[RossAppliedUnbalance, ...]
    clearance_bearings: tuple[str, ...]
    audits: list[AnalysisAudit] = field(default_factory=list)
    stage_elapsed_s: dict[str, float] = field(default_factory=dict)


class _TimeFrequencyService:
    def __init__(self, backend: RossAnalysisBackend | None = None) -> None:
        self.backend = backend or RossAnalysisBackend()

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, state: str) -> None:
        if callback is not None:
            callback(stage, state)

    @staticmethod
    def _check_cancel(cancelled: CancelCallback | None, label: str) -> None:
        if cancelled is not None and cancelled():
            raise EngineeringError(f"{label} cancelled by user after the current ROSS stage.")

    def _stage(
        self,
        elapsed: dict[str, float],
        stage: str,
        fn: Callable[[], Any],
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCallback | None,
        label: str,
    ) -> Any:
        self._check_cancel(cancelled, label)
        self._emit(progress, stage, "running")
        start = perf_counter()
        try:
            value = fn()
        except Exception:
            elapsed[stage] = perf_counter() - start
            self._emit(progress, stage, "failed")
            raise
        elapsed[stage] = perf_counter() - start
        self._emit(progress, stage, "completed")
        return value

    def _build(
        self,
        project: RotorProject,
        elapsed: dict[str, float],
        *,
        progress: ProgressCallback | None,
        cancelled: CancelCallback | None,
        label: str,
    ) -> RossBuildResult:
        build = self._stage(
            elapsed,
            f"{label} · Strict Rotor",
            lambda: self.backend.build_rotor(project, strict=True),
            progress=progress,
            cancelled=cancelled,
            label=label,
        )
        if build.unresolved_positions_mm:
            raise EngineeringError(
                f"{label} requires exact ROSS nodes; unresolved positions: "
                + ", ".join(f"{v:g} mm" for v in build.unresolved_positions_mm)
            )
        return build

    @staticmethod
    def _bounded_grid(project: RotorProject, low: float, high: float, points: int) -> tuple[np.ndarray, list[AnalysisAudit]]:
        env_low, env_high, audits = AnalysisPipelineService._bearing_envelope_rpm(project)
        requested = (float(low), float(high))
        bounded_low = max(env_low, requested[0])
        bounded_high = min(env_high, requested[1])
        if bounded_high <= bounded_low:
            raise EngineeringError(
                f"Requested dynamic range {requested[0]:g}-{requested[1]:g} rpm lies outside the qualified "
                f"bearing K/C envelope {env_low:g}-{env_high:g} rpm."
            )
        if bounded_low != requested[0] or bounded_high != requested[1]:
            audits.append(AnalysisAudit(
                "TIME_FREQUENCY_BEARING_ENVELOPE",
                f"Requested range {requested[0]:g}-{requested[1]:g} rpm constrained to "
                f"{bounded_low:g}-{bounded_high:g} rpm by bearing K/C tables.",
                "warning",
            ))
        return np.linspace(bounded_low, bounded_high, int(points), dtype=float), audits

    @staticmethod
    def _node_for(build: RossBuildResult, position_mm: float, label: str) -> int:
        node = build.node_insertion_plan.node_for(float(position_mm))
        if node is None:
            raise EngineeringError(f"{label} at x={position_mm:g} mm has no exact ROSS node.")
        return int(node)

    @classmethod
    def _probes(cls, project: RotorProject, build: RossBuildResult) -> tuple[NativeProbe, ...]:
        probes: list[NativeProbe] = []
        for index, probe in enumerate(project.probes, 1):
            node = cls._node_for(build, probe.position_mm, f"Probe {probe.name or index}")
            probes.append(NativeProbe(node, float(probe.orientation_deg), probe.name or f"Probe {index}"))
        return tuple(probes)

    def _unbalance_inputs(
        self,
        project: RotorProject,
        build: RossBuildResult,
        *,
        names: Iterable[str] | None = None,
    ) -> list[RossUnbalanceInput]:
        selected = None if names is None else {str(name) for name in names}
        inputs: list[RossUnbalanceInput] = []
        for load in project.loads:
            if load.kind.strip().casefold() != "unbalance":
                continue
            if selected is not None and load.name not in selected:
                continue
            node = self._node_for(build, load.position_mm, f"Unbalance {load.name!r}")
            source_unit = str(load.metadata.get("source_unit", load.metadata.get("magnitude_unit", "kg*m")))
            inputs.append(RossUnbalanceInput(
                node=node,
                raw_magnitude=float(load.magnitude),
                source_unit=source_unit,
                phase_rad=radians(float(load.phase_deg)),
            ))
        if not inputs:
            raise EngineeringError("This analysis requires at least one project load with kind='unbalance'.")
        return inputs

    def _applied_unbalance(self, inputs: Iterable[RossUnbalanceInput]) -> tuple[RossAppliedUnbalance, ...]:
        return tuple(
            RossAppliedUnbalance(
                node=item.node,
                raw_magnitude=item.raw_magnitude,
                source_unit=item.source_unit,
                magnitude_kg_m=self.backend.normalize_unbalance_kg_m(item.raw_magnitude, item.source_unit),
                phase_rad=item.phase_rad,
            )
            for item in inputs
        )


class FrequencyResponseService(_TimeFrequencyService):
    """Independent native ``Rotor.run_freq_response()`` transaction."""

    def run(self, project: RotorProject, request: FrequencyResponseRequest, *, progress=None, cancelled=None):
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        speed_rpm, audits = self._bounded_grid(project, request.min_rpm, request.max_rpm, request.points)
        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Frequency Response")
        input_node = self._node_for(build, request.input_position_mm, "Frequency-response input")
        output_node = self._node_for(build, request.output_position_mm, "Frequency-response output")
        ndof = int(build.rotor.number_dof)
        inp = input_node * ndof + int(request.input_dof)
        out = output_node * ndof + int(request.output_dof)
        native = self._stage(
            elapsed,
            "Frequency Response · Solve",
            lambda: self.backend.run_frequency_response_build(
                build, speed_rpm * 2.0 * pi / 60.0, modes=request.modes, free_free=request.free_free
            ),
            progress=progress,
            cancelled=cancelled,
            label="Frequency Response",
        )
        for name in ("freq_resp", "velc_resp", "accl_resp"):
            if not np.all(np.isfinite(np.abs(np.asarray(getattr(native, name))))):
                raise EngineeringError(f"ROSS {name} contains non-finite values.")
        audits.append(AnalysisAudit(
            "ROSS_FREQUENCY_RESPONSE_NATIVE_021",
            "Native Rotor.run_freq_response() retained with displacement, velocity and acceleration FRFs; plot methods do not re-solve.",
            "info",
        ))
        return FrequencyResponseAnalysisResult(
            project.name, build, request, native, speed_rpm, input_node, output_node, inp, out, audits, elapsed
        )


class UnbalanceResponseService(_TimeFrequencyService):
    """Independent native ``Rotor.run_unbalance_response()`` transaction."""

    def run(self, project: RotorProject, request: UnbalanceResponseRequest, *, progress=None, cancelled=None):
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        speed_rpm, audits = self._bounded_grid(project, request.min_rpm, request.max_rpm, request.points)
        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Unbalance Response")
        inputs = self._unbalance_inputs(project, build, names=request.load_names)
        run = self._stage(
            elapsed,
            "Unbalance Response · Solve",
            lambda: self.backend.run_unbalance_build(build, inputs, speed_rpm.tolist()),
            progress=progress,
            cancelled=cancelled,
            label="Unbalance Response",
        )
        if not np.all(np.isfinite(np.abs(np.asarray(run.response.forced_resp)))):
            raise EngineeringError("ROSS unbalance forced response contains non-finite values.")
        audits.append(AnalysisAudit(
            "ROSS_UNBALANCE_NATIVE_021",
            "Native ForcedResponseResults retained from Rotor.run_unbalance_response(), including Bode, polar, deflected-shape and bending-moment outputs.",
            "info",
        ))
        return UnbalanceResponseAnalysisResult(
            project.name, build, request, run.response, speed_rpm, self._probes(project, build),
            run.applied_inputs, audits, elapsed
        )


class TimeResponseService(_TimeFrequencyService):
    """Independent native ``Rotor.run_time_response()`` transaction."""

    def run(self, project: RotorProject, request: TimeResponseRequest, *, progress=None, cancelled=None):
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Time Response")
        t = np.linspace(0.0, float(request.duration_s), int(request.samples), dtype=float)
        speed_profile_rpm = np.linspace(float(request.speed_start_rpm), float(request.speed_end_rpm), len(t))
        speed_rad_s_array = speed_profile_rpm * 2.0 * pi / 60.0
        speed_arg: float | np.ndarray = (
            float(speed_rad_s_array[0]) if np.allclose(speed_rad_s_array, speed_rad_s_array[0]) else speed_rad_s_array
        )

        force = np.zeros((len(t), int(build.rotor.ndof)), dtype=float)
        applied: tuple[RossAppliedUnbalance, ...] = ()
        if request.include_project_unbalance:
            raw = self._unbalance_inputs(project, build)
            applied = self._applied_unbalance(raw)
            funb = build.rotor.unbalance_force_over_time(
                node=[item.node for item in applied],
                magnitude=[item.magnitude_kg_m for item in applied],
                phase=[item.phase_rad for item in applied],
                omega=speed_arg,
                t=t,
            )
            force += np.asarray(funb, dtype=float).T

        if request.include_gravity:
            weight = np.asarray(build.rotor.gravitational_force(direction="y"), dtype=float)
            force += weight[np.newaxis, :]

        if abs(request.harmonic_x_n) > 0 or abs(request.harmonic_y_n) > 0:
            assert request.harmonic_position_mm is not None
            node = self._node_for(build, request.harmonic_position_mm, "Harmonic force")
            ndof = int(build.rotor.number_dof)
            phase = radians(float(request.harmonic_phase_deg))
            omega = float(request.harmonic_omega_rad_s)
            force[:, node * ndof + 0] += float(request.harmonic_x_n) * np.cos(omega * t + phase)
            force[:, node * ndof + 1] += float(request.harmonic_y_n) * np.sin(omega * t + phase)

        native = self._stage(
            elapsed,
            "Time Response · Solve",
            lambda: self.backend.run_time_response_build(
                build, speed_arg, force, t, method=request.method.strip().casefold()
            ),
            progress=progress,
            cancelled=cancelled,
            label="Time Response",
        )
        if not np.all(np.isfinite(np.asarray(native.yout, dtype=float))):
            raise EngineeringError("ROSS time response contains non-finite displacements.")
        audits = [AnalysisAudit(
            "ROSS_TIME_RESPONSE_NATIVE_021",
            f"Native Rotor.run_time_response(method={request.method!r}) retained; plot_1d/plot_2d/plot_3d/plot_dfft are post-processing only.",
            "info",
        )]
        return TimeResponseAnalysisResult(
            project.name, build, request, native, t, speed_profile_rpm, self._probes(project, build),
            float(np.max(np.abs(force))) if force.size else 0.0, applied, audits, elapsed
        )


class HarmonicBalanceService(_TimeFrequencyService):
    """Independent native ``Rotor.run_harmonic_balance_response()`` transaction."""

    def run(self, project: RotorProject, request: HarmonicBalanceRequest, *, progress=None, cancelled=None):
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Harmonic Balance")
        speed_rad_s = float(request.speed_rpm) * 2.0 * pi / 60.0
        t = np.linspace(0.0, float(request.duration_s), int(request.samples), dtype=float)
        forces: list[dict[str, Any]] = []

        if request.direct_magnitudes_n:
            assert request.direct_position_mm is not None
            node = self._node_for(build, request.direct_position_mm, "HBM direct force")
            forces.append({
                "node": node,
                "magnitudes": [float(v) for v in request.direct_magnitudes_n],
                "phases": [radians(float(v)) for v in request.direct_phases_deg],
                "harmonics": [int(v) for v in request.direct_harmonics],
            })

        if request.include_project_unbalance:
            raw = self._unbalance_inputs(project, build)
            applied = self._applied_unbalance(raw)
            for item in applied:
                forces.append({
                    "node": item.node,
                    "magnitudes": [item.magnitude_kg_m * speed_rad_s**2],
                    "phases": [item.phase_rad],
                    "harmonics": [1],
                })

        native = self._stage(
            elapsed,
            "Harmonic Balance · Solve",
            lambda: self.backend.run_harmonic_balance_build(
                build,
                speed_rad_s=speed_rad_s,
                time_s=t,
                harmonic_forces=forces,
                gravity=request.gravity,
                n_harmonics=request.n_harmonics,
            ),
            progress=progress,
            cancelled=cancelled,
            label="Harmonic Balance",
        )
        audits = [AnalysisAudit(
            "ROSS_HBM_NATIVE_021",
            "Native HarmonicBalanceResults retained from Rotor.run_harmonic_balance_response(); frequency-domain, deflected-shape and reconstructed time/DFFT outputs share the same solve.",
            "info",
        )]
        return HarmonicBalanceAnalysisResult(
            project.name, build, request, native, self._probes(project, build), tuple(forces), audits, elapsed
        )


class UCSService(_TimeFrequencyService):
    """Independent native ``Rotor.run_ucs()`` transaction."""

    def run(self, project: RotorProject, request: UCSRequest, *, progress=None, cancelled=None):
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="UCS")
        native = self._stage(
            elapsed,
            "UCS · Solve",
            lambda: self.backend.run_ucs_build(
                build,
                stiffness_range=(request.stiffness_start_exp, request.stiffness_end_exp),
                num_modes=request.num_modes,
                num=request.num,
                synchronous=request.synchronous,
            ),
            progress=progress,
            cancelled=cancelled,
            label="UCS",
        )
        audits = [AnalysisAudit(
            "ROSS_UCS_NATIVE_021",
            "Native UCSResults retained from Rotor.run_ucs(), including map and critical-point 2D/3D mode-shape outputs.",
            "info",
        )]
        return UCSAnalysisResult(project.name, build, request, native, audits, elapsed)


class ClearanceService(_TimeFrequencyService):
    """Native ROSS 2.3 clearance analysis with an explicit bearing-clearance contract."""

    def _attach_clearances(self, project: RotorProject, build: RossBuildResult) -> tuple[str, ...]:
        attached: list[str] = []
        for spec in project.bearings:
            raw = spec.metadata.get("radial_clearance_m")
            if raw is None:
                continue
            try:
                clearance = float(raw)
            except (TypeError, ValueError) as exc:
                raise EngineeringError(f"Bearing {spec.name!r} radial_clearance_m is not numeric: {raw!r}.") from exc
            if not isfinite(clearance) or clearance <= 0:
                raise EngineeringError(f"Bearing {spec.name!r} radial_clearance_m must be positive; received {raw!r}.")
            node = self._node_for(build, spec.position_mm, f"Bearing {spec.name!r}")
            candidates = [element for element in build.rotor.bearing_elements if int(element.n) == node]
            if not candidates:
                raise EngineeringError(f"Bearing {spec.name!r} has no matching ROSS bearing element at node {node}.")
            setattr(candidates[0], "radial_clearance", clearance)
            attached.append(spec.name)
        if not attached:
            raise EngineeringError(
                "Clearance Analysis requires radial_clearance_m on at least one Bearing Studio model. "
                "Define bearing radial clearance before running this native ROSS analysis."
            )
        return tuple(attached)

    def run(self, project: RotorProject, request: ClearanceRequest, *, progress=None, cancelled=None):
        project.validate()
        request.validate()
        elapsed: dict[str, float] = {}
        build = self._build(project, elapsed, progress=progress, cancelled=cancelled, label="Clearance")
        if build.support_link_nodes:
            raise EngineeringError(
                "Native ROSS 2.3 run_clearance_analysis() iterates every BearingElement, including auxiliary "
                "ground-support bearings. Clearance Analysis is therefore blocked while flexible support links "
                "are present so ROSS Studio does not report non-physical support clearances."
            )
        clearance_bearings = self._attach_clearances(project, build)
        raw = self._unbalance_inputs(project, build)
        applied = self._applied_unbalance(raw)
        speed_rad_s = float(request.speed_rpm) * 2.0 * pi / 60.0
        if request.points == 1 or request.band_percent == 0:
            frequency = np.asarray([speed_rad_s], dtype=float)
        else:
            frac = float(request.band_percent) / 100.0
            frequency = np.linspace(speed_rad_s * (1.0 - frac), speed_rad_s * (1.0 + frac), int(request.points))
        native = self._stage(
            elapsed,
            "Clearance · Solve",
            lambda: self.backend.run_clearance_build(
                build,
                speed_rad_s=speed_rad_s,
                nodes=[item.node for item in applied],
                magnitudes_kg_m=[item.magnitude_kg_m for item in applied],
                phases_rad=[item.phase_rad for item in applied],
                frequency_rad_s=frequency,
                modes=request.modes,
            ),
            progress=progress,
            cancelled=cancelled,
            label="Clearance",
        )
        clearance_values = np.asarray(native.clearance, dtype=float)
        if not np.all(np.isfinite(clearance_values)):
            raise EngineeringError(
                "ROSS clearance result contains non-finite clearance values. Define radial_clearance_m for every "
                "physical bearing participating in the native clearance analysis."
            )
        audits = [AnalysisAudit(
            "ROSS_CLEARANCE_NATIVE_021",
            "Native Rotor.run_clearance_analysis() retained. Bearing radial_clearance_m is attached explicitly to the corresponding ROSS bearing element; no clearance is inferred.",
            "info",
        )]
        return ClearanceAnalysisResult(
            project.name, build, request, native, applied, clearance_bearings, audits, elapsed
        )


__all__ = [
    "ClearanceAnalysisResult", "ClearanceRequest", "ClearanceService",
    "FrequencyResponseAnalysisResult", "FrequencyResponseRequest", "FrequencyResponseService",
    "HarmonicBalanceAnalysisResult", "HarmonicBalanceRequest", "HarmonicBalanceService",
    "NativeProbe", "TimeResponseAnalysisResult", "TimeResponseRequest", "TimeResponseService",
    "UCSAnalysisResult", "UCSRequest", "UCSService",
    "UnbalanceResponseAnalysisResult", "UnbalanceResponseRequest", "UnbalanceResponseService",
]
