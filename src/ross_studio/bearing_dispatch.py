"""Explicit class dispatch and producer-bound calculation context."""
from dataclasses import dataclass

from .bearing_studio_service import BearingCalculationResult, BearingStudioService
from .domain import EngineeringError
from .thd_bearing_service import THDBearingCalculationResult, THDBearingStudioService
from .thrust_pad_service import ThrustPadCalculationResult, ThrustPadStudioService


BearingResult = BearingCalculationResult | THDBearingCalculationResult | ThrustPadCalculationResult
BearingService = BearingStudioService | THDBearingStudioService | ThrustPadStudioService


@dataclass(frozen=True)
class BearingCalculationContext:
    service: BearingService
    result: BearingResult
    bearing_index: int
    project_snapshot: object


class BearingServiceDispatcher:
    """Route each ROSS class to one explicit scientific owner."""

    def __init__(self, general, thd, thrust_pad):
        self.services = {name: general for name in general.GENERAL_CLASSES}
        self.services.update({name: thd for name in thd.SUPPORTED_CLASSES})
        self.services.update({name: thrust_pad for name in thrust_pad.SUPPORTED_CLASSES})

    def for_class(self, ross_class):
        if ross_class not in self.services:
            raise EngineeringError(f"{ross_class}: no qualified ROSS Studio scientific service is registered.")
        return self.services[ross_class]


__all__ = [
    "BearingCalculationContext",
    "BearingResult",
    "BearingService",
    "BearingServiceDispatcher",
]
