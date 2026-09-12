from __future__ import annotations

from pathlib import Path

import pytest

from ross_studio.domain import (
    AdapterStatus,
    EngineeringError,
    FoundationCoefficientPoint,
    FoundationModel,
    FoundationSpec,
)
from ross_studio.models import load_reference_project_model
from ross_studio.project_io import load_project, save_project


def test_foundation_is_first_class_and_owned_by_support() -> None:
    model = load_reference_project_model()
    project = model.engineering
    assert project is not None
    project.foundations.append(
        FoundationSpec(
            name="DE foundation",
            support_index=0,
            model_type=FoundationModel.LUMPED_KCM,
            mass_kg=125.0,
            kxx=8.0e8,
            kyy=9.0e8,
            kxy=2.0e7,
            kyx=-1.0e7,
            cxx=1.5e5,
            cyy=1.8e5,
            cxy=2.0e3,
            cyx=-1.0e3,
        )
    )

    project.validate()

    foundation = project.foundations[0]
    assert foundation.support_index == 0
    assert project.supports[foundation.support_index].bearing_index == 0
    assert foundation.status == AdapterStatus.VALIDATED
    assert foundation.kxy == pytest.approx(2.0e7)
    assert foundation.cyx == pytest.approx(-1.0e3)


def test_foundation_ownership_is_one_to_one() -> None:
    model = load_reference_project_model()
    project = model.engineering
    assert project is not None
    project.foundations.extend(
        [
            FoundationSpec("F1", support_index=0, model_type=FoundationModel.RIGID),
            FoundationSpec("F2", support_index=0, model_type=FoundationModel.RIGID),
        ]
    )

    with pytest.raises(EngineeringError, match="more than one foundation"):
        project.validate()


def test_frequency_dependent_foundation_requires_strict_frequency_axis() -> None:
    foundation = FoundationSpec(
        "FD",
        support_index=0,
        model_type=FoundationModel.FREQUENCY_DEPENDENT_KC,
        coefficients=[
            FoundationCoefficientPoint(10.0, 1e8, 0.0, 0.0, 1.1e8, 1e4, 0.0, 0.0, 1.2e4),
            FoundationCoefficientPoint(20.0, 1.2e8, 1e6, -1e6, 1.3e8, 1.1e4, 100.0, -100.0, 1.3e4),
        ],
    )
    foundation.validate()
    assert foundation.frequency_dependent

    foundation.coefficients[1] = FoundationCoefficientPoint(
        10.0, 1.2e8, 1e6, -1e6, 1.3e8, 1.1e4, 100.0, -100.0, 1.3e4
    )
    with pytest.raises(EngineeringError, match="strictly increasing"):
        foundation.validate()


def test_six_dof_and_reduced_matrix_foundations_fail_closed() -> None:
    six_dof = FoundationSpec("6DOF", support_index=0, model_type=FoundationModel.LUMPED_KCM, mass_kg=10.0, dof=6)
    with pytest.raises(EngineeringError, match="6-DOF"):
        six_dof.validate()
    assert six_dof.status == AdapterStatus.BLOCKED

    reduced = FoundationSpec("ROM", support_index=0, model_type=FoundationModel.REDUCED_MATRIX)
    with pytest.raises(EngineeringError, match="REDUCED_MATRIX"):
        reduced.validate()
    assert reduced.status == AdapterStatus.BLOCKED


def test_native_project_roundtrip_preserves_foundation_contract(tmp_path: Path) -> None:
    model = load_reference_project_model()
    assert model.engineering is not None
    model.engineering.foundations.append(
        FoundationSpec(
            name="NDE FD foundation",
            support_index=1,
            model_type=FoundationModel.FREQUENCY_DEPENDENT_KC,
            coefficients=[
                FoundationCoefficientPoint(0.0, 5.0e8, 1.0e6, -2.0e6, 5.5e8, 8.0e4, 500.0, -400.0, 9.0e4),
                FoundationCoefficientPoint(120.0, 6.0e8, 2.0e6, -3.0e6, 6.5e8, 9.0e4, 600.0, -500.0, 1.0e5),
            ],
            metadata={"source": "Foundation Studio 0.24 qualification"},
        )
    )
    model.engineering.validate()

    target = save_project(model, tmp_path / "foundation.rossproj")
    restored = load_project(target)

    assert restored.engineering is not None
    assert restored.engineering.foundations == model.engineering.foundations
    assert restored.engineering.foundations[0].model_type == FoundationModel.FREQUENCY_DEPENDENT_KC
    assert restored.engineering.foundations[0].coefficients[1].frequency_hz == pytest.approx(120.0)
