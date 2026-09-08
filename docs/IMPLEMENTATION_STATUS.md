# RotorDin UI → ROSS integration status

## Implemented in Phase 1

- Solver-neutral `AnalysisBackend` contract.
- Native ROSS 2.3.0 backend and auditable run directories.
- `RotorProject` schema v2 with materials, shaft, disks, point masses and bearings.
- Automatic shaft remeshing at every component position.
- Native conical `ShaftElement` mapping; no cylindrical subdivision approximation.
- Mandatory lateral coordinate adapter: RotorDin `x/z` → ROSS `x/y`.
- Bearing builders for:
  - direct/speed-dependent K/C coefficients;
  - ball bearings;
  - roller bearings;
  - simplified cylindrical hydrodynamic bearings;
  - `PlainJournal` fluid-film bearings;
  - `TiltingPad` fluid-film bearings.
- Initial analyses: static, modal, critical speed and Campbell.
- Conservative adapter for the verified common subset of the previous RotorDin project model.
- JSON audit artifacts (`project.json`, `model.json`, `results.json`) for every run.

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

## Next implementation slice

1. Port the approved PySide6 RotorDin workspace into this repository and bind it to `RotorProject`.
2. Add Bearing Studio editors/results for the six bearing types already supported by the builder.
3. Add forced/unbalance/frequency/time response adapters and Plotly/Qt result views.
4. Implement verified support `n_link` topology and legacy bearing table importer.
5. Add `ross_ext` for foundation dynamic impedance, flexible disks and UMP.
