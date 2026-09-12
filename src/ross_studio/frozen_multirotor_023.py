from __future__ import annotations

from dataclasses import dataclass

from .multirotor.qualification import run_multirotor_qualification


@dataclass(slots=True)
class FrozenMultiRotor023Result:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


def run_frozen_multirotor_023_test() -> FrozenMultiRotor023Result:
    result = run_multirotor_qualification()
    payload = result.to_dict()
    if payload.get("status") != "PASS":
        raise RuntimeError(f"Frozen MultiRotor 0.23 qualification failed: {payload}")
    return FrozenMultiRotor023Result(payload)


__all__ = ["FrozenMultiRotor023Result", "run_frozen_multirotor_023_test"]
