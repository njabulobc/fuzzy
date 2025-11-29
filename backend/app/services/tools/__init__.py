from __future__ import annotations

"""backend/app/services/tools/__init__.py

Tool adapter registry.

This module exposes a single convenience helper `get_default_tool_runners`
that constructs ToolRunner instances for all supported tools:

- Slither (static analysis)
- Echidna (property-based fuzzing)
- Foundry (tests + fuzzing + invariants)

The runner in `app.services.scanner.runner` accepts a mapping from tool name
to an object implementing `ToolRunnerProtocol`. These adapters satisfy that
protocol and are wired here in one place so Celery tasks or synchronous
utility scripts can easily obtain the full set.
"""

from typing import Dict

from app.services.scanner.runner import ToolRunnerProtocol
from app.services.tools.echidna_tool import EchidnaToolRunner
from app.services.tools.foundry_tool import FoundryToolRunner
from app.services.tools.slither_tool import SlitherToolRunner


def get_default_tool_runners() -> Dict[str, ToolRunnerProtocol]:
    runners: list[ToolRunnerProtocol] = [
        SlitherToolRunner(),
        EchidnaToolRunner(),
        FoundryToolRunner(),
    ]
    return {runner.name: runner for runner in runners}
