# Core Rotor Dynamics — incremental feature qualification

Baseline requested: b824a619f27335c17855d05eb35203f4a399f2a8. Its exact tests run 34752025725 and frozen run 34752025796 succeeded on Linux and Windows. No scientific stage was skipped. The Linux package installation step is not applicable on Windows. Existing descendant b0c9a65d fixes are preserved, not rolled back.

This tranche adds a shared source/frozen sentinel harness (`core_qualification.py`). No feature receives a full qualification label just because this harness exits successfully; its declared coverage and missing journeys are explicit in the emitted JSON.

## Changes

- Named material editor, reached from the shaft toolbar. A global material edit validates a candidate rotor before commit; every section sharing that material receives the new properties.
- Explicit shaft resize opt-in. Components retain their absolute mm coordinates; out-of-span edits are rejected without modifying the live model. Default remains read-only, preserving the previous editor contract.
- Independent native ROSS rotor, using literal reference material, dimensions, disk, anisotropic Concent inertia tensor and cross-coupled K/C. Concent is compared with an independently specified rigid-body diagonal M and native DiskElement G, not with the Studio adapter itself.
- Native Static, Modal, Campbell, critical speeds and complex unbalance response comparisons; MAC handles arbitrary eigenvector phase. GUI modal/static tables and Campbell drawing arrays are inspected. Probe amplitude and phase are compared to independent projection of native displacement.
- Save/reopen/recompute and material-result invalidation.
- Conversion round trips cover mm/m, RPM/rad/s, Hz/rad/s, N/mm/N/m, Ns/mm/Ns/m, kg mm²/kg m², degrees/radians, bar/Pa, Celsius/Kelvin. For non-core units this proves the conversion primitive only, not a future editor's wiring.
- Identical harness is a required stage of both frozen jobs; no platform or previous gate removed.

## Numerical interpretation

Parameter sentinels use six decimal digits within the declared GUI precision, with distinct mass/inertia/cross-coefficient values. Expected geometry and matrices are constructed separately with ROSS 2.3.0. Near-zero assembled K entries showed cancellation at about 1e-8 because subtraction of global node positions rounds differently from literal independent element lengths. The matrix absolute floor is explicitly eight machine epsilons times the maximum matrix entry, while rtol remains 1e-12. This bounds floating-point assembly cancellation; it is not an engineering-model uncertainty. Native eigen/root comparisons retain the existing 1e-7/1e-6 relative bounds. Material nu can differ by one ULP because ROSS reconstructs it from E and G; the domain value is checked exactly.

The pipeline's GUI critical speeds are explicitly interpolated 1X Campbell crossings, not native run_critical_speed roots. Native root parity is checked separately. The remaining crossing/display coverage cannot be silently equated with native-root qualification.

## Feature matrix at implementation checkpoint

PASS = executed for the bounded case; GAP = that link still requires evidence. Source harness must be run successfully before using its PASS entries; platform JSON from the new exact SHA is required to close frozen columns.

| Feature | GUI/domain/adapter | Native assembly/numerics | Display | Reopen | Frozen Linux/Windows | Status |
|---|---|---|---|---|---|---|
| Material edit, existing shared Steel identity | PASS | PASS | PASS via downstream modal | PASS | GAP until new runs | Pending platform evidence |
| Hollow cylindrical shaft, two sections, resize at fixed absolute component positions | PASS | PASS | PASS via modal/Campbell | PASS | GAP until new runs | Pending platform evidence |
| DiskElement mass/Id/Ip | PASS editor record | PASS | PASS via modal/response | PASS | GAP until new runs | GAP full page journey |
| Concent independent Ix/Iy/Iz | PASS editor record | PASS | PASS via modal/response | PASS | GAP until new runs | GAP full page journey |
| BearingElement direct cross-coupled K/C | PASS table/service | PASS | PASS via response | PASS | GAP until new runs | GAP full Bearing Studio apply journey |
| Static | PASS model | PASS deformation | PASS max deflection table | GAP complete result set | GAP until new runs | GAP |
| Modal | PASS model | PASS wn/MAC | PASS frequency table | PASS | GAP until new runs | GAP full settings journey |
| Campbell | PASS model | PASS wd | PASS drawing arrays | GAP explicit replay check | GAP until new runs | GAP |
| Critical speeds | GAP native-root GUI path | PASS native roots | GAP interpolated crossing coverage | GAP | GAP until new runs | GAP |
| Unbalance | GAP complete load editor path | PASS amplitude/phase/projection | PASS phase table | PASS | GAP until new runs | GAP |

New Project shaft/bearing creation is still blocked in the historical workspace. This tranche does not disguise that limitation as a complete new-model journey. Complete Core before moving on to Bearing Studio and subsequent blocks. No PR or merge is authorized.
