# backend/app/services/reports/__init__.py
from __future__ import annotations

"""
Reporting utilities for scans.

This package provides:
- Markdown report generation for a scan
- PDF export built on top of the markdown report

High-level helpers exposed:

- build_scan_markdown_from_db(db, scan_id) -> str
- export_scan_pdf_from_db(db, scan_id, output_dir) -> pathlib.Path
"""

from .markdown_builder import (  # noqa: F401
    build_scan_markdown,
    build_scan_markdown_from_db,
)
from .pdf_exporter import (  # noqa: F401
    export_markdown_to_pdf,
    export_scan_pdf_from_db,
)
