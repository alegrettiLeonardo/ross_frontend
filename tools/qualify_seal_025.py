from __future__ import annotations

import json
from pathlib import Path

from ross_studio.seal_qualification import run_seal_qualification


def main() -> int:
    result = run_seal_qualification()
    payload = result.to_dict()
    target = Path("artifacts/seal_025_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
