import pytest

from ross_frontend.domain import (
    CoefficientBearingSpec,
    DomainError,
    MaterialSpec,
    RotorProject,
    ShaftSectionSpec,
)


def test_speed_dependent_coefficients_require_same_length():
    project = RotorProject(
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(1000, 100)],
        bearings=[
            CoefficientBearingSpec(
                100,
                kxx=[1.0, 2.0],
                kzz=[1.0, 2.0],
                cxx=[1.0, 2.0],
                czz=[1.0, 2.0],
                frequency_rpm=[1000, 2000],
            )
        ],
    )
    project.validate()
    project.bearings[0].kxx = [1.0]
    with pytest.raises(DomainError, match="same length"):
        project.validate()


def test_component_must_be_on_shaft():
    project = RotorProject(
        materials=[MaterialSpec()],
        shaft=[ShaftSectionSpec(100, 10)],
        bearings=[CoefficientBearingSpec(101, 1, 1, 1, 1)],
    )
    with pytest.raises(DomainError, match="outside the shaft"):
        project.validate()
