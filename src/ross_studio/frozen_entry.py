from __future__ import annotations

import json
from pathlib import Path
import sys
from traceback import format_exc


def _option_value(argv: list[str], name: str) -> str | None:
    try:
        index = argv.index(name)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        raise SystemExit(f"{name} requires a path argument")
    return argv[index + 1]


def _write_payload(path: str | None, payload: dict[str, object]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def frozen_self_test_main(argv: list[str]) -> int:
    output_path = _option_value(argv, "--self-test-output")
    try:
        from .frozen_selftest import run_frozen_self_test

        result = run_frozen_self_test()
        payload: dict[str, object] = result.to_dict()
        payload["executable"] = str(Path(sys.executable).resolve())
        payload["frozen"] = bool(getattr(sys, "frozen", False))
        _write_payload(output_path, payload)
        return 0
    except Exception as exc:
        payload = {
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": format_exc(),
            "executable": str(Path(sys.executable).resolve()),
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        _write_payload(output_path, payload)
        return 2


def main() -> int:
    argv = list(sys.argv[1:])
    if "--self-test" in argv or "--self-test-output" in argv:
        return frozen_self_test_main(argv)

    # Keep the heavy Qt application import out of the packaging self-test bootstrap.
    # This also gives the CI a clean way to prove the scientific runtime independently
    # of a desktop display while still using the exact same frozen executable.
    from .app import launch

    return int(launch())


if __name__ == "__main__":
    raise SystemExit(main())
