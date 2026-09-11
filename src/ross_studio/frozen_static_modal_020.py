from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from .analysis_backend import RossAnalysisBackend
from .models import load_reference_project_model
from .static_modal_decoupled import ModalAnalysisRequest, ModalAnalysisService, StaticAnalysisService


class _CountingBackend(RossAnalysisBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = {"build": 0, "static": 0, "modal": 0, "campbell": 0}
        self.build_ids: list[int] = []

    def build_rotor(self, project, *, strict=True):
        self.calls["build"] += 1
        build = super().build_rotor(project, strict=strict)
        self.build_ids.append(id(build))
        return build

    def run_static_build(self, build):
        self.calls["static"] += 1
        return super().run_static_build(build)

    def run_modal_build(self, build, speed_rpm, *, num_modes=12):
        self.calls["modal"] += 1
        return super().run_modal_build(build, speed_rpm, num_modes=num_modes)

    def run_campbell_build(self, build, speeds_rpm, *, frequencies=6):
        self.calls["campbell"] += 1
        return super().run_campbell_build(build, speeds_rpm, frequencies=frequencies)


@dataclass(slots=True, frozen=True)
class FrozenStaticModal020Result:
    status: str
    project: str
    static_after_calls: dict[str, int]
    final_calls: dict[str, int]
    independent_strict_builds: bool
    static_unresolved_positions_mm: tuple[float, ...]
    modal_unresolved_positions_mm: tuple[float, ...]
    modal_mode_count: int
    lateral_mode_count: int
    torsional_mode_count: int
    static_elapsed_s: float
    modal_elapsed_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_frozen_static_modal_020_test() -> FrozenStaticModal020Result:
    model = load_reference_project_model()
    engineering = deepcopy(model.engineering)
    if engineering is None:
        raise RuntimeError("Reference engineering domain was not packaged.")
    engineering.loads = [load for load in engineering.loads if load.kind.strip().casefold() != "unbalance"]

    backend = _CountingBackend()
    static = StaticAnalysisService(backend).run(engineering)
    after_static = dict(backend.calls)
    expected_static = {"build": 1, "static": 1, "modal": 0, "campbell": 0}
    if after_static != expected_static:
        raise RuntimeError(f"Frozen Static transaction leaked calls: expected {expected_static}, received {after_static}.")

    modal = ModalAnalysisService(backend).run(
        engineering,
        ModalAnalysisRequest(
            speed_rpm=engineering.operating_cases[0].rated_speed_rpm,
            num_modes=16,
            campbell_points=7,
            campbell_frequencies=6,
        ),
    )
    final = dict(backend.calls)
    expected_final = {"build": 2, "static": 1, "modal": 1, "campbell": 1}
    if final != expected_final:
        raise RuntimeError(f"Frozen Modal transaction leaked calls: expected {expected_final}, received {final}.")
    independent = len(set(backend.build_ids)) == 2
    if not independent:
        raise RuntimeError("Frozen Static and Modal transactions did not own distinct strict Rotor builds.")
    if static.build.unresolved_positions_mm or modal.build.unresolved_positions_mm:
        raise RuntimeError("Frozen decoupled Static/Modal runtime contains unresolved positions.")

    return FrozenStaticModal020Result(
        status="PASS",
        project=engineering.name,
        static_after_calls=after_static,
        final_calls=final,
        independent_strict_builds=independent,
        static_unresolved_positions_mm=tuple(float(v) for v in static.build.unresolved_positions_mm),
        modal_unresolved_positions_mm=tuple(float(v) for v in modal.build.unresolved_positions_mm),
        modal_mode_count=len(modal.modal_modes),
        lateral_mode_count=len(modal.mode_indices("Lateral")),
        torsional_mode_count=len(modal.mode_indices("Torsional")),
        static_elapsed_s=static.total_elapsed_s,
        modal_elapsed_s=modal.total_elapsed_s,
    )


__all__ = ["FrozenStaticModal020Result", "run_frozen_static_modal_020_test"]
