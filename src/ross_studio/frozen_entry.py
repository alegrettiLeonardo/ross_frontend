from __future__ import annotations

import json
from pathlib import Path
import sys
from traceback import format_exc
from typing import Callable, Protocol


class _SerializableResult(Protocol):
    def to_dict(self) -> dict[str, object]: ...


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


def _run_callable(argv: list[str], output_flag: str, runner: Callable[[], _SerializableResult], failure_code: int) -> int:
    output_path = _option_value(argv, output_flag)
    try:
        result = runner()
        payload: dict[str, object] = result.to_dict()
        payload["executable"] = str(Path(sys.executable).resolve())
        payload["frozen"] = bool(getattr(sys, "frozen", False))
        _write_payload(output_path, payload)
        return 0
    except Exception as exc:
        _write_payload(output_path, _failure_payload(exc))
        return failure_code


def frozen_self_test_main(argv: list[str]) -> int:
    from ross_studio.frozen_selftest import run_frozen_self_test
    return _run_callable(argv, "--self-test-output", run_frozen_self_test, 2)


def frozen_project_io_main(argv: list[str]) -> int:
    from ross_studio.frozen_project_io import run_frozen_project_io_test
    return _run_callable(argv, "--project-io-output", run_frozen_project_io_test, 4)


def frozen_gui_smoke_main(argv: list[str]) -> int:
    from ross_studio.frozen_gui_smoke import run_frozen_gui_smoke
    return _run_callable(argv, "--gui-smoke-output", run_frozen_gui_smoke, 3)


def frozen_engineering_outputs_main(argv: list[str]) -> int:
    from ross_studio.frozen_engineering_outputs import run_frozen_engineering_outputs_test
    return _run_callable(argv, "--engineering-outputs-output", run_frozen_engineering_outputs_test, 5)


def frozen_static_modal_020_main(argv: list[str]) -> int:
    from ross_studio.frozen_static_modal_020 import run_frozen_static_modal_020_test
    return _run_callable(argv, "--static-modal-020-output", run_frozen_static_modal_020_test, 6)


def frozen_time_frequency_021_main(argv: list[str]) -> int:
    from ross_studio.frozen_time_frequency_021 import run_frozen_time_frequency_021_test
    return _run_callable(argv, "--time-frequency-021-output", run_frozen_time_frequency_021_test, 7)


def frozen_stochastic_022_main(argv: list[str]) -> int:
    from ross_studio.frozen_stochastic_022 import run_frozen_stochastic_022_test
    return _run_callable(argv, "--stochastic-022-output", run_frozen_stochastic_022_test, 8)


def frozen_multirotor_023_main(argv: list[str]) -> int:
    from ross_studio.frozen_multirotor_023 import run_frozen_multirotor_023_test
    return _run_callable(argv, "--multirotor-023-output", run_frozen_multirotor_023_test, 9)


def frozen_foundation_024_main(argv: list[str]) -> int:
    from ross_studio.frozen_foundation_024 import run_frozen_foundation_024_test
    return _run_callable(argv, "--foundation-024-output", run_frozen_foundation_024_test, 10)


def frozen_seal_025_main(argv: list[str]) -> int:
    from ross_studio.frozen_seal_025 import run_frozen_seal_025_test
    return _run_callable(argv, "--seal-025-output", run_frozen_seal_025_test, 11)


def main() -> int:
    argv = list(sys.argv[1:])
    if "--self-test" in argv or "--self-test-output" in argv:
        return frozen_self_test_main(argv)
    if "--project-io-self-test" in argv or "--project-io-output" in argv:
        return frozen_project_io_main(argv)
    if "--gui-smoke" in argv or "--gui-smoke-output" in argv:
        return frozen_gui_smoke_main(argv)
    if "--engineering-outputs-self-test" in argv or "--engineering-outputs-output" in argv:
        return frozen_engineering_outputs_main(argv)
    if "--static-modal-020-self-test" in argv or "--static-modal-020-output" in argv:
        return frozen_static_modal_020_main(argv)
    if "--time-frequency-021-self-test" in argv or "--time-frequency-021-output" in argv:
        return frozen_time_frequency_021_main(argv)
    if "--stochastic-022-self-test" in argv or "--stochastic-022-output" in argv:
        return frozen_stochastic_022_main(argv)
    if "--multirotor-023-self-test" in argv or "--multirotor-023-output" in argv:
        return frozen_multirotor_023_main(argv)
    if "--foundation-024-self-test" in argv or "--foundation-024-output" in argv:
        return frozen_foundation_024_main(argv)
    if "--seal-025-self-test" in argv or "--seal-025-output" in argv:
        return frozen_seal_025_main(argv)

    from ross_studio.app import launch
    return int(launch())


if __name__ == "__main__":
    raise SystemExit(main())
