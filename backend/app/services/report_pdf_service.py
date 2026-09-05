from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any, Iterable

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PRI_RED = colors.HexColor("#B91C1C")
PRI_DARK_RED = colors.HexColor("#7F1D1D")
PRI_INK = colors.HexColor("#172033")
PRI_MUTED = colors.HexColor("#64748B")
PRI_LIGHT = colors.HexColor("#F8FAFC")
PRI_BORDER = colors.HexColor("#E2E8F0")
PRI_AMBER = colors.HexColor("#F59E0B")


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _metrics(company_reports: Iterable[dict[str, Any]], offer_reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    companies = list(company_reports)
    offers = list(offer_reports)
    total_offers = int(sum(_number(company.get("total_offers")) for company in companies))
    active_offers = int(sum(_number(company.get("active_offers")) for company in companies))
    total_applications = int(sum(_number(offer.get("total_applications")) for offer in offers))
    weighted_similarity = sum(
        _number(offer.get("avg_similarity")) * _number(offer.get("total_applications"))
        for offer in offers
    )
    avg_similarity = weighted_similarity / total_applications if total_applications else 0
    return {
        "total_companies": len(companies),
        "total_offers": total_offers,
        "active_offers": active_offers,
        "closed_offers": max(total_offers - active_offers, 0),
        "total_applications": total_applications,
        "avg_similarity": avg_similarity,
    }


def _pie_chart(active: int, closed: int) -> Drawing:
    drawing = Drawing(185, 120)
    values = [active, closed]
    if not any(values):
        values = [1]

    pie = Pie()
    pie.x = 3
    pie.y = 9
    pie.width = 96
    pie.height = 96
    pie.data = values
    pie.labels = None
    pie.slices.strokeColor = colors.white
    pie.slices.strokeWidth = 2
    pie.slices[0].fillColor = PRI_RED
    if len(values) > 1:
        pie.slices[1].fillColor = PRI_AMBER
    drawing.add(pie)

    total = active + closed
    active_rate = round(active * 100 / total) if total else 0
    drawing.add(String(109, 77, f"Activas: {active}", fontName="Helvetica-Bold", fontSize=9, fillColor=PRI_INK))
    drawing.add(String(109, 57, f"{active_rate}% del total", fontName="Helvetica", fontSize=8, fillColor=PRI_RED))
    drawing.add(String(109, 34, f"Cerradas: {closed}", fontName="Helvetica", fontSize=8, fillColor=PRI_MUTED))
    return drawing


def _applications_chart(offer_reports: list[dict[str, Any]]) -> Drawing:
    top_offers = sorted(
        offer_reports,
        key=lambda offer: _number(offer.get("total_applications")),
        reverse=True,
    )[:5]

    drawing = Drawing(245, 120)
    if not top_offers:
        drawing.add(String(12, 58, "No hay postulaciones para graficar.", fontName="Helvetica", fontSize=9, fillColor=PRI_MUTED))
        return drawing

    values = [_number(offer.get("total_applications")) for offer in reversed(top_offers)]
    names = [str(offer.get("title") or "Sin título")[:20] for offer in reversed(top_offers)]
    max_value = max(values) if values else 1

    chart = HorizontalBarChart()
    chart.x = 96
    chart.y = 10
    chart.height = 94
    chart.width = 135
    chart.data = [values]
    chart.categoryAxis.categoryNames = names
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = PRI_MUTED
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(max_value, 1)
    chart.valueAxis.valueStep = max(1, round(max_value / 4))
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.strokeColor = PRI_BORDER
    chart.bars[0].fillColor = PRI_RED
    chart.bars[0].strokeColor = None
    chart.barWidth = 10
    drawing.add(chart)
    return drawing


def build_executive_report_pdf(
    company_reports: list[dict[str, Any]],
    offer_reports: list[dict[str, Any]],
    generated_at: datetime | None = None,
) -> bytes:
    generated_at = generated_at or datetime.now()
    metrics = _metrics(company_reports, offer_reports)
    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        title="Reporte gerencial PRI",
        author="PRI",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExecutiveTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=PRI_INK,
        alignment=TA_LEFT,
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "ExecutiveSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=PRI_MUTED,
    )
    section_style = ParagraphStyle(
        "ExecutiveSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=PRI_INK,
        spaceBefore=6,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ExecutiveBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=PRI_MUTED,
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=colors.white,
    )
    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=body_style,
        fontSize=7.5,
        leading=10,
        textColor=PRI_INK,
    )

    story: list[Any] = []
    header = Table(
        [[
            Paragraph("Reporte gerencial de reclutamiento", title_style),
            Paragraph(
                f"Generado el {generated_at.strftime('%d/%m/%Y a las %H:%M')}<br/><b>Uso interno gerencial</b>",
                subtitle_style,
            ),
        ]],
        colWidths=[182 * mm, 78 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 2, PRI_RED),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([header, Spacer(1, 7 * mm)])

    kpi_data = [[
        Paragraph(f"<b>{metrics['total_companies']}</b><br/><font size='8' color='#64748B'>Empresas</font>", title_style),
        Paragraph(f"<b>{metrics['active_offers']}</b><br/><font size='8' color='#64748B'>Vacantes activas</font>", title_style),
        Paragraph(f"<b>{metrics['total_applications']}</b><br/><font size='8' color='#64748B'>Postulaciones</font>", title_style),
        Paragraph(f"<b>{metrics['avg_similarity']:.1f}%</b><br/><font size='8' color='#64748B'>Afinidad promedio</font>", title_style),
    ]]
    kpis = Table(kpi_data, colWidths=[65 * mm] * 4, rowHeights=[25 * mm])
    kpis.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRI_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.7, PRI_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, PRI_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([kpis, Spacer(1, 6 * mm)])

    top_offer = max(offer_reports, key=lambda offer: _number(offer.get("total_applications")), default=None)
    active_rate = metrics["active_offers"] * 100 / metrics["total_offers"] if metrics["total_offers"] else 0
    insight_lines = [
        f"La cartera mantiene <b>{active_rate:.0f}%</b> de sus vacantes activas.",
        (
            f"La vacante con mayor volumen es <b>{escape(str(top_offer.get('title') or 'Sin título'))}</b> "
            f"con <b>{int(_number(top_offer.get('total_applications')))}</b> postulaciones."
            if top_offer else "Aún no hay postulaciones registradas."
        ),
        f"La afinidad promedio ponderada de los candidatos es <b>{metrics['avg_similarity']:.1f}%</b>.",
    ]
    insights = [Paragraph("Lectura ejecutiva", section_style)] + [
        Paragraph(f"- {line}", body_style) for line in insight_lines
    ]
    overview = Table(
        [[
            [Paragraph("Estado de vacantes", section_style), _pie_chart(metrics["active_offers"], metrics["closed_offers"])],
            [Paragraph("Postulaciones por vacante", section_style), _applications_chart(offer_reports)],
            insights,
        ]],
        colWidths=[72 * mm, 96 * mm, 92 * mm],
    )
    overview.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.7, PRI_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, PRI_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([overview, Spacer(1, 4 * mm), Paragraph("Detalle de vacantes", section_style)])

    rows = [[
        Paragraph("Vacante", table_header_style),
        Paragraph("Empresa", table_header_style),
        Paragraph("Postulaciones", table_header_style),
        Paragraph("Afinidad promedio", table_header_style),
    ]]
    for offer in sorted(offer_reports, key=lambda item: _number(item.get("total_applications")), reverse=True):
        similarity = _number(offer.get("avg_similarity"))
        rows.append([
            Paragraph(escape(str(offer.get("title") or "Sin título")), table_cell_style),
            Paragraph(escape(str(offer.get("company_name") or "Sin empresa")), table_cell_style),
            Paragraph(str(int(_number(offer.get("total_applications")))), table_cell_style),
            Paragraph(f"{similarity:.1f}%" if offer.get("avg_similarity") is not None else "Sin datos", table_cell_style),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No hay vacantes registradas.", table_cell_style), "", "", ""])

    detail = Table(rows, colWidths=[94 * mm, 72 * mm, 43 * mm, 51 * mm], repeatRows=1)
    detail_style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRI_DARK_RED),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PRI_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, PRI_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if not offer_reports:
        detail_style.append(("SPAN", (0, 1), (-1, 1)))
    detail.setStyle(TableStyle(detail_style))
    story.append(detail)

    def page_decoration(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        page_width, _ = landscape(A4)
        canvas.setFillColor(PRI_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(14 * mm, 8 * mm, "PRI - Reporte confidencial para uso interno")
        canvas.drawRightString(page_width - 14 * mm, 8 * mm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    return output.getvalue()
