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


def _failure_payload(exc: Exception) -> dict[str, object]:
    return {
        "status": "FAIL",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": format_exc(),
        "executable": str(Path(sys.executable).resolve()),
        "frozen": bool(getattr(sys, "frozen", False)),
    }


def frozen_self_test_main(argv: list[str]) -> int:
    output_path = _option_value(argv, "--self-test-output")
    try:
        from ross_studio.frozen_selftest import run_frozen_self_test

        result = run_frozen_self_test()
        payload: dict[str, object] = result.to_dict()
        payload["executable"] = str(Path(sys.executable).resolve())
        payload["frozen"] = bool(getattr(sys, "frozen", False))
        _write_payload(output_path, payload)
        return 0
    except Exception as exc:
        _write_payload(output_path, _failure_payload(exc))
        return 2


def frozen_project_io_main(argv: list[str]) -> int:
    output_path = _option_value(argv, "--project-io-output")
    try:
        from ross_studio.frozen_project_io import run_frozen_project_io_test

        result = run_frozen_project_io_test()
        payload: dict[str, object] = result.to_dict()
        payload["executable"] = str(Path(sys.executable).resolve())
        payload["frozen"] = bool(getattr(sys, "frozen", False))
        _write_payload(output_path, payload)
        return 0
    except Exception as exc:
        _write_payload(output_path, _failure_payload(exc))
        return 4


def frozen_gui_smoke_main(argv: list[str]) -> int:
    output_path = _option_value(argv, "--gui-smoke-output")
    try:
        from ross_studio.frozen_gui_smoke import run_frozen_gui_smoke

        result = run_frozen_gui_smoke()
        payload: dict[str, object] = result.to_dict()
        payload["executable"] = str(Path(sys.executable).resolve())
        payload["frozen"] = bool(getattr(sys, "frozen", False))
        _write_payload(output_path, payload)
        return 0
    except Exception as exc:
        _write_payload(output_path, _failure_payload(exc))
        return 3


def main() -> int:
    argv = list(sys.argv[1:])
    if "--self-test" in argv or "--self-test-output" in argv:
        return frozen_self_test_main(argv)
    if "--project-io-self-test" in argv or "--project-io-output" in argv:
        return frozen_project_io_main(argv)
    if "--gui-smoke" in argv or "--gui-smoke-output" in argv:
        return frozen_gui_smoke_main(argv)

    # Keep heavy Qt imports out of scientific and I/O packaging self-test bootstraps.
    # Normal desktop execution still enters the exact production application.
    from ross_studio.app import launch

    return int(launch())


if __name__ == "__main__":
    raise SystemExit(main())
