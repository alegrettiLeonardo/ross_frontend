import json

import numpy as np
import pytest

from ross_frontend.backends.ross.backend import RossBackend
from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.domain import (
    AnalysisRequest,
    MaterialSpec,
    RotorProject,
    ShaftSectionSpec,
    UMPRegionSpec,
    UmpFormulation,
)
from fakes import FakeRoss


class CapturingBuilder(RossModelBuilder):
    def build(self, project):
        self.last_build = super().build(project)
        return self.last_build


def test_backend_writes_ump_matrices_and_keeps_static_on_base_rotor(tmp_path):
    project = RotorProject(
        reference="ump-audit",
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000.0, 100.0)],
        ump_regions=[
            UMPRegionSpec(
                200.0,
                800.0,
                2.0e6,
                formulation=UmpFormulation.PHYSICAL_CORRECTED,
                source_unit="N/m²",
            )
        ],
        analyses=AnalysisRequest(
            static=True,
            modal=False,
            critical_speed=False,
            campbell=False,
            modal_speed_rpm=1800.0,
        ),
    )
    builder = CapturingBuilder(FakeRoss())
    result = RossBackend(builder, run_root=tmp_path).run(project)
    build = builder.last_build

    assert result.ok
    assert build.base_rotor is not build.rotor
    assert ("static", {}) in build.base_rotor.calls
    assert ("static", {}) not in build.rotor.calls
    assert "ump" in result.data
    assert "ump_audit.json" in result.sections

    audit = json.loads((result.run_dir / "ump_audit.json").read_text())
    assert audit["matrix_identity"] == "K_effective = K_without_ump - K_ump"
    assert audit["matrix_identity_max_abs_error"] == pytest.approx(0.0)
    assert audit["static_and_stiffness_map_rotor"] == "base_rotor_without_ump"

    k0 = np.load(result.run_dir / "K_without_ump.npz")["matrix"]
    ku = np.load(result.run_dir / "K_ump.npz")["matrix"]
    ke = np.load(result.run_dir / "K_effective.npz")["matrix"]
    assert np.linalg.norm(ku) > 0.0
    assert np.allclose(ke, k0 - ku)
