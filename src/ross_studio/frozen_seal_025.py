from __future__ import annotations

from .seal_qualification import SealQualification, run_seal_qualification


def run_frozen_seal_025_test() -> SealQualification:
    result = run_seal_qualification()
    if result.status != "PASS":
        raise RuntimeError(f"Frozen Seal Studio 0.25 qualification failed: {result.to_dict()}")
    return result


__all__ = ["run_frozen_seal_025_test"]
