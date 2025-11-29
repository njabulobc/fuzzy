from __future__ import annotations

"""backend/app/services/diagnostics/error_classifier.py

Centralized error classification for tool executions.

This module looks at a ToolResult (stdout, stderr, return code, etc.)
and assigns a stable, machine-readable `failure_reason` string.

The classification is:
- deterministic (no randomness)
- text-based (pattern matching against known error signatures)
- tool-aware (Docker, Slither, Echidna, Foundry)

Typical failure_reason values:
- docker-daemon-unavailable
- docker-image-not-found
- docker-binary-not-found
- tool-timeout
- tool-output-parse-error
- tool-compilation-error
- tool-build-error
- tool-not-found
- tool-runtime-error
- tool-non-zero-exit
- process-spawn-error
- unknown-error
"""

from dataclasses import dataclass
from typing import Optional

from app.services.tools.base import ToolResult


@dataclass
class ErrorContext:
    """Lightweight context for classification."""

    tool: str
    result: ToolResult


def _text(value: Optional[str]) -> str:
    return (value or "").strip()


def _lower(value: Optional[str]) -> str:
    return _text(value).lower()


def _contains_any(haystack: str, needles: list[str]) -> bool:
    return any(n in haystack for n in needles)


def classify_tool_failure(tool: str, result: ToolResult) -> str:
    """Classify a tool failure into a stable failure_reason code.

    This function assumes the tool invocation did *not* succeed.
    It never returns None; at minimum it returns "unknown-error".
    """
    # Shortcuts for readability
    stdout = _lower(result.output)
    stderr = _lower(result.error)
    combined = f"{stdout}\n{stderr}"
    rc = result.return_code
    parsing_error = _text(result.parsing_error)
    existing_reason = _text(result.failure_reason)

    # 1) Respect explicit timeout/crash markers from the runner layer
    if existing_reason in ("timeout", "process-spawn-error"):
        return existing_reason

    # 2) Timeouts
    if "timeout" in stderr or "timed out" in stderr:
        return "tool-timeout"

    # 3) Parsing / JSON issues
    if parsing_error:
        return "tool-output-parse-error"

    # 4) Docker-specific issues
    # Docker daemon unavailable
    if _contains_any(
        combined,
        [
            "cannot connect to the docker daemon",
            "is the docker daemon running",
            "permission denied while trying to connect to the docker daemon",
        ],
    ):
        return "docker-daemon-unavailable"

    # Docker binary not found on PATH
    if "no such file or directory: 'docker'" in combined or "docker: not found" in combined:
        return "docker-binary-not-found"

    # Docker image pull / not found
    if _contains_any(
        combined,
        [
            "pull access denied for",
            "repository does not exist",
            "manifest unknown",
            "no such image",
        ],
    ):
        return "docker-image-not-found"

    # 5) Compilation / build issues (solc / forge / echidna)
    if _contains_any(
        combined,
        [
            "compilererror",
            "parsererror",
            "typeerror",
            "syntaxerror",
            "could not compile",
            "failed to compile",
            "compile error",
            "error while compiling",
        ],
    ):
        return "tool-compilation-error"

    # Foundry/forge-specific build errors
    if _contains_any(
        combined,
        [
            "forge build failed",
            "failed to build",
            "build failed",
            "error: could not compile",
        ],
    ):
        return "tool-build-error"

    # Echidna not present in image / binary missing
    if _contains_any(
        combined,
        [
            "echidna-test: command not found",
            "echidna: command not found",
        ],
    ):
        return "tool-not-found"

    # Slither not present
    if "slither: command not found" in combined:
        return "tool-not-found"

    # Foundry/forge binary missing
    if _contains_any(
        combined,
        [
            "forge: command not found",
            "foundry: command not found",
        ],
    ):
        return "tool-not-found"

    # 6) Generic runtime/tool errors
    if _contains_any(
        combined,
        [
            "runtime error",
            "panic:",
            "stack trace:",
            "segmentation fault",
            "segfault",
        ],
    ):
        return "tool-runtime-error"

    # 7) Non-zero exit without a more specific classification
    if rc is not None and rc != 0:
        return "tool-non-zero-exit"

    # 8) Fall back to existing reason or unknown
    if existing_reason:
        return existing_reason
    return "unknown-error"
