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
    return {"status":"FAIL","error_type":type(exc).__name__,"error":str(exc),"traceback":format_exc(),"executable":str(Path(sys.executable).resolve()),"frozen":bool(getattr(sys,"frozen",False))}


def _run(argv: list[str], output_flag: str, import_path: str, function_name: str, code: int) -> int:
    output_path = _option_value(argv, output_flag)
    try:
        module = __import__(import_path, fromlist=[function_name]); result = getattr(module, function_name)(); payload: dict[str, object] = result.to_dict(); payload["executable"] = str(Path(sys.executable).resolve()); payload["frozen"] = bool(getattr(sys,"frozen",False)); _write_payload(output_path, payload); return 0
    except Exception as exc:
        _write_payload(output_path, _failure_payload(exc)); return code


def frozen_self_test_main(argv): return _run(argv,"--self-test-output","ross_studio.frozen_selftest","run_frozen_self_test",2)
def frozen_project_io_main(argv): return _run(argv,"--project-io-output","ross_studio.frozen_project_io","run_frozen_project_io_test",4)
def frozen_gui_smoke_main(argv): return _run(argv,"--gui-smoke-output","ross_studio.frozen_gui_smoke","run_frozen_gui_smoke",3)
def frozen_engineering_outputs_main(argv): return _run(argv,"--engineering-outputs-output","ross_studio.frozen_engineering_outputs","run_frozen_engineering_outputs_test",5)
def frozen_static_modal_020_main(argv): return _run(argv,"--static-modal-020-output","ross_studio.frozen_static_modal_020","run_frozen_static_modal_020_test",6)
def frozen_time_frequency_021_main(argv): return _run(argv,"--time-frequency-021-output","ross_studio.frozen_time_frequency_021","run_frozen_time_frequency_021_test",7)
def frozen_stochastic_022_main(argv): return _run(argv,"--stochastic-022-output","ross_studio.frozen_stochastic_022","run_frozen_stochastic_022_test",8)
def frozen_multirotor_023_main(argv): return _run(argv,"--multirotor-023-output","ross_studio.frozen_multirotor_023","run_frozen_multirotor_023_test",9)


def main() -> int:
    argv = list(sys.argv[1:])
    if "--self-test" in argv or "--self-test-output" in argv: return frozen_self_test_main(argv)
    if "--project-io-self-test" in argv or "--project-io-output" in argv: return frozen_project_io_main(argv)
    if "--gui-smoke" in argv or "--gui-smoke-output" in argv: return frozen_gui_smoke_main(argv)
    if "--engineering-outputs-self-test" in argv or "--engineering-outputs-output" in argv: return frozen_engineering_outputs_main(argv)
    if "--static-modal-020-self-test" in argv or "--static-modal-020-output" in argv: return frozen_static_modal_020_main(argv)
    if "--time-frequency-021-self-test" in argv or "--time-frequency-021-output" in argv: return frozen_time_frequency_021_main(argv)
    if "--stochastic-022-self-test" in argv or "--stochastic-022-output" in argv: return frozen_stochastic_022_main(argv)
    if "--multirotor-023-self-test" in argv or "--multirotor-023-output" in argv: return frozen_multirotor_023_main(argv)
    from ross_studio.app import launch
    return int(launch())


if __name__ == "__main__": raise SystemExit(main())
