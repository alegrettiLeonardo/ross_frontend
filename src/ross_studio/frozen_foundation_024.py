from __future__ import annotations

from dataclasses import dataclass

from .foundation_qualification import run_foundation_qualification


@dataclass(slots=True)
class FrozenFoundation024Result:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


def run_frozen_foundation_024_test() -> FrozenFoundation024Result:
    result = run_foundation_qualification()
    payload = result.to_dict()
    if payload.get("status") != "PASS":
        raise RuntimeError(f"Frozen Foundation Studio 0.24 qualification failed: {payload}")
    return FrozenFoundation024Result(payload)


__all__ = ["FrozenFoundation024Result", "run_frozen_foundation_024_test"]
