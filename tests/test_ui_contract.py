from pathlib import Path

from ross_studio.models import BearingModel, CAMPBELL_MODES, load_reference_project_model
from ross_studio.theme import COLORS


def test_approved_palette_contract() -> None:
    assert COLORS.title_bar == "#173f5f"
    assert COLORS.sidebar == "#1f3f5d"
    assert COLORS.active == "#2186e5"
    assert COLORS.background == "#f3f8fc"
    assert COLORS.surface == "#ffffff"
    assert COLORS.success == "#1ba85b"
    assert COLORS.console_bg == "#09141f"


def test_rotor_screen_contract_uses_op_w60_reference() -> None:
    project = load_reference_project_model()
    assert project.name == "OP-W60-500-60Hz-IC611-P3"
    assert project.line == "W60"
    assert project.frame == "500"
    assert project.poles == 2
    assert project.speed_rpm == 3600
    assert project.speed_max_rpm == 4500
    assert project.total_length_mm == 2555.2
    assert project.physical_sections == 15
    assert project.ross_shaft_elements == 27
    assert project.disks == 4
    assert project.bearings == 2
    assert project.supports == 2


def test_bearing_screen_contract_uses_imported_kc_table() -> None:
    project = load_reference_project_model()
    assert project.engineering is not None
    bearing = BearingModel.from_project(project.engineering)
    assert bearing.name == "dianteiro -quente"
    assert bearing.bearing_type == "Coefficient K/C"
    assert bearing.ross_class == "BearingElement"
    assert bearing.group == "General / Parametric"
    assert len(bearing.coefficients) == 11
    assert bearing.coefficients[0].rpm == 900
    assert bearing.coefficients[-1].rpm == 5000


def test_campbell_screen_contract_values() -> None:
    assert len(CAMPBELL_MODES) == 12
    assert CAMPBELL_MODES[1].speed_rpm == 2840
    assert CAMPBELL_MODES[5].speed_rpm == 6520


def test_required_screen_sources_exist() -> None:
    root = Path(__file__).parents[1] / "src" / "ross_studio"
    required = [
        root / "pages" / "rotor_model.py",
        root / "pages" / "bearing_groups.py",
        root / "pages" / "bearing_studio.py",
        root / "pages" / "results.py",
        root / "solver_console.py",
        root / "domain.py",
        root / "services.py",
        root / "topology.py",
        root / "ross_backend.py",
    ]
    assert all(path.is_file() for path in required)


def test_wgm20_is_not_a_production_default_anymore() -> None:
    root = Path(__file__).parents[1] / "src" / "ross_studio"
    offenders = []
    for path in root.rglob("*.py"):
        if "WGM20" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(root))
    assert offenders == []
