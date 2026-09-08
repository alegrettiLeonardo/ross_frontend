from types import SimpleNamespace

import pytest

from ross_frontend.backends.ross.bearing_calculator import RossBearingCalculator
from ross_frontend.domain import CoefficientBearingSpec, PlainJournalBearingSpec


class FakeBuilder:
    @staticmethod
    def _p(value):
        return round(float(value), 9)

    def _build_bearing(self, spec, node_map):
        assert node_map[self._p(spec.position_mm)] == 0
        if isinstance(spec, CoefficientBearingSpec):
            return SimpleNamespace(
                frequency=[10.0, 20.0],
                kxx=[1.0, 2.0], kxy=[3.0, 4.0], kyx=[5.0, 6.0], kyy=[7.0, 8.0],
                cxx=[9.0, 10.0], cxy=[11.0, 12.0], cyx=[13.0, 14.0], cyy=[15.0, 16.0],
            )
        native = SimpleNamespace(
            frequency=[100.0],
            kxx=[1e7], kxy=[-2e6], kyx=[3e6], kyy=[1.1e7],
            cxx=[1e5], cxy=[-2e4], cyx=[3e4], cyy=[1.1e5],
            outputs=[{
                "eccentricity": [0.42], "attitude": [1.0], "power_loss": [1800.0],
                "y_max_p": [8e6], "differential_flow_rate": [5e-4],
                "xj_cb": [0.2], "yj_cb": [-0.37], "non_convergence": [""],
            }],
            pressure_fields=[[[[1e6, 2e6], [3e6, 4e6]]]],
            temperature_fields=[[[[313.15, 323.15], [333.15, 343.15]]]],
            film_thickness_fields=[[[[8e-5, 7e-5], [6e-5, 5e-5]]]],
            theta_grids=[[[[0.0, 0.0], [1.0, 1.0]]]],
            z_grids=[[[[0.0, 0.01], [0.0, 0.01]]]],
            initial_time=10.0,
            final_time=12.5,
        )
        return SimpleNamespace(
            frequency=[100.0], kxx=native.kxx, kxy=native.kxy, kyx=native.kyx, kyy=native.kyy,
            cxx=native.cxx, cxy=native.cxy, cyx=native.cyx, cyy=native.cyy, _results=native,
        )


def test_coefficient_bearing_returns_native_rows():
    calc = RossBearingCalculator(builder=FakeBuilder())
    spec = CoefficientBearingSpec(
        position_mm=0, kxx=[1.0, 2.0], kzz=[7.0, 8.0], kxz=[3.0, 4.0], kzx=[5.0, 6.0],
        cxx=[9.0, 10.0], czz=[15.0, 16.0], cxz=[11.0, 12.0], czx=[13.0, 14.0],
        frequency_rpm=[1000.0, 2000.0],
    )
    result = calc.calculate(spec)
    assert [row.rpm for row in result.coefficients] == [1000.0, 2000.0]
    assert result.coefficients[1].kyy == pytest.approx(8.0)
    assert result.operating_points == []
    assert not result.has_field_results


def test_fluid_film_results_are_converted_to_engineering_units():
    calc = RossBearingCalculator(builder=FakeBuilder())
    spec = PlainJournalBearingSpec(
        position_mm=0, pad_axial_length_mm=80, journal_diameter_mm=100, radial_clearance_mm=0.1,
        n_pads=2, pad_arc_deg=175, oil_supply_temperature_c=40, frequency_rpm=[1500],
        lubricant="ISOVG32", load_y_n=-5000,
    )
    result = calc.calculate(spec)
    assert result.has_field_results
    assert result.execution_time_s == pytest.approx(2.5)
    point = result.operating_points[0]
    assert point.eccentricity_ratio == pytest.approx(0.42)
    assert point.min_film_thickness_mm == pytest.approx(0.05)
    assert point.max_temperature_c == pytest.approx(70.0)
    assert point.power_loss_kw == pytest.approx(1.8)
    assert point.flow_l_min == pytest.approx(30.0)
    assert point.converged
    assert result.temperature_fields_c[0][0][0][0] == pytest.approx(40.0)
    assert result.axial_grids_mm[0][0][0][1] == pytest.approx(10.0)
