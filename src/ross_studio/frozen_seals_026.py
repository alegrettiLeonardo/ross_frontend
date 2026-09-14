from __future__ import annotations

from dataclasses import dataclass

from .seals_qualification import run_seals_qualification


@dataclass(slots=True)
class FrozenSeals026Result:
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


def run_frozen_seals_026_test() -> FrozenSeals026Result:
    result = run_seals_qualification(frozen_mode=True)
    payload = result.to_dict()
    if payload.get("status") != "PASS":
        raise RuntimeError(f"Frozen Seals 0.26 qualification failed: {payload}")
    return FrozenSeals026Result(payload)


__all__ = ["FrozenSeals026Result", "run_frozen_seals_026_test"]
