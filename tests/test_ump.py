import pytest

from ross_frontend.ross_ext.ump import (
    consistent_ump_matrix,
    legacy_ump_to_si,
    ump_force_from_displacement,
)


def test_legacy_ump_conversion_is_explicit_and_si():
    assert legacy_ump_to_si(1.002) == pytest.approx(9_826_263.3)
    with pytest.raises(ValueError):
        legacy_ump_to_si(-1.0)


def test_consistent_ump_matrix_is_symmetric_lateral_only():
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
    # alpha has the opposite ROSS bending sign to beta.
    assert matrix[1][3] == pytest.approx(-matrix[0][4])

    axial_torsional = (2, 5, 8, 11)
    for dof in axial_torsional:
        assert all(matrix[dof][j] == pytest.approx(0.0) for j in range(12))
        assert all(matrix[i][dof] == pytest.approx(0.0) for i in range(12))


def test_force_side_and_negative_stiffness_forms_are_equivalent():
    k = 1.0e6
    length = 0.4
    q = [0.0] * 12
    q[0] = 1.0e-3
    q[6] = 0.5e-3

    matrix = consistent_ump_matrix(k, length)
    force = ump_force_from_displacement(k, length, q)
    expected = [sum(matrix[i][j] * q[j] for j in range(12)) for i in range(12)]
    assert force == pytest.approx(expected)
    assert force[0] > 0.0
    assert force[6] > 0.0


def test_ump_matrix_rejects_invalid_physical_values():
    with pytest.raises(ValueError):
        consistent_ump_matrix(-1.0, 0.5)
    with pytest.raises(ValueError):
        consistent_ump_matrix(1.0, 0.0)
