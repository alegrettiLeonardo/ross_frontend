import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ross_frontend.domain import BearingKind
from ross_frontend.ui.main_window import RossStudioWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_approved_bearing_selector_builds_all_six_domain_types(app):
    window = RossStudioWindow()
    page = window.bearing_page

    page._type_changed("coefficient")
    coefficient = page._build_spec()
    assert coefficient.kind == BearingKind.COEFFICIENT
    assert coefficient.frequency_rpm == [500.0, 1000.0, 2000.0, 4000.0, 6000.0, 8000.0, 10000.0]
    assert coefficient.kxz[0] == pytest.approx(-0.32e7)
    assert coefficient.kzz[0] == pytest.approx(1.10e7)

    page._type_changed("ball")
    ball = page._build_spec()
    assert ball.kind == BearingKind.BALL
    assert ball.n_balls == 8
    assert ball.ball_diameter_mm == pytest.approx(12.0)
    assert ball.static_load_n == pytest.approx(5000.0)

    page._type_changed("roller")
    roller = page._build_spec()
    assert roller.kind == BearingKind.ROLLER
    assert roller.n_rollers == 8
    assert roller.roller_length_mm == pytest.approx(20.0)
    assert roller.static_load_n == pytest.approx(5000.0)

    page._type_changed("cylindrical")
    cylindrical = page._build_spec()
    assert cylindrical.kind == BearingKind.CYLINDRICAL
    assert cylindrical.journal_diameter_mm == pytest.approx(100.0)
    assert cylindrical.bearing_length_mm == pytest.approx(80.0)
    assert cylindrical.radial_clearance_mm == pytest.approx(0.10)
    assert cylindrical.oil_viscosity_pa_s == pytest.approx(0.03)

    page._type_changed("plain")
    plain = page._build_spec()
    assert plain.kind == BearingKind.PLAIN_JOURNAL
    assert plain.n_pads == 2
    assert plain.pad_arc_deg == pytest.approx(176.0)
    assert plain.equilibrium_type == "match_load"

    page._type_changed("tilting")
    tilting = page._build_spec()
    assert tilting.kind == BearingKind.TILTING_PAD
    assert len(tilting.pivot_angle_deg) == 5
    assert tilting.pivot_angle_deg[0] == pytest.approx(18.0)
    assert tilting.equilibrium_type == "match_load"

    window.close()
