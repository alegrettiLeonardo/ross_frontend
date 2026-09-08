# ROSS Studio

Desktop engineering interface for [ROSS](https://github.com/petrobras/ross), evolving the RotorDin PySide6 workflow while keeping the scientific model explicit and auditable.

## Run the desktop application

```bash
python -m pip install -e .
ross-studio
```

or:

```bash
python -m ross_frontend
```

The application opens with the approved `WGM20` starter model and the approved ROSS Studio visual system.

## Architecture

```text
PySide6 UI / RotorProject
          |
          v
   AnalysisBackend
          |
          +---- RossBackend (primary)
          |
          +---- legacy RotorDin adapter (migration/reference only)
          |
          v
   RossModelBuilder
          |
          +-- Material / ShaftElement
          +-- DiskElement / PointMass
          +-- BearingElement / rolling bearings
          +-- Cylindrical / PlainJournal / TiltingPad
          |
          v
       ross.Rotor
          |
          +-- static
          +-- modal
          +-- critical speed
          +-- Campbell
```

`Run Analysis` executes `RossBackend` in a Qt worker thread and sends the returned `AnalysisResult` to the results workspace.

The lateral-coordinate conversion is centralized and mandatory: the historical RotorDin lateral plane is **x/z**, while ROSS uses **x/y** and reserves **z** for the axial direction.

See:

- `docs/UI_IMPLEMENTATION.md` for the approved visual/interaction contract.
- `docs/IMPLEMENTATION_STATUS.md` for scientific migration gates and the next implementation slice.
