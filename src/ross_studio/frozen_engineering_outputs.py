from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import tempfile

import ross

from . import __version__


@dataclass(slots=True, frozen=True)
class FrozenEngineeringOutputsResult:
    status: str
    ross_version: str
    ross_studio_version: str
    native_ross_plot_traces: int
    png_bytes: int
    xlsx_bytes: int
    pdf_bytes: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_frozen_engineering_outputs_test() -> FrozenEngineeringOutputsResult:
    """Exercise rich-export runtime dependencies from the exact frozen executable.

    The normal CI gate validates the full OP-W60 Engineering Outputs pipeline. This
    frozen gate is intentionally lightweight: it proves that the packaged executable
    can create a native ROSS Plotly figure and that Kaleido/OpenPyXL/ReportLab runtime
    resources survived PyInstaller collection on Windows and Linux.
    """

    from openpyxl import Workbook
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    rotor = ross.rotor_example()
    figure = rotor.plot_rotor(nodes=1)
    traces = len(getattr(figure, "data", ()))
    if traces <= 0:
        raise RuntimeError("Frozen native ROSS plot contains no traces.")

    with tempfile.TemporaryDirectory(prefix="ross-studio-frozen-outputs-") as temp:
        root = Path(temp)
        png = root / "native_ross_rotor.png"
        figure.write_image(str(png), format="png", width=900, height=500, scale=1)

        xlsx = root / "engineering_outputs.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Qualification"
        sheet.append(["ROSS", ross.__version__])
        sheet.append(["ROSS Studio", __version__])
        sheet.append(["Native ROSS plot traces", traces])
        workbook.save(xlsx)

        pdf = root / "engineering_outputs.pdf"
        report = canvas.Canvas(str(pdf), pagesize=A4)
        report.drawString(72, 780, "ROSS Studio Engineering Outputs frozen export gate")
        report.drawString(72, 760, f"ROSS {ross.__version__} · Studio {__version__}")
        report.drawImage(str(png), 72, 420, width=450, height=250, preserveAspectRatio=True, anchor="c")
        report.save()

        for path in (png, xlsx, pdf):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError(f"Frozen Engineering Outputs did not create {path.name}.")

        return FrozenEngineeringOutputsResult(
            status="PASS",
            ross_version=ross.__version__,
            ross_studio_version=__version__,
            native_ross_plot_traces=traces,
            png_bytes=png.stat().st_size,
            xlsx_bytes=xlsx.stat().st_size,
            pdf_bytes=pdf.stat().st_size,
        )


__all__ = ["FrozenEngineeringOutputsResult", "run_frozen_engineering_outputs_test"]
