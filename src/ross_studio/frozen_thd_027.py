from __future__ import annotations

from dataclasses import dataclass

from .thd_qualification_027 import run_thd_bearings_027_qualification


@dataclass(slots=True)
class FrozenTHD027Result:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


def run_frozen_thd_027_test() -> FrozenTHD027Result:
    result = run_thd_bearings_027_qualification(frozen_mode=True)
    payload = result.to_dict()
    if payload.get("status") != "PASS":
        raise RuntimeError(f"Frozen THD Bearings 0.27 qualification failed: {payload}")
    return FrozenTHD027Result(payload)


__all__ = ["FrozenTHD027Result", "run_frozen_thd_027_test"]
