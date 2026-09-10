"""Explicit class dispatch and producer-bound calculation context."""
from dataclasses import dataclass

from .bearing_studio_service import BearingCalculationResult, BearingStudioService
from .domain import EngineeringError
from .thd_bearing_service import THDBearingCalculationResult, THDBearingStudioService


@dataclass(frozen=True)
class BearingCalculationContext:
    service: BearingStudioService | THDBearingStudioService
    result: BearingCalculationResult | THDBearingCalculationResult
    bearing_index: int
    project_snapshot: object


class BearingServiceDispatcher:
    def __init__(self, general, thd):
        self.services = {name: general for name in general.GENERAL_CLASSES}
        self.services.update({name: thd for name in thd.SUPPORTED_CLASSES})

    def for_class(self, ross_class):
        if ross_class not in self.services:
            raise EngineeringError(f"{ross_class}: axial/AMB coupling remains blocked.")
        return self.services[ross_class]
