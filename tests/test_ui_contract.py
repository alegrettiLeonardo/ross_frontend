from pathlib import Path


def test_approved_visual_tokens_are_centralized():
    text = Path("src/ross_frontend/ui/theme.py").read_text(encoding="utf-8")
    for token in ("#103B5D", "#0B2E49", "#137FF1", "#F4F8FC", "#FFFFFF", "#CFDDEA", "#16A66B", "#071B2B"):
        assert token in text


def test_approved_screens_and_fields_exist_in_sources():
    sources = "\n".join(p.read_text(encoding="utf-8") for p in Path("src/ross_frontend/ui").glob("*.py"))
    required = (
        "Rotor Model", "Shaft Segments", "Project Information", "Model Summary", "Quick Actions", "Run Analysis",
        "Bearing Studio", "Coefficient K/C", "Ball Bearing", "Roller Bearing", "Cylindrical", "Plain Journal", "Tilting Pad",
        "K & C Coefficients", "Pressure", "Temperature", "Film Thickness", "Journal Position", "Convergence",
        "Analysis Results", "Campbell Diagram", "First Critical Speed", "Second Critical Speed", "Stability Margin",
        "ROSS Solver Console", "Execution Status", "Analysis Steps", "Open Results",
    )
    for label in required:
        assert label in sources
