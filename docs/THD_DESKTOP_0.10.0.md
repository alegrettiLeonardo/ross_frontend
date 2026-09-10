# THD desktop qualification

Baseline: `612069bb9b4f3613be098a676dc4b5c8ed0af08a`; main CI run
34420814483 succeeded, including all scientific gates and artifact publication.
Candidate pre-promotion CI run `34465849721` also succeeded with the complete
THD desktop workflow enabled only for the qualification test. After that gate,
PlainJournal, TiltingPad and SqueezeFilmDamper were promoted in the production
registry and the test-only capability override was removed. The complete
post-promotion CI is the release gate before merge. No ROSS upgrade:
`ross-rotordynamics==2.3.0` remains pinned.

## Workflow

Select THD, select PlainJournal / TiltingPad / SqueezeFilmDamper, then Calculate.
The scrollable dialog contains the complete model-specific input contract in
engineering units. Default geometries/loads are examples and are identified as
such; they do not calibrate the imported OP-W60. Speed stations are an explicit,
positive, strictly increasing comma-separated vector (rpm).

The application routes the selected class through an explicit service map. A Qt
worker performs the native calculation while the modal progress window remains
responsive. Native ROSS does not offer safe mid-solve cancellation. Calculate
invalidates the previous pending Apply. Exceptions are reported without applying
partial results.

Preview keeps all eight K/C components at every speed; the selected row is the
nearest solved station to the project rated speed. Both stiffness and damping
plots use the actual table and separate scales. Field tabs select speed and,
where applicable, pad. Native dimensional matrices appear as colored cell grids
with exact values and explicit grid-index axes. No interpolated or invented
pressure/temperature fields are generated.

Apply uses the producer stored in the calculation context. It validates a copy
before changing the engineering model and rejects a result if rotor inputs or
selected class changed. The applied class is BearingElement; provenance remains
in source_model. The native element is retained in the desktop session after
Apply. Native fields are not serialized into the rotor; solved K/C and complete
engineering/normalized input metadata are retained. Reopening a serialized rotor
therefore requires a fresh Calculate to restore native field views.

## Unit traceability

| Dialog key | Scientific boundary / ROSS argument |
|---|---|
| speed_rpm | Q_(rpm, RPM) → frequency (rad/s) |
| journal_diameter_mm | journal_diameter_m; radius = diameter/2 for PlainJournal/SFD |
| radial_clearance_um | radial_clearance_m → radial_clearance |
| axial_length_mm | axial_length_m → axial_length |
| pad_axial_length_mm | pad_axial_length_m → pad_axial_length per pad |
| pad_thickness_mm | pad_thickness_m → pad_thickness |
| n_pad / n_pads | n_pad / repeated per-pad arrays |
| pad_arc_deg | PlainJournal pad_arc_length (degrees); TiltingPad Q_(deg) |
| preload / offset | preload / pre_load; offset per pad |
| pivot_angles_deg | Q_(deg) → pivot_angle |
| geometry / lubricant | native geometry / lubricant |
| reference_temperature_c | PlainJournal reference_temperature (°C) |
| oil_supply_temperature_c | Q_(degC) → TiltingPad oil_supply_temperature |
| fxs_load_n / fys_load_n | PlainJournal loads; TiltingPad load vector for determine_eccentricity |
| groove_factor | one native fraction per pad |
| sommerfeld_type | native integer 1 or 2 |
| initial_eccentricity_ratio / initial_attitude_angle_deg | initial_guess = [epsilon, radians] |
| method / operating_type | native method / operating_type |
| oil_flow_l_min | Q_(L/min) → oil_flow_v |
| oil_supply_pressure_bar | oil_supply_pressure_pa → oil_supply_pressure |
| elements_circumferential / elements_axial | native film volume counts |
| equilibrium_type / eccentricity_ratio / attitude_angle_deg | native equilibrium mode / eccentricity / Q_(deg) |
| thermal_type / nx / nz | native thermal mode and volume counts |
| cavitation | native SFD cavitation flag |

Metadata includes engineering_input, normalized_input (explicit ROSS mixed-unit
contract), si_input (dimensional SI audit), geometry, lubricant, discretization,
operating_condition, speed_rpm, ross_api_contract and solved_kc_cache.

## Scientific limits discovered in the pinned source

- TiltingPad `_calculate_performance` appends the selected pad's `h_pivot` into
  `minH_list`. That is **not a global film minimum**. The UI labels it as pivot
  film thickness; global h_min is unavailable. Pressure/temperature extrema use
  all stored pads, not only ROSS's selected-pad scalar summary.
- These native result contracts do not preserve film-thickness distributions.
  PlainJournal circular h_min and SFD h_min use the existing geometric expression
  c(1-epsilon), with an explicit summary and no invented distribution.
- SFD supplies pressure maxima, but no pressure or temperature field. It does not
  provide an optimization history. Missing quantities say
  `Not available for this ROSS model`.
- PlainJournal OptimizeResult supplies optimizer iterations and success when
  available. Histories can contain objective evaluations, especially for
  TiltingPad; their lengths are not mislabeled as iteration counts.
- The backend still handles TiltingPad's ndarray `self.K` by invoking the ROSS
  base BearingElement evaluator. No native THD solve runs during rotor analysis.
- Qualification covers the explicit test inputs and ROSS modes; finite output
  does not establish mesh convergence, operating-envelope validity, thermal
  convergence for every possible input, or experimental calibration.

## Gates

`tests/test_thd_desktop_010.py` uses the **production capability registry**,
actual dialogs, clicked Qt buttons, worker execution, native ROSS, two speed
stations per lateral class, preview field data, Apply, flexible support, strict
builder and finite modal results. It also asserts that the three lateral classes
are `VALIDATED`, while ThrustPad remains `PLANNED` and AMB remains `BLOCKED`.
General and all pre-existing scientific tests remain active. There is no
pre-promotion registry monkeypatch after capability promotion.

The CI artifact includes `thd_desktop_qualification.json` and extends
`thd_bearing_studio_qualification.json` with desktop gates, input contracts,
convergence and field availability. All prior UMP, Concent, OP-W60, golden and
isolation gates remain unchanged. A green complete CI on the promoted production
registry is mandatory before merge into `main`.