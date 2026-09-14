# Bearing Studio — first Feature Qualification increment

Predecessor Core implementation b4ed1558d3de86b3e0155c9e6eb21e31e51c30d6 closed source CI 34787127571 (245 tests; every step successful) and frozen run 34787127521, Linux job 103804507019 and Windows job 103804506866. Each platform executed 103 Core comparisons. Only the Linux apt step was skipped on Windows as not applicable. Core scope remains the existing-model fixture documented separately; this is not product-wide qualification.

## HIGH finding: scalar bearing result disappears

The real Ball/Roller Calculate→Apply journey calculated and assembled correct native K/C, but Apply reconstructed BearingModel only from spec.coefficients. Scalar calculations are persisted in spec.kxx…cyy with an empty frequency table. The output therefore disappeared after Apply and reopen. Two independent native K/C regression cases reproduced failure (zero GUI rows instead of one).

Correction: the presentation model retains a row of the persisted scalar coefficients for direct K/C and calculated Ball/Roller models. The scientific domain remains scalar; no frequency table is inserted and no solver is replaced. Other native models do not receive fabricated scalar outputs. The displayed RPM uses the exact operating-case value for this row.

Sentinels: 9 rolling elements; diameter/length 23.456789 mm; load 1234.56789 N; angle 13.456789 degrees. Independent ROSS 2.3.0 BallBearingElement/RollerBearingElement reference K and C are compared with final assembled elements at 123.456 rad/s using rtol=atol=1e-12. Controller reopen preserves K and C exactly and the formatted Kxx result remains visible. Tests failed before the fix and passed after it. Twenty related tests passed locally; the shared two-case runner also passed after extraction.

The same runner is mandatory inside the frozen GUI process; the external binary checker requires both model cases. Exact new-head CI and frozen outcomes must be inspected, not inherited from Core.

| Feature | GUI input/unit adapter | Native element K/C | Apply/reopen display | Full solver→GUI results | Frozen new HEAD | Feature status |
|---|---|---|---|---|---|---|
| Ball | PASS | PASS | PASS | GAP | GAP pending CI | NOT QUALIFIED for full feature chain |
| Roller | PASS | PASS | PASS | GAP | GAP pending CI | NOT QUALIFIED for full feature chain |
| Cylindrical | Existing service gates only | No new independent case in this increment | GAP | GAP | GAP | NOT QUALIFIED |
| Other Bearing Studio models | Follow their assigned THD/AMB blocks | GAP full feature chain | GAP | GAP | GAP | NOT QUALIFIED |

No new full Feature Qualification claim is made. Next work is the complete solver/result chain for these models, independent Cylindrical parameter/table/assembly comparison, and input-error/preview invalidation cases. Flexible supports are assigned to Foundation; THD and AMB retain their separate ordered blocks.

## Second increment: independent rotor, full GUI solve and stale-input rejection

The first increment 2d038b4a79c86dd7f515acdeb685ad29c0a3a64f passed source run 34788195492 (job 103807435906), and frozen run 34788195485 (Linux 103807436024, Windows 103807435942). No scientific stage skipped.

CRITICAL finding: editing a visible input after Calculate did not invalidate the calculation context or disable Apply. All three new native cases reproduced the stale Apply state. The scientific snapshot checked the rotor but omitted the input editor snapshot. Fixed by emitting input-change notifications for scalar/vector/choice controls and K/C table edits/removals, invalidating previews via the existing application handler, and comparing a deep copy of calculated inputs at the Apply boundary. Formulation/coordinate selectors also invalidate the preview. A zero-load rejection and a suppressed-notification edit verify that invalid/stale input cannot commit.

The shared source/frozen runner now includes Ball, Roller and Cylindrical. It compares element and assembled K/C at nine speeds against a separately constructed ROSS rotor. Cylindrical uses five frequency stations and four interpolation points, with independent literal reference geometry/load/viscosity. It invokes the real window.run_analysis handler and SolverConsole (small requested grids, native solver unchanged), compares modal frequencies and complex unbalance response, inspects the modal table, reopens through the controller and recomputes. Scope: one existing station, rigid ground support, native default damping for rolling models. Other bearing models, support links and expanded fluid-model ranges are excluded.

Executed locally: three expanded cases passed; nineteen related tests passed with the input-invalidation fix; final three cases with invalid-input and suppressed-notification checks passed. No numerical tolerance was loosened. The new exact HEAD still requires complete source and frozen gates before declaring its bounded features qualified.

| Feature, declared case | Inputs/native K/C | Assembly/native solver | GUI modal result | Reopen/recompute | Error/stale gates | New frozen evidence |
|---|---|---|---|---|---|---|
| Ball | PASS | PASS | PASS | PASS | PASS | GAP until exact SHA runs |
| Roller | PASS | PASS | PASS | PASS | PASS | GAP until exact SHA runs |
| Cylindrical, five stations/interpolation | PASS | PASS | PASS | PASS | PASS | GAP until exact SHA runs |

## CI regression closure

Source run 34828754596 at b6f30d971e0c5e8627c0682b1994788edd636c48 failed in test_controller_new_creates_truthful_empty_workspace: the new input notification wiring assumed input_panel existed on EmptyBearingStudioPage. Subsequent qualification scripts were skipped, so that source run is FAIL, not partial PASS. The empty page legitimately has no input editor; wiring now explicitly excludes that page type. Its disabled scientific controls remain unchanged.

The shared frozen regression now invokes controller.new() (engineering domain is explicitly None), then loads its populated fixture and executes each native case. This closes the missing frozen path that allowed the source-only failure. Twelve project-I/O and bearing tests passed after correction. The case now also compares every displayed K/C table column and all converted bearing metadata sent through the adapter. The external binary checker requires at least 40 successful numerical comparisons per bearing case. Exact successor CI remains required.
