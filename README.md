# ROSS Frontend

Desktop engineering interface for [ROSS](https://github.com/petrobras/ross), evolving the existing RotorDin PySide6 workflow while keeping the scientific model explicit and auditable.

## Architecture

```text
PySide6 UI / Project Model
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

The lateral-coordinate conversion is centralized and mandatory: the historical RotorDin lateral plane is **x/z**, while ROSS uses **x/y** and reserves **z** for the axial direction.

See `docs/IMPLEMENTATION_STATUS.md` for migration gates and the next implementation slice.
