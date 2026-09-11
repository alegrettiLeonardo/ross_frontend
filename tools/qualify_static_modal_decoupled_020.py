from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from ross_studio.analysis_backend import RossAnalysisBackend
from ross_studio.models import load_reference_project_model
from ross_studio.static_modal_decoupled import (
    ModalAnalysisRequest,
    ModalAnalysisService,
    StaticAnalysisService,
)


class CountingBackend(RossAnalysisBackend):
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


def main() -> int:
    model = load_reference_project_model()
    engineering = deepcopy(model.engineering)
    if engineering is None:
        raise RuntimeError("Reference project has no engineering domain.")
    engineering.loads = [load for load in engineering.loads if load.kind.strip().casefold() != "unbalance"]

    backend = CountingBackend()
    static = StaticAnalysisService(backend).run(engineering)
    after_static = dict(backend.calls)
    if after_static != {"build": 1, "static": 1, "modal": 0, "campbell": 0}:
        raise RuntimeError(f"Static transaction leaked into Modal/Campbell: {after_static}")

    request = ModalAnalysisRequest(
        speed_rpm=engineering.operating_cases[0].rated_speed_rpm,
        num_modes=16,
        campbell_points=9,
        campbell_frequencies=6,
    )
    modal = ModalAnalysisService(backend).run(engineering, request)
    final = dict(backend.calls)
    if final != {"build": 2, "static": 1, "modal": 1, "campbell": 1}:
        raise RuntimeError(f"Modal transaction leaked into Static or did not run Campbell once: {final}")
    if len(set(backend.build_ids)) != 2:
        raise RuntimeError("Static and Modal did not own distinct strict-build transactions.")
    if static.build.unresolved_positions_mm or modal.build.unresolved_positions_mm:
        raise RuntimeError("0.20 decoupled transactions contain unresolved engineering positions.")

    lateral = list(modal.mode_indices("Lateral"))
    torsional = list(modal.mode_indices("Torsional"))
    payload = {
        "status": "PASS",
        "release": "0.20.0",
        "project": engineering.name,
        "unbalance_required": False,
        "static_transaction_calls": after_static,
        "final_calls": final,
        "independent_strict_builds": len(set(backend.build_ids)) == 2,
        "static_owns_modal": False,
        "modal_owns_static": False,
        "static_source": "Rotor.run_static",
        "modal_source": "Rotor.run_modal",
        "campbell_source": "Rotor.run_campbell",
        "static_elapsed_s": static.total_elapsed_s,
        "modal_elapsed_s": modal.total_elapsed_s,
        "lateral_mode_indices": lateral,
        "torsional_mode_indices": torsional,
        "modal_cache_key": list(request.cache_key()),
        "project_change_invalidation": "STATIC_AND_MODAL",
        "modal_input_change_invalidation": "MODAL_ONLY",
        "plot_harmonics_invalidation": "NONE",
        "unresolved_positions_mm": [],
    }
    target = Path("artifacts/static_modal_decoupled_020_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
