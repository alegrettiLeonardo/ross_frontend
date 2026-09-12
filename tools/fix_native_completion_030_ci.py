from __future__ import annotations

from pathlib import Path

path = Path("tools/qualify_bearing_native_outputs_0151.py")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        "from ross_studio.domain import AdapterStatus\n",
        "",
    ),
    (
        '    gates["AMB_blocked"] = amb_status == AdapterStatus.BLOCKED\n',
        '    # AMB was outside the 0.15.1 Bearing Native Outputs qualification scope.\n'
        '    # Its current capability status is reported below, while the dedicated 0.30 gate\n'
        '    # qualifies MagneticBearingElement, Newmark feedback outputs and ISO sensitivity.\n',
    ),
    (
        '            "AMB": "blocked until actuator/sensor/controller domain is qualified",\n',
        '            "AMB": "outside the 0.15.1 pass/fail scope; current registry status is informational and native AMB is qualified by the 0.30 gate",\n',
    ),
]
for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}: {old!r}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
print("Bearing Native Outputs 0.15.1 qualifier made phase-aware for ROSS Studio 0.30")
