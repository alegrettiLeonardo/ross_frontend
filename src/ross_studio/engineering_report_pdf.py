from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

from .domain import EngineeringError
from .engineering_outputs import EngineeringOutputsService, EngineeringOutputsSnapshot, EngineeringTable

if TYPE_CHECKING:
    from .engineering_figures import EngineeringFigureCatalog


def export_pdf_fitted(
    snapshot: EngineeringOutputsSnapshot,
    path: str | Path,
    *,
    figure_paths: dict[str, Path] | None = None,
    figure_catalog: "EngineeringFigureCatalog | None" = None,
) -> Path:
    """Write a bounded, wrapped PDF report for Engineering Outputs.

    The scientific content remains owned by ``EngineeringOutputsSnapshot`` and the
    native ROSS Plotly figures. This function only owns page composition. Every table
    is fitted to the printable landscape-A4 width so long audit messages cannot extend
    beyond the page boundary.
    """

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from xml.sax.saxutils import escape
    except Exception as exc:  # pragma: no cover - dependency/frozen gate
        raise EngineeringError(f"PDF export requires reportlab: {exc}") from exc

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(target),
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"ROSS Studio Engineering Outputs - {snapshot.project.get('name', '')}",
        author="ROSS Studio",
    )
    page_width, _page_height = landscape(A4)
    usable_width = page_width - document.leftMargin - document.rightMargin

    body_style = ParagraphStyle(
        "EngineeringTableBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=6.2,
        leading=7.2,
        spaceBefore=0,
        spaceAfter=0,
    )
    header_style = ParagraphStyle(
        "EngineeringTableHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
    )

    def cell(value: object, style: ParagraphStyle = body_style) -> Paragraph:
        return Paragraph(escape("" if value is None else str(value)), style)

    def fitted_widths(engineering_table: EngineeringTable) -> list[float]:
        count = max(1, len(engineering_table.columns))
        minimum = 26.0 if count >= 10 else 34.0
        minimum = min(minimum, usable_width / count)
        remaining = max(0.0, usable_width - minimum * count)
        weights: list[float] = []
        for index, column in enumerate(engineering_table.columns):
            lengths = [len(str(column))]
            for row in engineering_table.rows[:100]:
                if index < len(row) and row[index] is not None:
                    lengths.append(len(str(row[index])))
            weights.append(float(max(6, min(80, max(lengths)))))
        total = sum(weights) or float(count)
        return [minimum + remaining * weight / total for weight in weights]

    story: list[Any] = [
        Paragraph("ROSS Studio - Engineering Outputs", styles["Title"]),
        Paragraph(str(snapshot.project.get("name", "")), styles["Heading2"]),
        Paragraph(
            f"ROSS {snapshot.provenance.get('ross_version')} - ROSS Studio {snapshot.provenance.get('ross_studio_version')} - "
            f"Project fingerprint {snapshot.provenance.get('project_fingerprint_sha256')}",
            styles["BodyText"],
        ),
        Spacer(1, 6 * mm),
    ]

    summary_rows = [
        [cell("Quantity", header_style), cell("Value", header_style)],
        *[[cell(key), cell(value)] for key, value in snapshot.summary.items()],
    ]
    summary_table = Table(summary_rows, repeatRows=1, colWidths=[70 * mm, 150 * mm], hAlign="LEFT")
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#AAB7C4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.extend([summary_table, PageBreak()])

    for engineering_table in snapshot.tables:
        story.append(Paragraph(engineering_table.title, styles["Heading2"]))
        rows = [
            [cell(column, header_style) for column in engineering_table.columns],
            *[[cell(value) for value in row] for row in engineering_table.rows],
        ]
        table = Table(
            rows,
            repeatRows=1,
            colWidths=fitted_widths(engineering_table),
            hAlign="LEFT",
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
            ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#BBC5CE")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.extend([table, Spacer(1, 5 * mm)])

    if figure_paths:
        story.extend([PageBreak(), Paragraph("Native ROSS Figures", styles["Heading1"])])
        for key, image_path in figure_paths.items():
            title = key
            source = "ROSS native Plotly figure"
            basis = ""
            if figure_catalog is not None:
                spec = figure_catalog.spec(key)
                title = spec.title
                source = spec.source_method
                basis = spec.tutorial_basis
            block: list[Any] = [
                Paragraph(title, styles["Heading2"]),
                Paragraph(f"Source: {source}", styles["BodyText"]),
            ]
            if basis:
                block.append(Paragraph(f"Tutorial basis: {basis}", styles["BodyText"]))
            block.extend([
                Spacer(1, 2 * mm),
                Image(str(image_path), width=240 * mm, height=135 * mm, kind="proportional"),
                Spacer(1, 5 * mm),
            ])
            story.append(KeepTogether(block))

    story.extend([PageBreak(), Paragraph("Limitations", styles["Heading1"])])
    for item in snapshot.limitations:
        story.append(Paragraph(f"- {escape(str(item))}", styles["BodyText"]))

    document.build(story)
    if not target.is_file() or target.stat().st_size == 0:
        raise EngineeringError("PDF export did not produce a valid report file.")
    return target


def install_engineering_report_export() -> None:
    """Install the bounded report composer on the 0.18 Engineering Outputs service."""

    EngineeringOutputsService.export_pdf = staticmethod(export_pdf_fitted)
    EngineeringOutputsService.PDF_LAYOUT_POLICY = "LANDSCAPE_A4_FIT_AND_WRAP"


__all__ = ["export_pdf_fitted", "install_engineering_report_export"]
