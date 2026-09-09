# ROSS Studio — Engineering checkpoint 0.7.0

This checkpoint is intentionally created before the next engineering implementation tranche.

## Approved Bearing Studio interaction

The Bearings entry is organized in three engineering groups. A group selection opens a second screen where the user selects and configures the concrete ROSS class.

### General / Parametric

- `BearingElement`
- `BallBearingElement`
- `RollerBearingElement`
- `CylindricalBearing`

Purpose: coefficients supplied directly or computed from a simpler analytical/parametric model.

### Thermo-Hydro-Dynamic (THD)

- `PlainJournal`
- `TiltingPad`
- `ThrustPad`
- `SqueezeFilmDamper`

Purpose: coefficients obtained from Reynolds-equation-based numerical/analytical models, with thermal coupling where supported by the installed ROSS API.

### Active Magnetic Bearings (AMB)

- `MagneticBearingElement`

Purpose: dynamic coefficients derived from electromagnetic/actuator parameters and the configured controller model. No AMB result may be synthesized when the installed ROSS capability or required controller inputs are unavailable.

## Engineering invariants for the next tranche

- No widget calls ROSS directly.
- Bearing-group/class availability is capability-gated from the installed ROSS version.
- Unsupported classes are shown as unavailable/planned and never execute fake calculations.
- Domain data remain SI; UI units are converted by the application unit service.
- Heavy bearing calculations stay off the Qt GUI thread.
- Applying K/C to the rotor requires a valid/converged bearing result.
- The approved UI language and the real project/domain model replace mockup-only data.

## Next implementation scope

1. Bearing group landing page.
2. Group-to-class navigation and class-specific editors.
3. General/Parametric, THD and AMB capability registry integration.
4. Remove remaining hard-coded demonstration identity from production UI.
5. Continue production editors for rotor/shaft/disks/seals/supports/couplings/loads/probes.
6. Preserve the scientific boundary: UI → services → domain → backend → ROSS.
