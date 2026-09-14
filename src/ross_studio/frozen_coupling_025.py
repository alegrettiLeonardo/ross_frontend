from __future__ import annotations

from dataclasses import dataclass

from .coupling_qualification import run_coupling_qualification


@dataclass(slots=True)
class FrozenCoupling025Result:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


def run_frozen_coupling_025_test() -> FrozenCoupling025Result:
    result = run_coupling_qualification()
    payload = result.to_dict()
    if payload.get("status") != "PASS":
        raise RuntimeError(f"Frozen Coupling 0.25 feature qualification failed: {payload}")
    return FrozenCoupling025Result(payload)


__all__ = ["FrozenCoupling025Result", "run_frozen_coupling_025_test"]
