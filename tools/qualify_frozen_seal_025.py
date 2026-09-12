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
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/frozen_seal_025.json")
    exe = executable_path(dist_root).resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(exe), "--seal-025-self-test", "--seal-025-output", str(output)],
        check=False,
        timeout=900,
    )
    if not output.is_file():
        raise SystemExit(f"Frozen Seal Studio 0.25 gate produced no output; returncode={proc.returncode}")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if proc.returncode != 0 or payload.get("status") != "PASS" or payload.get("frozen") is not True:
        raise SystemExit(json.dumps(payload, indent=2, ensure_ascii=False))
    assert payload["ross_version"] == "2.3.0"
    assert payload["prospective_exact_node_pass"] is True
    assert payload["direct_kc_parity_pass"] is True
    assert payload["labyrinth_native_class"] == "LabyrinthSeal"
    assert payload["labyrinth_regression_pass"] is True
    assert payload["labyrinth_builder_parity_pass"] is True
    assert payload["labyrinth_k_plot_traces"] > 0
    assert payload["labyrinth_pressure_plot_traces"] > 0
    assert payload["hole_pattern_native_class"] == "HolePatternSeal"
    assert payload["hole_pattern_regression_pass"] is True
    assert payload["hole_pattern_builder_parity_pass"] is True
    assert payload["hole_pattern_k_plot_traces"] > 0
    assert payload["hole_pattern_pressure_plot_traces"] > 0
    assert payload["hybrid_native_class"] == "HybridSeal"
    assert payload["hybrid_regression_pass"] is True
    assert payload["hybrid_builder_parity_pass"] is True
    assert payload["hybrid_convergence_plot_traces"] >= 3
    assert payload["hybrid_final_convergence"] <= 1.0e-6
    assert payload["persistence_roundtrip_pass"] is True
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
