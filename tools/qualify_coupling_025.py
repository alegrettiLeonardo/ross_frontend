from __future__ import annotations

import json
from pathlib import Path

from ross_studio.coupling_qualification import run_coupling_qualification


def main() -> None:
    result = run_coupling_qualification()
    payload = result.to_dict()
    target = Path("artifacts/coupling_025_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.status != "PASS":
        raise SystemExit("Coupling 0.25 feature qualification failed")


if __name__ == "__main__":
    main()
