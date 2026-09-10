# ROSS Studio

Desktop scientific-engineering interface for [ROSS Rotordynamics](https://github.com/petrobras/ross), focused on rotordynamics workflows for rotating electrical machines.

## Scientific baseline

This project is currently pinned to:

- Python 3.12 in CI
- PySide6 6.7+
- `ross-rotordynamics == 2.3.0`

Do not upgrade the ROSS version without a dedicated compatibility and requalification tranche.

## Qualified rotor workflow

The OP-W60 reference case is exercised through the real ROSS pipeline:

```text
strict Rotor
   ↓
Static
   ↓
Modal
   ↓
Critical Speeds
   ↓
Campbell
   ↓
Unbalance Response
   ↓
Probes
   ↓
Results / GUI / Solver Console
```

The reference topology contains 15 physical shaft sections, 28 shaft-node positions, 27 ROSS `ShaftElement`s and two main radial bearings with flexible-support link nodes 28 and 29.

## Bearing Studio

### General / Parametric

Qualified classes:

- `BearingElement` — direct or speed-dependent K/C
- `BallBearingElement`
- `RollerBearingElement`
- `CylindricalBearing`
- `CylindricalBearing` with flexible support through the qualified solved-K/C `BearingElement(n_link=...)` adapter

### Lateral THD

Qualified classes:

- `PlainJournal`
- `TiltingPad`
- `SqueezeFilmDamper`

The lateral THD execution policy is:

```text
native ROSS 2.3 THD / Reynolds solve
        ↓
solved lateral K/C versus speed
        ↓
BearingElement cache
        ↓
n_link when a qualified flexible support exists
        ↓
Rotor ROSS
```

The native THD element is retained for field post-processing. Rotor analyses consume the solved K/C cache and do not rerun the expensive THD solution.

### Axial ThrustPad — 0.11.0 gate

`ThrustPad` is treated as an axial model and is never reduced to lateral Kxx/Kyy.

Its physical contract is:

```text
native ROSS 2.3 ThrustPad
        ↓
pressure / temperature / film solution
        ↓
Kzz(speed), Czz(speed)
        ↓
independent axial BearingElement at the selected shaft station
        ↓
ROSS z DOF
```

The existing radial bearing at that station remains a separate element. Its lateral K/C and flexible-support `n_link` are preserved. A lateral support link is not reused for thrust dynamics: ROSS Studio blocks that topology until an explicit axial-support Kzz/Czz contract exists.

`ThrustPad` remains capability-gated until the scientific, Qt end-to-end, strict-builder and CI release gates are all green on the same production registry state.

### Active Magnetic Bearing

`MagneticBearingElement` remains blocked until an explicit actuator, sensor and controller domain is implemented and qualified.

## Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -e .
ross-studio
```

or:

```bash
python -m ross_studio
```

## Qualification

```bash
pip install -e '.[dev]'
python -m compileall -q src tests tools
python -m pytest -q -ra
python tools/qualify_ump.py
python tools/qualify_concentrated.py
python tools/qualify_bearing_studio.py
python tools/qualify_thd_bearing_studio.py
python tools/qualify_thrust_pad.py
python tools/qualify_op_w60_pipeline.py
python tools/correlate_op_w60_rotordin.py --enforce
python tools/isolate_op_w60_response_differences.py
python tools/isolate_op_w60_conventions.py
```

GitHub Actions runs the same gates and publishes the engineering qualification JSON/CSV artifacts. Failures are treated as release gates; tests, tolerances and physical checks must not be weakened merely to obtain a green CI.

## Core architecture

```text
src/ross_studio/
├── app.py                         # desktop shell, explicit service dispatch and transactional Apply
├── bearing_dispatch.py            # class -> scientific service ownership
├── bearing_studio_service.py      # General / Parametric models
├── thd_bearing_service.py         # lateral THD models
├── thrust_pad_service.py          # axial ThrustPad model and Kzz/Czz cache
├── ross_backend.py                # strict ROSS model assembly
├── analysis_backend.py            # qualified real ROSS analyses
├── services.py                    # capability registry and engineering validation
├── solver_console.py              # execution console
└── pages/
    ├── rotor_model.py
    ├── bearing_studio.py
    ├── thd_results.py
    └── results.py
```
