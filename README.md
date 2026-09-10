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

The reference topology contains 15 physical shaft sections, 28 shaft-node positions, 27 effective ROSS `ShaftElement`s and two main radial bearings with flexible-support link nodes 28 and 29.

## Shaft discretization and model view — 0.12.0

Each physical `ShaftSection` carries an explicit `fe_elements` request. This is a **minimum finite-element discretization inside the physical section**, not a nearest-node placement policy.

ROSS Studio builds the shaft topology as:

```text
physical section boundaries
        +
per-section uniform FE subdivision
        +
mandatory exact engineering coordinates
        ↓
NodeInsertionService
        ↓
effective ROSS ShaftElements
```

Bearings, distributed-mass boundaries/centres, concentrated masses, disks, seals, couplings, loads and probes retain exact axial coordinates. Refining a section adds mesh nodes but never moves an engineering entity to a nearby node.

The OP-W60 default remains backward compatible:

```text
15 physical sections
15 requested/base FE elements
+ exact node insertion
= 27 effective ROSS ShaftElements
= 28 shaft nodes
```

The Rotor workspace provides two complementary model views:

- **Engineering 2D** — model-driven selectable sketch with physical geometry, FE node/element overlay, supports, loads, UMP and probes;
- **ROSS Native** — independent audit view generated from the strict ROSS `Rotor` through `Rotor.plot_rotor()`.

The model workspace uses the left sidebar as its single primary navigation. The former duplicate horizontal model-tab bar is intentionally not part of the 0.12 architecture.

## Bearing Studio

### Bearing Studio 2.0 — 0.13.0 tranche

The Bearing Studio workspace now separates **physical bearing identity** from the **ROSS calculation model**. The sidebar opens Bearing Studio directly; there is no intermediate family landing page.

The transaction is:

```text
select physical bearing station (DE / NDE / future station)
        ↓
select model family and qualified ROSS class
        ↓
Calculate
        ↓
Preview only — engineering RotorProject unchanged
        ↓
Apply to Rotor
        ↓
commit exactly the selected bearing transaction
```

`BearingWorkspaceService` resolves every `BearingSpec` to its engineering index, exact axial coordinate, exact ROSS shaft node, current source model and flexible-support ownership. The application no longer uses an implicit `bearing_index=0` for dialogs, scientific services, previews or calculation context.

Changing the selected physical station invalidates an unapplied preview. The Apply gate also verifies that the current station still matches the station captured during Calculate. For the OP-W60 qualification, an NDE BallBearing transaction must leave DE byte-for-byte equivalent at the engineering-domain level and preserve the qualified flexible-support links 28/29 in the strict ROSS rotor.

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

### Axial ThrustPad — 0.11.0 qualified

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

`ThrustPad` is `VALIDATED` in the production capability registry. The lateral THD service still rejects it; axial execution is owned only by the dedicated ThrustPad service.

### Active Magnetic Bearing

`MagneticBearingElement` remains blocked until an explicit actuator, sensor and controller domain is implemented and qualified.

## Frozen desktop executable gate — 0.12.0 qualified

The desktop package uses a production-style PyInstaller onedir build. The exact same frozen executable supports two internal non-interactive qualification modes:

```text
ROSS-Studio --self-test --self-test-output frozen_selftest.json
ROSS-Studio --gui-smoke --gui-smoke-output frozen_gui.json
```

The scientific self-test proves, from inside the packaged runtime:

- ROSS version is exactly 2.3.0;
- the OP-W60 engineering resource is packaged;
- the strict OP-W60 rotor builds with no unresolved node positions;
- native `Rotor.plot_rotor()` generates a real Plotly figure;
- all eight qualified Bearing Studio classes remain executable;
- only `MagneticBearingElement` remains blocked.

The GUI smoke additionally constructs the real `RossStudioWindow` in the frozen runtime and exercises non-modal navigation/capability gating. The 0.12 gate passed on both Linux and Windows. A successful PyInstaller build without successful scientific and GUI runtime gates is not a release pass.

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

## Build frozen desktop application

```bash
pip install -e '.[package]'
python -m PyInstaller --clean --noconfirm packaging/ROSS-Studio.spec
```

The result is an onedir package under `dist/ROSS-Studio/`.

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
python tools/qualify_workspace_012.py
python tools/qualify_bearing_workspace.py
python tools/qualify_op_w60_pipeline.py
python tools/correlate_op_w60_rotordin.py --enforce
python tools/isolate_op_w60_response_differences.py
python tools/isolate_op_w60_conventions.py
```

GitHub Actions runs the same scientific gates. The separate frozen-executable workflow additionally builds Linux and Windows desktop packages and runs the scientific self-test plus GUI startup smoke against the actual binaries. Failures are release gates; tests, tolerances and physical checks must not be weakened merely to obtain a green CI.

## Core architecture

```text
src/ross_studio/
├── app.py                         # desktop shell, explicit station selection and transactional Apply
├── bearing_workspace.py           # physical bearing identity / DE-NDE station mapping
├── bearing_dispatch.py            # class -> scientific service ownership
├── bearing_studio_service.py      # General / Parametric models
├── thd_bearing_service.py         # lateral THD models
├── thrust_pad_service.py          # axial ThrustPad model and Kzz/Czz cache
├── topology.py                    # exact physical node insertion + per-section FE mesh union
├── rotor_scene.py                 # interactive engineering 2D model view
├── rotor_selection.py             # shared sketch/table selection contract
├── ross_native_view.py            # strict Rotor -> native ROSS plot_rotor audit view
├── ross_backend.py                # strict ROSS model assembly
├── analysis_backend.py            # qualified real ROSS analyses
├── services.py                    # capability registry and engineering validation
├── frozen_entry.py                # normal GUI bootstrap + frozen qualification modes
├── frozen_selftest.py             # scientific packaged-runtime gate
├── frozen_gui_smoke.py            # frozen Qt/Bearing Studio startup gate
├── solver_console.py              # execution console
└── pages/
    ├── rotor_model.py
    ├── bearing_studio.py
    ├── thd_results.py
    └── results.py
```
