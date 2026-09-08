# RotorDin UI → ROSS integration status

## Implemented

### Phase 1 — scientific backend foundation

- Solver-neutral `AnalysisBackend` contract.
- Native ROSS 2.3.0 backend and auditable run directories.
- `RotorProject` schema v2 with materials, shaft, disks, point masses and bearings.
- Automatic shaft remeshing at every component position.
- Native conical `ShaftElement` mapping; no cylindrical subdivision approximation.
- Mandatory lateral coordinate adapter: RotorDin `x/z` → ROSS `x/y`.
- Bearing builders for direct/speed-dependent K/C, ball, roller, cylindrical, `PlainJournal` and `TiltingPad`.
- Initial analyses: static, modal, critical speed and Campbell.
- Conservative adapter for the verified common subset of the previous RotorDin project model.
- JSON audit artifacts (`project.json`, `model.json`, `results.json`) for every run.

### Phase 2 — approved ROSS Studio desktop workspace

- Approved frameless title bar, exact central color tokens, left navigation, toolbar and status strip.
- Dynamic 2D rotor sketch with stepped/conical diameters, numbered shaft sections, disks, bearings and supports.
- Editable Shaft Segments table bound to `RotorProject`.
- Project Information, Model Summary and Quick Actions panels.
- Bearing Studio matching the approved mockup:
  - Coefficient K/C;
  - Ball Bearing;
  - Roller Bearing;
  - Cylindrical;
  - Plain Journal;
  - Tilting Pad;
  - geometry, operation and lubrication/model inputs;
  - operating point, K/C, pressure, temperature, film thickness, journal position and convergence result tabs.
- `Apply to Rotor` maps the Tilting Pad form to `TiltingPadBearingSpec`.
- Campbell results workspace with KPI cards, mode table, synchronous line, critical-speed markers and PNG/CSV export.
- `AnalysisResult` updates Campbell curves and critical-speed values after a real ROSS run.
- Approved ROSS Solver Console implemented with `QThread`; the GUI remains responsive while ROSS executes.
- Desktop entry points: `ross-studio` and `python -m ross_frontend`.
- Offscreen PySide6 smoke tests plus visual-contract regression tests.

## Explicit migration gates

The legacy adapter intentionally rejects the following until their physics are mapped and validated:

- ribbed/equivalent RotorDin shaft sections;
- distributed masses;
- concentrated masses with rotational inertias whose axis convention has not been verified;
- legacy COEF/TABLE bearing files;
- RotorDin support chains;
- force/probe response definitions;
- foundation M/C/K and dynamic impedance;
- flexible disks and UMP.

This fail-closed behavior is intentional: migration must not silently alter the physical model.

## Bearing Studio scientific gate

The initial K/C and Operating Point values displayed before a native bearing solve are presentation seeds that reproduce the approved mockup. They are **not** exported or identified as ROSS solver output. The next bearing slice must replace them with native ROSS `BearingResults` and populate Pressure, Temperature, Film Thickness, Journal Position and Convergence from the actual bearing calculation.

## Next implementation slice

1. Wire native ROSS bearing calculations and `BearingResults` into Bearing Studio, starting with direct K/C, rolling bearings, `PlainJournal` and `TiltingPad`.
2. Add forced response, unbalance response, frequency response and time response adapters/results.
3. Implement verified support `n_link` topology and legacy bearing table importer.
4. Add project deserialization/migration to complement the implemented JSON save path.
5. Add `ross_ext` for foundation dynamic impedance, flexible disks and UMP.
