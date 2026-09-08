# Approved ROSS Studio UI implementation

The PySide6 UI in `src/ross_frontend/ui` implements the four mockups approved on 2026-09-08.

## Visual contract

- Custom dark title bar: `#103B5D` → `#0B2E49`.
- Sidebar: `#123A59` → `#0F304B`.
- Primary action/selection: `#137FF1`.
- Workspace background: `#F4F8FC`.
- Cards: white with `#CFDDEA` borders.
- Success state: `#16A66B`.
- Solver console: `#071B2B` / `#0E2639`.
- Segoe UI / Inter fallback typography.
- Icons are runtime vector drawings, not raster placeholders, so they remain sharp with DPI scaling.

## Screens implemented

1. **Rotor Model** — dynamic rotor sketch, numbered shaft sections, component tabs, editable shaft table, project inspector, model summary, validation/run actions.
2. **Bearing Studio** — six approved bearing type selectors, geometry/operation/lubrication fields, operating point, K/C table and chart, result tabs and quick actions.
3. **Analysis Results / Campbell** — analysis selector, KPI cards, Campbell chart, mode table, settings, PNG/CSV export.
4. **ROSS Solver Console** — non-blocking solver execution through `QThread`, progress log, execution state, analysis steps, elapsed time and results folder action.

## Functional integration

`Run Analysis` validates `RotorProject`, opens the console, lazily creates `RossBackend`, runs the ROSS solver off the GUI thread and sends the resulting `AnalysisResult` to the Campbell page. The frontend can start without importing ROSS until a calculation is requested.

`Apply to Rotor` in Bearing Studio maps the approved Tilting Pad fields to `TiltingPadBearingSpec`.

The K/C table shown before a real THD calculation is a presentation seed matching the approved mockup. Replacing that seed and the Operating Point placeholders with native `BearingResults` is the next bearing-calculation integration gate; the UI does not treat those seed values as solver output.
