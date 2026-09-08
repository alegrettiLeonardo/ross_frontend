from pathlib import Path

from ross_studio.models import BearingModel, ProjectModel, CAMPBELL_MODES
from ross_studio.theme import COLORS


def test_approved_palette_contract() -> None:
    assert COLORS.title_bar == "#173f5f"
    assert COLORS.sidebar == "#1f3f5d"
    assert COLORS.active == "#2186e5"
    assert COLORS.background == "#f3f8fc"
    assert COLORS.surface == "#ffffff"
    assert COLORS.success == "#1ba85b"
    assert COLORS.console_bg == "#09141f"


def test_rotor_screen_contract_values() -> None:
    project = ProjectModel()
    assert project.name == "WGM20"
    assert project.description == "Wind generator main rotor\n(20 MW class)"
    assert project.speed_rpm == 1800
    assert project.material == "Steel (AISI 4140)"
    assert project.total_mass_kg == 286.4
    assert project.total_length_mm == 1200
    assert [s.length_mm for s in project.segments] == [200, 150, 250, 250, 200, 150]
    assert len(project.segments) == 6


def test_bearing_screen_contract_values() -> None:
    bearing = BearingModel()
    assert bearing.name == "DE Journal Bearing"
    assert bearing.bearing_type == "Tilting Pad"
    assert bearing.number_of_pads == 5
    assert bearing.preload == 0.50
    assert bearing.radial_clearance_mm == 0.10
    assert bearing.lubricant_grade == "ISO VG 32"
    assert bearing.thermal_model == "Energy Equation"
    assert len(bearing.coefficients) == 7
    assert bearing.coefficients[4].rpm == 6000


def test_campbell_screen_contract_values() -> None:
    assert len(CAMPBELL_MODES) == 12
    assert CAMPBELL_MODES[1].speed_rpm == 2840
    assert CAMPBELL_MODES[5].speed_rpm == 6520


def test_required_screen_sources_exist() -> None:
    root = Path(__file__).parents[1] / "src" / "ross_studio"
    required = [
        root / "pages" / "rotor_model.py",
        root / "pages" / "bearing_studio.py",
        root / "pages" / "results.py",
        root / "solver_console.py",
    ]
    assert all(path.is_file() for path in required)
