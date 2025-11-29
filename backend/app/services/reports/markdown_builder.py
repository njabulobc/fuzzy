# backend/app/services/reports/markdown_builder.py
from __future__ import annotations

"""
Markdown report generation for scans.

This module is deliberately pure and side-effect free: it takes ORM
objects (Scan, Finding, ToolExecution) and returns a markdown string.

It does **not** hit the filesystem or external services.
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable, List

from sqlalchemy.orm import Session, selectinload

from app import models


def _format_dt(dt: datetime | None) -> str:
    if not dt:
        return "-"
    # ISO-like but more human
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_severity_counts(findings: Iterable[models.Finding]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for f in findings:
        sev = (f.severity or "UNKNOWN").upper()
        counter[sev] += 1
    return dict(counter)


def _build_tool_counts(findings: Iterable[models.Finding]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for f in findings:
        tool = (f.tool or "unknown").lower()
        counter[tool] += 1
    return dict(counter)


def build_scan_markdown(
    *,
    project: models.Project,
    scan: models.Scan,
    findings: List[models.Finding],
    tool_executions: List[models.ToolExecution],
) -> str:
    """
    Build a markdown report for a given scan.

    This function assumes all ORM objects are already loaded and attached
    to an active Session (but does not itself touch the DB).
    """
    lines: list[str] = []

    # Header
    lines.append(f"# Security Scan Report")
    lines.append("")
    lines.append(f"**Project:** {project.name}")
    lines.append(f"**Project ID:** `{project.id}`")
    lines.append(f"**Scan ID:** `{scan.id}`")
    if scan.name:
        lines.append(f"**Scan Name:** {scan.name}")
    lines.append(f"**Status:** `{scan.status.value}`")
    lines.append(f"**Target:** `{scan.target}`")
    lines.append(f"**Tools:** `{', '.join(scan.tools)}`" if scan.tools else "**Tools:** `-`")
    if scan.chain:
        lines.append(f"**Chain / Network:** `{scan.chain}`")
    lines.append(f"**Created at:** {_format_dt(scan.created_at)}")
    lines.append(f"**Started at:** {_format_dt(scan.started_at)}")
    lines.append(f"**Finished at:** {_format_dt(scan.finished_at)}")
    lines.append("")

    # Summary tables
    lines.append("## Summary")
    lines.append("")

    severity_counts = _build_severity_counts(findings)
    tool_counts = _build_tool_counts(findings)
    total_findings = len(findings)

    lines.append(f"- **Total findings:** {total_findings}")
    if severity_counts:
        lines.append("- **By severity:**")
        for sev, count in sorted(severity_counts.items(), key=lambda t: t[0]):
            lines.append(f"  - {sev}: {count}")
    if tool_counts:
        lines.append("- **By tool:**")
        for tool, count in sorted(tool_counts.items(), key=lambda t: t[0]):
            lines.append(f"  - {tool}: {count}")
    lines.append("")

    # Tool execution details
    lines.append("## Tool Executions")
    lines.append("")
    if not tool_executions:
        lines.append("_No tool execution records found for this scan._")
    else:
        lines.append("| Tool | Status | Exit Code | Findings | Duration (s) | Failure Reason |")
        lines.append("|------|--------|-----------|----------|--------------|----------------|")
        for te in sorted(tool_executions, key=lambda t: t.tool):
            status = te.status.value if te.status else "-"
            exit_code = te.exit_code if te.exit_code is not None else "-"
            findings_count = te.findings_count
            duration = f"{te.duration_seconds:.2f}" if te.duration_seconds is not None else "-"
            reason = te.failure_reason or "-"
            lines.append(
                f"| {te.tool} | {status} | {exit_code} | {findings_count} | {duration} | {reason} |"
            )
    lines.append("")

    # Findings by severity & tool
    lines.append("## Findings")
    lines.append("")
    if not findings:
        lines.append("_No findings were recorded for this scan._")
        return "\n".join(lines)

    # Group findings by severity then tool
    grouped: dict[str, dict[str, list[models.Finding]]] = defaultdict(lambda: defaultdict(list))
    for f in findings:
        sev = (f.severity or "UNKNOWN").upper()
        tool = (f.tool or "unknown").lower()
        grouped[sev][tool].append(f)

    for severity in sorted(grouped.keys()):
        lines.append(f"### Severity: {severity}")
        lines.append("")
        for tool, tool_findings in sorted(grouped[severity].items(), key=lambda t: t[0]):
            lines.append(f"#### Tool: {tool}")
            lines.append("")
            for idx, f in enumerate(sorted(tool_findings, key=lambda x: x.created_at or scan.created_at), start=1):
                lines.append(f"##### {idx}. {f.title}")
                lines.append("")
                if f.file_path:
                    location = f.file_path
                    if f.line_number:
                        location += f":{f.line_number}"
                    lines.append(f"- **Location:** `{location}`")
                if f.function:
                    lines.append(f"- **Function:** `{f.function}`")
                if f.tool_version:
                    lines.append(f"- **Tool version:** `{f.tool_version}`")
                if f.input_seed:
                    lines.append(f"- **Input seed:** `{f.input_seed}`")
                if f.coverage:
                    lines.append(f"- **Coverage:** `{f.coverage}`")
                if f.assertions:
                    lines.append(f"- **Assertions:** `{f.assertions}`")
                lines.append("")
                if f.description:
                    lines.append("**Description**")
                    lines.append("")
                    lines.append(f"{f.description}")
                    lines.append("")
                if f.raw:
                    lines.append("<details>")
                    lines.append("<summary>Raw tool output</summary>")
                    lines.append("")
                    lines.append("```json")
                    # Keep raw JSON compact; truncate extremely long strings is left
                    # to the consumer (UI) if needed.
                    import json as _json  # local import to avoid global pollution

                    lines.append(_json.dumps(f.raw, indent=2, sort_keys=True))
                    lines.append("```")
                    lines.append("</details>")
                    lines.append("")
            lines.append("")
        lines.append("")

    return "\n".join(lines)


def build_scan_markdown_from_db(db: Session, scan_id: str) -> str:
    """
    Convenience helper that loads a scan + related data from the DB and
    returns the markdown report.
    """
    scan = (
        db.query(models.Scan)
        .options(
            selectinload(models.Scan.project),
            selectinload(models.Scan.findings),
            selectinload(models.Scan.tool_executions),
        )
        .filter(models.Scan.id == scan_id)
        .first()
    )
    if not scan:
        raise ValueError(f"Scan {scan_id} not found")

    project = scan.project
    if not project:
        raise ValueError(f"Scan {scan_id} has no associated project")

    findings = list(scan.findings or [])
    tool_executions = list(scan.tool_executions or [])
    return build_scan_markdown(
        project=project,
        scan=scan,
        findings=findings,
        tool_executions=tool_executions,
    )
