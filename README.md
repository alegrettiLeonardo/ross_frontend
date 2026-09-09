# ROSS Studio

Desktop engineering interface for [ROSS](https://github.com/petrobras/ross), focused on rotordynamics workflows for rotating electrical machines.

## Approved UI baseline

The branch `feature/approved-ross-studio-ui-20260908` implements the four approved reference screens:

- Rotor Model / WGM20 model editor
- Bearing Studio / tilting-pad bearing workflow
- Analysis Results / Campbell diagram
- ROSS Solver Console

Fields, labels, navigation groups, design colors and engineering icons are encoded as an explicit UI contract so later solver integration does not change the approved presentation inadvertently.

## Stack

- Python 3.10+
- PySide6 6.7+
- ROSS (`ross-rotordynamics`) 2.4+

## Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -e .
ross-studio
```

or:

```bash
python -m ross_studio
```

## Tests

```bash
pip install -e '.[dev]'
pytest
python -m compileall -q src tests
```

## Architecture

```text
src/ross_studio/
├── app.py                 # main desktop shell and navigation
├── theme.py               # approved colors and Qt stylesheet
├── icons.py               # deterministic vector-like engineering icons
├── models.py              # WGM20 UI data contract
├── ui_shell.py            # sidebar, toolbar, cards and status bar
├── charts.py              # rotor sketch, bearing and Campbell graphics
├── solver_console.py      # approved execution-console modal
└── pages/
    ├── rotor_model.py
    ├── bearing_studio.py
    └── results.py
```

The current milestone establishes the approved UI and interactions. Binding every editor and result to live ROSS calculations is kept behind the next backend-integration milestone so the visual contract remains stable.
