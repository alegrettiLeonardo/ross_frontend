from math import isclose, pi

from ross_frontend.backends.ross.builder import RossModelBuilder
from ross_frontend.domain import (
    BallBearingSpec,
    CoefficientBearingSpec,
    MaterialSpec,
    PlainJournalBearingSpec,
    RotorProject,
    ShaftSectionSpec,
    TiltingPadBearingSpec,
)
from fakes import FakeRoss


def project_with_cone():
    return RotorProject(
        reference="cone",
        materials=[MaterialSpec(name="AISI 4140")],
        shaft=[
            ShaftSectionSpec(
                length_mm=1000,
                outer_diameter_left_mm=100,
                outer_diameter_right_mm=200,
                material="AISI 4140",
            )
        ],
        bearings=[
            CoefficientBearingSpec(
                position_mm=250,
                kxx=1e6,
                kzz=2e6,
                kxz=3e5,
                kzx=4e5,
                cxx=100,
                czz=200,
                cxz=30,
                czx=40,
            )
        ],
    )


def test_builder_splits_conical_shaft_at_component_and_interpolates_geometry():
    build = RossModelBuilder(FakeRoss()).build(project_with_cone())
    assert build.node_by_position_mm == {0.0: 0, 250.0: 1, 1000.0: 2}
    assert len(build.shaft_elements) == 2

    first = build.shaft_elements[0].kwargs
    second = build.shaft_elements[1].kwargs
    assert isclose(first["odl"], 0.100)
    assert isclose(first["odr"], 0.125)
    assert isclose(second["odl"], 0.125)
    assert isclose(second["odr"], 0.200)
    assert first["n"] == 0 and second["n"] == 1
    assert first["material"].kwargs["name"] == "AISI_4140"


def test_coefficient_bearing_uses_xy_fields_and_never_ross_axial_kzz():
    build = RossModelBuilder(FakeRoss()).build(project_with_cone())
    bearing = build.bearing_elements[0].kwargs
    assert bearing["n"] == 1
    assert bearing["kxx"] == 1e6
    assert bearing["kyy"] == 2e6
    assert bearing["kxy"] == 3e5
    assert bearing["kyx"] == 4e5
    assert bearing["cyy"] == 200
    assert "kzz" not in bearing and "czz" not in bearing


def test_ball_plain_journal_and_tilting_pad_parameters_are_converted_to_si():
    project = RotorProject(
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000, 100)],
        bearings=[
            BallBearingSpec(100, 8, 12.0, 500.0, 30.0),
            PlainJournalBearingSpec(
                position_mm=500,
                pad_axial_length_mm=100,
                journal_diameter_mm=80,
                radial_clearance_mm=0.1,
                n_pads=2,
                pad_arc_deg=176,
                oil_supply_temperature_c=50,
                frequency_rpm=[900, 1800],
                load_y_n=-1000,
                oil_flow_l_min=30,
            ),
            TiltingPadBearingSpec(
                position_mm=900,
                journal_diameter_mm=80,
                radial_clearance_mm=0.1,
                pad_axial_length_mm=60,
                pad_thickness_mm=20,
                pad_arc_deg=60,
                pivot_angle_deg=[0, 72, 144, 216, 288],
                frequency_rpm=[900],
                oil_supply_temperature_c=45,
                oil_flow_l_min=20,
            ),
        ],
    )
    build = RossModelBuilder(FakeRoss()).build(project)
    ball, plain, tilt = [x.kwargs for x in build.bearing_elements]
    assert isclose(ball["d_balls"], 0.012)
    assert isclose(ball["alpha"], pi / 6)
    assert isclose(plain["journal_diameter"], 0.08)
    assert isclose(plain["radial_clearance"], 1e-4)
    assert isclose(plain["oil_supply_temperature"], 323.15)
    assert isclose(plain["oil_flow_v"], 30 / 1000 / 60)
    assert isclose(tilt["pad_arc"], pi / 3)
    assert isclose(tilt["oil_flow_v"], 20 / 1000 / 60)
