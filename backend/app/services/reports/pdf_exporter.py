# backend/app/services/reports/pdf_exporter.py
from __future__ import annotations

"""
PDF export for scan reports.

This module builds a PDF from a markdown string in a very simple way:
it renders the markdown as plain text, preserving headings, bullet
points, and code blocks as literal lines.

For more advanced formatting, a richer markdown→HTML→PDF pipeline can
be added later, but this keeps dependencies minimal and robust.
"""

from pathlib import Path
from typing import Union

from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app import models
from app.services.reports.markdown_builder import build_scan_markdown_from_db

PageSize = tuple[float, float]


def export_markdown_to_pdf(
    markdown: str,
    output_path: Union[str, Path],
    *,
    page_size: PageSize = A4,
    margin_left: int = 40,
    margin_top: int = 40,
    line_height: int = 14,
) -> Path:
    """
    Render a markdown string into a simple text-based PDF.

    The markdown content is treated as plain text. Headings, lists, and
    code blocks are preserved as-is in the text representation, which is
    sufficient for security reports that will primarily be consumed as
    structured text.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(output_path), pagesize=page_size)
    width, height = page_size

    x = margin_left
    y = height - margin_top

    for line in markdown.splitlines():
        if y <= margin_top:
            c.showPage()
            y = height - margin_top
        # Using drawString keeps layout simple and deterministic
        c.drawString(x, y, line[:2000])  # guard against extremely long lines
        y -= line_height

    c.showPage()
    c.save()
    return output_path


def export_scan_pdf_from_db(
    db: Session,
    scan_id: str,
    output_dir: Union[str, Path],
) -> Path:
    """
    Generate a markdown report for a scan and export it as a PDF file
    under the specified directory.

    Typical usage inside a Celery task or worker:

        from app.services.reports import export_scan_pdf_from_db
        pdf_path = export_scan_pdf_from_db(db, scan_id, workspace.artifacts_dir / "reports")
    """
    markdown = build_scan_markdown_from_db(db, scan_id)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # File name: scan_<scan_id>.pdf (sanitized)
    safe_id = scan_id.replace("/", "_")
    pdf_path = output_dir / f"scan_{safe_id}.pdf"

    return export_markdown_to_pdf(markdown, pdf_path)
