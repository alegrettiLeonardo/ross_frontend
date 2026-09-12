from __future__ import annotations

import json
from pathlib import Path

from ross_studio.foundation_qualification import run_foundation_qualification


def main() -> None:
    result = run_foundation_qualification()
    payload = result.to_dict()
    target = Path("artifacts/foundation_024_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.status != "PASS":
        raise SystemExit("Foundation Studio 0.24 qualification failed")


if __name__ == "__main__":
    main()
