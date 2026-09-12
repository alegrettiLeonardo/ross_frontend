from __future__ import annotations

import json
from pathlib import Path
import platform
import subprocess
import sys


def executable_path(dist_root: Path) -> Path:
    name = "ROSS-Studio.exe" if platform.system() == "Windows" else "ROSS-Studio"
    return dist_root / "ROSS-Studio" / name


def main() -> int:
    dist_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_foundation_024.json")
    exe = executable_path(dist_root).resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(exe), "--foundation-024-self-test", "--foundation-024-output", str(output)],
        check=False,
        timeout=300,
    )
    if not output.is_file():
        raise SystemExit(f"Frozen Foundation 0.24 gate produced no output; returncode={proc.returncode}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS" or payload.get("frozen") is not True:
        raise SystemExit(json.dumps(payload, indent=2, ensure_ascii=False))
    assert payload["ross_version"] == "2.3.0"
    assert payload["rigid_exact_m_parity"] is True
    assert payload["rigid_exact_k_parity"] is True
    assert payload["rigid_exact_c_parity"] is True
    assert payload["high_stiffness_max_error_percent"] < 0.5
    assert payload["modal_sensitivity_max_shift_percent"] > 0.5
    assert payload["matrix_delta_norm_m"] > 0.0
    assert payload["matrix_delta_norm_k"] > 0.0
    assert payload["matrix_delta_norm_c"] > 0.0
    assert payload["cross_coupled_k_pass"] is True
    assert payload["cross_coupled_c_pass"] is True
    assert payload["frequency_axis_rad_s_pass"] is True
    assert payload["frequency_interpolation_pass"] is True
    assert payload["unsupported_contracts_blocked"] is True
    assert payload["exact_support_ownership_pass"] is True
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
