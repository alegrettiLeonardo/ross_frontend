from __future__ import annotations

import json
from pathlib import Path

from ross_studio.seals_qualification import run_seals_qualification


def main() -> int:
    result = run_seals_qualification()
    payload = result.to_dict()
    target = Path("artifacts/seals_026_qualification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "qualification_matrix": payload["qualification_matrix"], "artifact": str(target)}, indent=2))
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
