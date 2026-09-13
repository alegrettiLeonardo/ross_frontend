# ROSS Studio engineering qualification — evidence ledger

**Decision: NOT YET ENGINEERING QUALIFIED.** This is an execution checkpoint, not a release certificate. Individual test PASS statements below refer only to the stated cases. The required ten-part acceptance chain has not been demonstrated for every product feature.

## Identity and initial state

- Repository: alegrettiLeonardo/ross_frontend.
- Branch: feature/ross-studio-engineering-qualification. No main edits or merge; no PR opened because the qualification condition is not satisfied.
- Initial main: 350895a0fff5f877eec51b94a67e4c40c64d8b45 (PR #18). It matched the requested baseline when inspected.
- First correction commit: ca2e2ce1c4da0d0b826c4aa0d80dc32f552bf020.
- Second correction commit: b824a619f27335c17855d05eb35203f4a399f2a8.
- Studio package/source version: 0.30.0; ROSS dependency remains exactly ross-rotordynamics==2.3.0. No upstream-main APIs were substituted.
- Attached ROSS tutorials were consulted as context; installed 2.3.0 constructor signatures and runtime objects are the implementation authority. The uploaded upstream source archive is not the Studio repository.

## Findings, causes and corrections

| ID | Risk | Finding / cause | Change and evidence |
|---|---|---|---|
| EQ01 | CRITICAL | Explicit Kyy=0/Cyy=0 was treated as absent by `value or x_direction`, inventing stiffness/damping | Preserve explicit zeros in backend, Bearing Studio and foundation assembly; regression inspects native coefficients for bearing and support |
| EQ02 | CRITICAL | Seal coefficient preview survived parameter edits and could apply old physics | Parameter edits clear preview/plots and disable Apply; Qt regression |
| EQ03 | CRITICAL | Results on several pages outlived model edits | Fingerprint guards added to deterministic, fault, AMB, stochastic, MultiRotor and engineering output pages; asynchronous stale completion rejected in covered paths. Coverage remains incomplete for all editing journeys |
| EQ04 | HIGH | Frozen selftest and external verifier still expected AMB to be blocked | Require actual MagneticBearingElement, calculate/apply and independent K/C parity. Preserve all existing scientific frozen stages |
| EQ05 | HIGH | Frozen GUI fixture expected obsolete single-station coupling behavior | Use finite two-node interval and verify native CouplingElement, node adjacency and length |
| EQ06 | HIGH | Gas seal adapters passed keyword names absent in pinned ROSS 2.3.0 | Correct shaft radius conversion and native names for Labyrinth, HolePattern and Hybrid; execute each native model, coefficients and rotor inclusion |
| EQ07 | CRITICAL | NaN physical values passed comparison-based validation | Recursive finite check before scientific build, including nested metadata; four entity regressions |
| EQ08 | HIGH | Duplicate support identities / unordered bearing speed tables ambiguous | Reject with received values and corrective instructions; regressions |
| EQ09 | CRITICAL | HybridSeal may return after iteration limit without converging stage mass flows | Reject nonfinite/absent residual or residual above requested native tolerance; actual one-iteration failure regression; no tolerance relaxation |
| EQ10 | MEDIUM | Schema migrations inserted defaults with no retained record | Record added paths/values and old/new schemas in persisted engineering warnings; round-trip regression |
| EQ11 | MEDIUM | Frozen workflow omitted main and qualification branch, artifacts lost after failures | Add branch triggers, Linux runtime libraries, always-upload evidence with exact SHA; no continue-on-error |

## Architecture inventory

All entries are executable source paths, not claims of complete qualification. Domain values primarily use mm/rpm and SI K/C; adapters own conversion to native SI. Results retain native ROSS objects; project files retain model inputs, not a serialized native solver.

| Area / files | Responsibility; inputs → outputs; dependencies | State and principal residual risk |
|---|---|---|
| Frontend `app.py`, `app_legacy.py`, `ui_shell.py`, `page_registry.py`, `pages/` | Qt navigation, editors, workers, display; ProjectModel → user actions/results | Active composition replaces legacy module classes at runtime; legacy code is used, not dead code. Duplicate routing and page layers complicate lifecycle audit |
| Domain `domain.py`, `topology.py` | Entity validation, physical sections/stations → topology and specs | Explicit finite values and topology; exhaustive invalid-input matrix not completed |
| Project model `models.py` | GUI summaries and engineering model → page data | Derived presentation fields can diverge unless refresh paths are exercised |
| Persistence `project_io.py`, `project_file_service.py`, controller | JSON schemas 1/2/3, save/load/import → ProjectModel | Lossless tested fixtures; migration defaults recorded. All analysis-page settings are not demonstrated persistent |
| Backend `ross_backend_base.py`, `ross_backend.py`, `ross_compat.py` | Specs → materials, Shaft/Disk/PointMass/Bearing/Seal/Coupling and Rotor | Base and extension both active; strict node insertion. Independent reference proof covers compact linear rotor, not all combinations |
| Analysis `analysis_pipeline.py`, `analysis_backend.py` | Operating case/loads → native static/modal/Campbell/response, audits | OP-W60 gates exist; warning visibility and invalid models require further coverage |
| Bearing Studio `bearing_studio_service.py`, inputs, workspace | Direct K/C, ball/roller/cylindrical/AMB inputs → preview/spec/native coefficients | Runtime gates exist; broad parameter envelope/reference comparisons incomplete |
| THD `thd_bearing_service.py`, `thrust_pad_service.py` | PlainJournal/TiltingPad/SFD and separate ThrustPad → solved native coefficients | Real 2.3.0 classes used; convergence/thermal validation across design envelope incomplete |
| Seal Studio `seal_studio_service.py`, seal page | Pressure/temperature/gas/geometric inputs → direct or native gas seal and coefficients | Constructor bugs fixed; full independent thermofluid reference and frozen gas-seal journeys pending |
| Foundation `foundation_qualification.py`, foundation page, backend | Linked support M/K/C or frequency tables → explicit support DOFs/condensed coefficients | Existing reference gates; general imported foundation matrices are not an arbitrary full FE foundation solver |
| Faults `fault_analysis.py`, faults page | Misalignment/rubbing/crack inputs → native time results | Actual short GUI runs tested; long-time convergence and independent amplitudes not qualified |
| AMB `amb_analysis.py`, AMB page, qualification | Electromagnetic/controller inputs → native bearing and sensitivity | Assembly parity and real sensitivity/time plots tested; short case is not a stability/ISO certification |
| Static/Modal `static_modal_analysis.py`, decoupled service/page | Independent requests → static/modal/Campbell results and plots | Separate transactions and stale guards; full scalar/table/plot inspection pending |
| Time/Frequency `time_frequency_analysis.py`, native catalogs/page | Frequency, unbalance, time, HB requests → native outputs | Singular/pseudoinverse native warnings observed; engineering acceptance of these cases unresolved |
| Stochastic `stochastic_analysis.py`, catalogs/page | Seed/distributions/requests → ST_Rotor and sample results | Reproducibility and runtime fixtures; uncertainty calibration and complete GUI edit matrix pending |
| MultiRotor `multirotor/`, page | Rotors, gears and request → native MultiRotor | Three-shaft modal tested; unsupported routes blocked. Not all analyses valid for native MultiRotor |
| Engineering outputs `engineering_outputs.py`, figures, PDF/page | Analysis result + model → traceable tables/HTML/PNG/PDF | Some capabilities explicitly NOT_QUALIFIED; export provenance exists. Full graphic correctness across all families pending |
| Rotor Builder `model_builder_service.py`, entity dialogs | Transactional edits → validated physical model | Exact insertion rather than nearest-node placement; comprehensive GUI-to-solver scalar sentinels pending |
| Import/export `legacy_import.py`, project controller | Supported IRDIN / labelled ASCII → model; native JSON → save | Unknown layouts fail closed; not a generic parser for every Dyrobes version |
| Frozen `packaging/ROSS-Studio.spec`, `frozen_*.py`, qualifiers | PyInstaller artifact → in-process application/solver/IO evidence | Original regression diagnosed; current Linux/Windows CI must be checked on exact final HEAD |
| Tests `tests/`, `tools/` | Unit/integration/native reference/Qt + qualification scripts → assertions and artifacts | Broad regression suite is necessary but insufficient for entire engineering certificate |

## Numerical evidence and tolerances

`independent_parity.csv` records Studio/direct maxima, maximum absolute and relative-infinity errors, tolerances and PASS/FAIL. Both rotors are built separately: six 0.1 m hollow steel shaft elements, two anisotropic K/C supports and one disk. The direct fixture instantiates ROSS classes without the Studio builder.

Mass is 15.548838024402972 kg. M/K/C/G, nodes, mass, frequencies, unbalance and critical speeds agreed to the recorded precision. Modal vectors are compared with MAC because eigenvectors have arbitrary complex phase. MAC error was 6.66e-16 in this run.

Assembly rtol=1e-12 permits floating-point accumulation only; it is not a physical modeling uncertainty. Modal/response rtol=1e-7 and critical rtol=1e-6 accommodate iterative eigensolver/root solving. Absolute floors apply to near-zero values. This is code parity, not experimental validation or FE convergence. No golden or solver equation was changed.

Physical tests check M/K symmetry in the conservative fixture, G antisymmetry, positive-definite M, exact zero-unbalance response, linear unbalance scaling, frequency reduction with added disk mass and frequency increase with stiffer supports. Additional gyro branch-tracking and support-removal cases remain necessary.

`benchmarks.json` records SMALL/MEDIUM/LARGE (6/24/60 elements, 42/150/366 DOFs), build/modal/Campbell/unbalance/time/GUI/save/load times and process peak RSS. Runs use five speed points and 21 time samples; they are small workloads, not full production sweeps. Measurements were made on a shared machine; RSS is cumulative and is not allocated to individual operations. No performance improvement is claimed.

## CI and frozen failure investigation

- Initial main tests run 34722362858: SUCCESS.
- Original frozen run 34721996894: FAILURE on Linux job 103629485900 and Windows job 103629486055. Exact scientific failure: `RuntimeError: Frozen Bearing Studio capability mismatch: missing executable=[], unexpected executable=['MagneticBearingElement'], blocked=[].` Downstream MultiRotor/Foundation were skipped because of that failure.
- ca2e2ce tests 34723484334: SUCCESS. Frozen 34723484305: FAILURE; after internal contract repair, external `qualify_frozen_binary.py` still asserted the obsolete executable set. Jobs 103633426604 and 103633426672. Artifacts retained.
- b824a619 local full suite: 233 tests, 0 failures, 0 errors, 0 skipped, 134.944 s in JUnit. PyInstaller build completed. CI tests 34752025725 and frozen 34752025796 were launched; see subsequent execution status evidence for conclusions.
- Five workflow files inspected. Tests/frozen are active qualification gates. Historical fix-native-completion-030, package-source-0141 and project-file-io-0142 workflows target old branches/versions; they do not constitute current release evidence. Linux apt stage on Windows is intentionally not applicable, distinct from a scientific stage skipped after failure.

Warnings requiring explicit engineering review: unavailable REFPROP causes native ccp to choose HEOS/CoolProp; low slenderness in OP-W60; THD covariance estimate; singular/pseudoinverse warnings in some time/frequency fixtures; NumPy matrix deprecations. Native warnings are not evidence of physical correctness.

## Qualification matrix

P = executed evidence for limited cases, not full-area PASS. GAP = incomplete chain. Frozen column refers to feature-specific journeys; generic binary startup does not qualify each component. **No entire row is QUALIFIED under the requested ten conditions yet.**

| Area | Backend | Frontend | Integration | Persistence | Frozen | Physical/reference validation | Status |
|---|---|---|---|---|---|---|---|
| Shaft | P | P | P | P | GAP | P compact rotor | NOT QUALIFIED |
| Disks/PointMass/Concent | P | P | P | P | GAP | P | NOT QUALIFIED |
| Bearings General | P | P | P | P | GAP | P | NOT QUALIFIED |
| THD | P | P | P | P | GAP | GAP design envelope | NOT QUALIFIED |
| Seals | P | P | P | P | GAP gas models | GAP independent thermofluid | NOT QUALIFIED |
| Coupling | P | P | P | P | GAP final platforms | GAP independent matrices | NOT QUALIFIED |
| Foundation | P | P | P | P | GAP final platforms | P | NOT QUALIFIED |
| UMP | P | P | P | P | GAP | P analytical case | NOT QUALIFIED |
| AMB | P | P | P | P | GAP sensitivity | P assembly, GAP dynamics | NOT QUALIFIED |
| Faults | P | P short runs | P | GAP requests | GAP | GAP reference amplitudes | NOT QUALIFIED |
| Static/Modal/Campbell/Critical | P | P | P | P model | GAP final platforms | P compact reference | NOT QUALIFIED |
| Time/Frequency/HB/UCS/Clearance | P | P | P | GAP requests | GAP final platforms | GAP all references | NOT QUALIFIED |
| Stochastic | P | P | P | GAP requests | GAP final platforms | GAP distributions/reference | NOT QUALIFIED |
| MultiRotor | P | P | P | P | GAP final platforms | GAP full analysis set | NOT QUALIFIED |
| Engineering Outputs | P | P | P | GAP all configuration | GAP final platforms | GAP full graphics inspection | NOT QUALIFIED |

## Residual gates / next work

1. Close exact final HEAD CI and both frozen jobs; do not treat pending/skipped stages as PASS.
2. Complete seven user journeys with scalar sentinels for every critical editable entity, save/close/reopen/recompute and compare actual displayed/exported arrays.
3. Full unit round-trip matrix (mm/m, rpm/rad/s, Hz, stiffness/damping, inertias, phase, pressure and temperature), including every advanced editor, remains incomplete.
4. Extend independent numerical references to all specialized bearings/seals/foundation/coupling, AMB dynamics, faults, stochastic and MultiRotor; justify convergence and physical applicability.
5. Seal/fault plot failures now display native errors; complete the audit of remaining legacy exception paths. Audit all occurrence contexts in `audit_occurrences.txt`; the scan itself is not proof of absence of fallbacks. `pass` in mixin subclasses and exception marker classes is harmless; failures re-raised by solver stage wrappers are not swallowed; optional-capability None returns must remain visible as unavailable.
6. Establish warning acceptance policy: no silent scientific fallback or false Ready, including upstream pseudoinverse and fluid EOS selection.
7. Complete stale-output checks for every model field, async race and open export dialog; timer guards alone do not prove the complete requirement.
8. Persist and migrate relevant analysis requests, beyond the model fixtures already covered.
9. Isolated performance measurements and mesh/time-step convergence on realistic large machines, with operation-specific memory, remain outstanding.

No complete product feature is claimed ENGINEERING QUALIFIED. Scoped numerical, physical and regression successes are listed above so they can be reproduced without confusing them with a release certificate.

## Additional executed evidence

All 23 scientific commands from tests.yml completed locally with exit code 0 (`qualifier_runs_b824.json`). The local b824 binary passed all nine JSON gates including MultiRotor and Foundation (`frozen_local_b824.json`). These Linux results do not imply Windows PASS or validation of later source changes.
