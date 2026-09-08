import pytest

from ross_frontend.domain import DomainError, UmpFormulation, UMPRegionSpec
from ross_frontend.ross_ext.ump import (
    ROTORDIN_LEGACY_THRESHOLD_N_M2,
    consistent_ump_matrix,
    legacy_ump_to_si,
    rotordin_legacy_ump_matrix,
)


def _flatten(matrix):
    return [value for row in matrix for value in row]


def test_legacy_ump_conversion_is_explicit_only():
    assert legacy_ump_to_si(1.002) == pytest.approx(9_826_263.3)
    with pytest.raises(ValueError):
        legacy_ump_to_si(-1.0)


def test_corrected_consistent_ump_matrix_is_symmetric_lateral_only():
    k = 2.0e6
    length = 0.5
    matrix = consistent_ump_matrix(k, length)

    assert len(matrix) == 12
    assert all(len(row) == 12 for row in matrix)
    for i in range(12):
        for j in range(12):
            assert matrix[i][j] == pytest.approx(matrix[j][i])

    scale = k * length / 420.0
    assert matrix[0][0] == pytest.approx(scale * 156.0)
    assert matrix[0][4] == pytest.approx(scale * 22.0 * length)
    assert matrix[1][3] == pytest.approx(-matrix[0][4])

    axial_torsional = (2, 5, 8, 11)
    for dof in axial_torsional:
        assert all(matrix[dof][j] == pytest.approx(0.0) for j in range(12))
        assert all(matrix[i][dof] == pytest.approx(0.0) for i in range(12))


def test_corrected_ump_is_linear_and_continuous_at_zero():
    length = 0.4
    one = consistent_ump_matrix(1.5e6, length)
    two = consistent_ump_matrix(3.0e6, length)
    zero = consistent_ump_matrix(0.0, length)

    assert _flatten(two) == pytest.approx([2.0 * value for value in _flatten(one)])
    assert _flatten(zero) == pytest.approx([0.0] * 144)
    tiny = consistent_ump_matrix(1e-12, length)
    assert max(abs(v) for v in _flatten(tiny)) < 1e-12


def test_corrected_tensor_supports_cross_coupled_electromagnetic_stiffness():
    matrix = consistent_ump_matrix(
        2.0e6,
        0.5,
        kyy_prime_n_m2=3.0e6,
        kxy_prime_n_m2=0.4e6,
        kyx_prime_n_m2=-0.2e6,
    )
    assert matrix[0][0] > 0.0
    assert matrix[1][1] > matrix[0][0]
    assert matrix[0][1] > 0.0
    assert matrix[1][0] < 0.0
    assert matrix[0][1] != pytest.approx(matrix[1][0])


def test_rotordin_legacy_compat_reproduces_coemas_rotary_term_and_threshold():
    length = 0.3575
    rho = 7850.0
    inertia = 1.63e-4
    k = 1.002

    corrected = consistent_ump_matrix(k, length)
    legacy = rotordin_legacy_ump_matrix(k, length, rho, inertia)
    assert legacy[0][0] > corrected[0][0]
    assert legacy[1][1] > corrected[1][1]

    threshold = rotordin_legacy_ump_matrix(
        ROTORDIN_LEGACY_THRESHOLD_N_M2,
        length,
        rho,
        inertia,
    )
    assert _flatten(threshold) == pytest.approx([0.0] * 144)


def test_physical_corrected_is_fail_closed_for_unknown_legacy_unit():
    region = UMPRegionSpec(
        0.0,
        100.0,
        1.002,
        formulation=UmpFormulation.PHYSICAL_CORRECTED,
        source_unit="legacy_unknown",
    )
    with pytest.raises(DomainError, match="fail-closed"):
        region.validate(1000.0)


def test_schema_v4_isotropic_constructor_alias_still_works():
    region = UMPRegionSpec(0.0, 100.0, stiffness_per_length_n_m2=123.0)
    assert region.kxx_prime_n_m2 == pytest.approx(123.0)
    assert region.kyy_prime_n_m2 == pytest.approx(123.0)
    assert region.stiffness_per_length_n_m2 == pytest.approx(123.0)
