import json

from ross_frontend.backends.ross.backend import RossBackend
from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.domain import AnalysisRequest, CoefficientBearingSpec, MaterialSpec, RotorProject, ShaftSectionSpec
from fakes import FakeRoss


def test_backend_runs_initial_analysis_set_and_writes_audit(tmp_path):
    project = RotorProject(
        reference="WGM20 test",
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000, 100)],
        bearings=[CoefficientBearingSpec(0, 1e6, 1e6, 100, 100)],
        analyses=AnalysisRequest(
            modal=True,
            critical_speed=True,
            campbell=True,
            static=True,
            modal_speed_rpm=1800,
            campbell_initial_rpm=0,
            campbell_final_rpm=1000,
            campbell_step_rpm=500,
            modes=2,
        ),
    )
    messages = []
    backend = RossBackend(RossModelBuilder(FakeRoss()), run_root=tmp_path)
    result = backend.run(project, messages.append)

    assert result.ok
    assert result.backend == "ross"
    assert set(result.data) == {"model", "static", "modal", "critical_speed", "campbell"}
    assert set(result.sections) == {
        "ross_model.json",
        "static.json",
        "modal.json",
        "critical_speed.json",
        "campbell.json",
    }
    assert [p.rpm for p in result.critical_speeds] == [600.0, 1200.0]
    assert result.run_dir.name.endswith("WGM20_test")
    assert (result.run_dir / "project.json").is_file()
    assert (result.run_dir / "model.json").is_file()
    payload = json.loads((result.run_dir / "results.json").read_text())
    assert payload["backend_version"] == "2.3.0-test"
    assert any("Campbell" in m for m in messages)
    assert messages[-1] == "ROSS analysis completed."
