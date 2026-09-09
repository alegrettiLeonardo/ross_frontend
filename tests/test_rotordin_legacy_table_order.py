from pathlib import Path

import pytest

from ross_frontend.backends.ross.legacy_builder import RotorDinLegacyModelBuilder
from ross_frontend.legacy_import import load_irdin_project


CASE = Path(__file__).resolve().parents[1] / "cases" / "OP-W60-500-60Hz-IC611-P3" / "irdin_input.txt"


def test_w60_inline_table_is_decoded_in_rotordin_canonical_order():
    """RotorDin TABLE is rpm,xx,xz,zx,zz for both K and C.

    The historical frontend forwards the inline row unchanged to the Fortran
    TABLE reader.  This gate prevents the generic legacy grid-column naming from
    silently swapping the third and fourth coefficient in compatibility runs.
    """
    project = load_irdin_project(CASE)
    front = project.bearings[0]
    table = RotorDinLegacyModelBuilder._rotordin_table_coefficients(front)

    assert table["kxx"][0] == pytest.approx(1.66e8)
    assert table["kxz"][0] == pytest.approx(-9.02e7)
    assert table["kzx"][0] == pytest.approx(-5.08e8)
    assert table["kzz"][0] == pytest.approx(1.05e9)
    assert table["cxx"][0] == pytest.approx(7.68e5)
    assert table["cxz"][0] == pytest.approx(-1.66e6)
    assert table["czx"][0] == pytest.approx(-1.66e6)
    assert table["czz"][0] == pytest.approx(8.60e6)
