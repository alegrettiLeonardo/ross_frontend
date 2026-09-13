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
