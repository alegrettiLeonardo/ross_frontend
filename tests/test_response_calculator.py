from math import pi
from types import SimpleNamespace

import pytest

from ross_frontend.backends.ross.response_calculator import (
    FrequencyResponseRequest,
    ProjectUnbalanceResponseRequest,
    RossResponseCalculator,
    UnbalanceResponseRequest,
)
from ross_frontend.domain import MaterialSpec, ProbeSpec, RotorProject, ShaftSectionSpec, UnbalanceSpec


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
    ndof = 18
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
        # Node 1: x real, y imaginary so the 45-degree RotorDin probe
        # rotation can be checked exactly.
        rows[6] = [1 + 0j, 2 + 0j, 3 + 0j]
        rows[7] = [0 + 1j, 0 + 2j, 0 + 3j]
        # Node 2 used by the second physical probe.
        rows[12] = [2 + 0j, 4 + 0j, 6 + 0j]
        rows[13] = [0 + 2j, 0 + 4j, 0 + 6j]
        return SimpleNamespace(forced_resp=Matrix(rows))


class FakeBuilder:
    def __init__(self):
        self.rotor = FakeRotor()

    @staticmethod
    def _p(value):
        return round(float(value), 9)

    def build(self, project):
        positions = {0.0, project.shaft_length_mm}
        positions.update(item.position_mm for item in [*project.unbalances, *project.probes])
        node_map = {self._p(value): idx for idx, value in enumerate(sorted(positions))}
        return SimpleNamespace(rotor=self.rotor, node_by_position_mm=node_map)


def project():
    return RotorProject(
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000.0, 100.0)],
    )


def project_with_physical_response():
    return RotorProject(
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000.0, 100.0)],
        unbalances=[
            UnbalanceSpec(250.0, 100.0, 0.0, "U1"),
            UnbalanceSpec(750.0, 200.0, 90.0, "U2"),
        ],
        probes=[
            ProbeSpec(250.0, 1, 45.0, "P1-X45"),
            ProbeSpec(750.0, 2, 45.0, "P2-Y45"),
        ],
        metadata={"response": {"initial_rpm": 0.0, "final_rpm": 6000.0, "step_rpm": 3000.0}},
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
    assert result.curves[1].magnitude == pytest.approx([1.0, 2.0, 3.0])
    assert result.curves[2].magnitude == pytest.approx([2**0.5, 8**0.5, 18**0.5])


def test_project_unbalance_response_uses_all_planes_and_exact_rotordin_probe_rotation():
    builder = FakeBuilder()
    project_data = project_with_physical_response()
    result = RossResponseCalculator(builder).project_unbalance_response(
        project_data,
        ProjectUnbalanceResponseRequest(),
    )

    call = builder.rotor.unbalance_call
    assert len(call["node"]) == 2
    assert call["unbalance_magnitude"] == pytest.approx([100e-6, 200e-6])
    assert call["unbalance_phase"] == pytest.approx([0.0, pi / 2])
    assert len(call["frequency"]) == 3

    assert [curve.label for curve in result.curves] == ["P1-X45", "P2-Y45"]
    first = result.curves[0]
    second = result.curves[1]
    # (x + y)/sqrt(2): 1+i gives unit magnitude and 45 deg phase.
    assert first.magnitude == pytest.approx([1.0, 2.0, 3.0])
    assert first.phase_deg == pytest.approx([45.0, 45.0, 45.0])
    # (y - x)/sqrt(2) at node 2: -2+2i -> |.|=2, phase=135 deg.
    assert second.magnitude == pytest.approx([2.0, 4.0, 6.0])
    assert second.phase_deg == pytest.approx([135.0, 135.0, 135.0])


def test_response_requests_reject_invalid_ranges_and_indices():
    with pytest.raises(ValueError):
        FrequencyResponseRequest(start_rpm=1000, final_rpm=500, points=3).validate()
    with pytest.raises(ValueError):
        FrequencyResponseRequest(input_dof=-1).validate()
    with pytest.raises(ValueError):
        UnbalanceResponseRequest(node=-1).validate()
