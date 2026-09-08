from math import pi
from types import SimpleNamespace

import pytest

from ross_frontend.backends.ross.response_calculator import (
    FrequencyResponseRequest,
    RossResponseCalculator,
    UnbalanceResponseRequest,
)
from ross_frontend.domain import MaterialSpec, RotorProject, ShaftSectionSpec


class Cube:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        out, inp, _ = key
        return self.values[(out, inp)]


class Matrix:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, key):
        row, _ = key
        return self.rows[row]


class FakeRotor:
    ndof = 12
    number_dof = 6

    def __init__(self):
        self.freq_call = None
        self.unbalance_call = None

    def run_freq_response(self, speed_range, modes=None):
        self.freq_call = (list(speed_range), modes)
        return SimpleNamespace(
            freq_resp=Cube({(1, 0): [1 + 0j, 0 + 2j, -3 + 0j]})
        )

    def run_unbalance_response(self, **kwargs):
        self.unbalance_call = kwargs
        rows = [[0j, 0j, 0j] for _ in range(self.ndof)]
        rows[6] = [1 + 0j, 2 + 0j, 3 + 0j]
        rows[7] = [0 + 1j, 0 + 2j, 0 + 4j]
        return SimpleNamespace(forced_resp=Matrix(rows))


class FakeBuilder:
    def __init__(self):
        self.rotor = FakeRotor()

    def build(self, project):
        return SimpleNamespace(rotor=self.rotor)


def project():
    return RotorProject(
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000.0, 100.0)],
    )


def test_frequency_response_normalizes_complex_transfer_function():
    builder = FakeBuilder()
    result = RossResponseCalculator(builder).frequency_response(
        project(),
        FrequencyResponseRequest(start_rpm=0, final_rpm=6000, points=3, input_dof=0, output_dof=1),
    )
    curve = result.curves[0]
    assert curve.x == [0.0, 3000.0, 6000.0]
    assert curve.magnitude == pytest.approx([1.0, 2.0, 3.0])
    assert curve.phase_deg == pytest.approx([0.0, 90.0, 180.0])
    assert curve.magnitude_unit == "m/N"
    assert len(builder.rotor.freq_call[0]) == 3


def test_unbalance_response_converts_g_mm_and_returns_xy_radial_curves():
    builder = FakeBuilder()
    result = RossResponseCalculator(builder).unbalance_response(
        project(),
        UnbalanceResponseRequest(
            node=0,
            probe_node=1,
            magnitude_g_mm=100.0,
            phase_deg=90.0,
            start_rpm=0,
            final_rpm=6000,
            points=3,
        ),
    )
    call = builder.rotor.unbalance_call
    assert call["unbalance_magnitude"] == pytest.approx(100e-6)
    assert call["unbalance_phase"] == pytest.approx(pi / 2)
    assert [curve.label for curve in result.curves] == ["X", "Y", "Radial"]
    assert result.curves[0].magnitude == pytest.approx([1.0, 2.0, 3.0])
    assert result.curves[1].magnitude == pytest.approx([1.0, 2.0, 4.0])
    assert result.curves[2].magnitude == pytest.approx([2**0.5, 8**0.5, 5.0])


def test_response_requests_reject_invalid_ranges_and_indices():
    with pytest.raises(ValueError):
        FrequencyResponseRequest(start_rpm=1000, final_rpm=500, points=3).validate()
    with pytest.raises(ValueError):
        FrequencyResponseRequest(input_dof=-1).validate()
    with pytest.raises(ValueError):
        UnbalanceResponseRequest(node=-1).validate()
