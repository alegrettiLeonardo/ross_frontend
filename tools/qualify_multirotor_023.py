from __future__ import annotations

import json
from pathlib import Path

from ross_studio.multirotor.qualification import run_multirotor_qualification


def main() -> None:
    result = run_multirotor_qualification()
    payload = result.to_dict()
    target = Path("artifacts/multirotor_023_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.status != "PASS": raise SystemExit("MultiRotor 0.23 qualification failed")


if __name__ == "__main__": main()
