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
    static_native_plot_traces: int
    modal_native_plot_traces: int
    modal_animation_frames: int
    png_bytes: int
    xlsx_bytes: int
    pdf_bytes: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_frozen_engineering_outputs_test() -> FrozenEngineeringOutputsResult:
    """Exercise rich export plus 0.19 native Static/Modal Plotly runtime in frozen builds."""

    from openpyxl import Workbook
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    rotor = ross.rotor_example()
    figure = rotor.plot_rotor(nodes=1)
    traces = len(getattr(figure, "data", ()))
    if traces <= 0:
        raise RuntimeError("Frozen native ROSS plot contains no traces.")

    rotor6 = ross.rotor_example_6dof()
    static = rotor6.run_static()
    static_figure = static.plot_deformation()
    static_traces = len(getattr(static_figure, "data", ()))
    if static_traces <= 0:
        raise RuntimeError("Frozen native ROSS StaticResults plot contains no traces.")

    modal = rotor6.run_modal(100.0, num_modes=16)
    shapes = tuple(modal.shapes)
    torsional = [index for index, shape in enumerate(shapes) if shape.mode_type == "Torsional"]
    mode = torsional[0] if torsional else 0
    modal_figure = modal.plot_mode_3d(mode, animation=True)
    modal_traces = len(getattr(modal_figure, "data", ()))
    animation_frames = len(getattr(modal_figure, "frames", ()))
    if modal_traces <= 0 or animation_frames <= 0:
        raise RuntimeError(
            f"Frozen native ROSS animated mode shape is incomplete: traces={modal_traces}, frames={animation_frames}."
        )

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
        sheet.append(["Static native plot traces", static_traces])
        sheet.append(["Modal native plot traces", modal_traces])
        sheet.append(["Modal animation frames", animation_frames])
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
            static_native_plot_traces=static_traces,
            modal_native_plot_traces=modal_traces,
            modal_animation_frames=animation_frames,
            png_bytes=png.stat().st_size,
            xlsx_bytes=xlsx.stat().st_size,
            pdf_bytes=pdf.stat().st_size,
        )


__all__ = ["FrozenEngineeringOutputsResult", "run_frozen_engineering_outputs_test"]
