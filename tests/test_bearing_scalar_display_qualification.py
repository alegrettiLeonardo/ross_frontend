from copy import deepcopy

import pytest

from ross_studio.bearing_scalar_qualification import run_direct_kc_case, run_scalar_bearing_case


@pytest.mark.parametrize("model", ["BallBearingElement", "RollerBearingElement", "CylindricalBearing"])
def test_scalar_kc_survives_apply_and_reopen(qtbot, tmp_path, model):
    result = run_scalar_bearing_case(model, tmp_path)
    assert result["status"] == "PASS"
    assert result["native_class"] == model
    assert result["coefficient_comparisons"]
    assert all(row["status"] == "PASS" for row in result["coefficient_comparisons"])


def test_direct_kc_full_transaction_survives_apply_and_reopen(qtbot, tmp_path):
    result = run_direct_kc_case(tmp_path)
    assert result["status"] == "PASS"
    assert result["native_class"] == "BearingElement"
    assert len(result["coefficient_comparisons"]) == 5 * 8
    assert all(row["status"] == "PASS" for row in result["coefficient_comparisons"])


def test_apply_without_calculate_is_rejected_without_mutation(qtbot):
    """Apply is fail-closed when no calculation context exists."""
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    before = deepcopy(window.project.engineering)
    assert window.bearing_calculation is None
    assert window.bearing_context is None

    window._apply_bearing()

    assert window.project.engineering == before
    assert window.bearing_calculation is None
    assert window.bearing_context is None
    assert not window.bearing_page.apply_button.isEnabled()


@pytest.mark.parametrize("nonfinite", ["nan", "inf", "-inf"])
def test_direct_kc_nonfinite_input_is_rejected_before_apply(qtbot, nonfinite):
    """NaN/Inf entered in the K/C editor cannot become a calculated/applied bearing."""
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    window._refresh_bearing_page(selected_class="BearingElement")
    before = deepcopy(window.project.engineering)
    table = window.bearing_page.input_panel.kc_table
    assert table is not None
    table.item(0, 1).setText(nonfinite)

    window._calculate_bearing()

    assert window.bearing_calculation is None
    assert window.bearing_context is None
    assert not window.bearing_page.apply_button.isEnabled()
    assert window.project.engineering == before


def test_direct_kc_mismatched_column_lengths_fail_closed(qtbot):
    """The row-oriented GUI rejects the equivalent of unequal parallel K/C array lengths.

    Bearing Studio persists K/C as complete ``BearingCoefficientPoint`` rows rather than
    independent arrays. A shorter coefficient column therefore materializes as a missing
    cell in one row and must be rejected before Calculate can create a preview.
    """
    from ross_studio.app import RossStudioWindow

    window = RossStudioWindow()
    qtbot.addWidget(window)
    window._refresh_bearing_page(selected_class="BearingElement")
    before = deepcopy(window.project.engineering)
    table = window.bearing_page.input_panel.kc_table
    assert table is not None
    assert table.rowCount() >= 1

    # Remove Cyy from one speed row: conceptually Cyy has N-1 values while the
    # frequency and the other seven K/C columns have N values.
    removed = table.takeItem(0, 8)
    assert removed is not None
    window._calculate_bearing()

    assert window.bearing_calculation is None
    assert window.bearing_context is None
    assert not window.bearing_page.apply_button.isEnabled()
    assert window.project.engineering == before
