from __future__ import annotations

"""
Diagnostics and error classification utilities.

This package currently provides:
- error_classifier: classify failures from tool executions into stable,
  machine-readable reasons that can be surfaced in the UI or used by
  reporting modules.

The goal is to keep error handling logic centralized and deterministic.
"""
