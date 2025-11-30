"""Lightweight Statsig integration for backend events."""
from __future__ import annotations

import logging
from typing import Any

from statsig import StatsigOptions, StatsigServer

from app.config import get_settings

logger = logging.getLogger(__name__)


class _StatsigAdapter:
    def __init__(self, secret_key: str | None, environment: str):
        self._client: StatsigServer | None = None
        if not secret_key:
            return

        try:
            self._client = StatsigServer(
                secret_key,
                options=StatsigOptions(environment={"tier": environment}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Statsig initialization failed: %s", exc)
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def log_event(
        self,
        *,
        user_id: str,
        event_name: str,
        value: float | int | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._client:
            return

        try:
            self._client.log_event(
                {"userID": user_id}, event_name, value=value, metadata=metadata
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Statsig event failed: %s", exc)

    def shutdown(self) -> None:
        if not self._client:
            return

        try:
            self._client.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Statsig shutdown failed: %s", exc)


_statsig_client: _StatsigAdapter | None = None


def get_statsig_client() -> _StatsigAdapter:
    global _statsig_client
    if _statsig_client is None:
        settings = get_settings()
        _statsig_client = _StatsigAdapter(
            settings.statsig_server_secret, settings.environment
        )
    return _statsig_client


def log_backend_event(
    event_name: str,
    *,
    user_id: str = "backend",
    value: float | int | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    client = get_statsig_client()
    client.log_event(user_id=user_id, event_name=event_name, value=value, metadata=metadata)


def shutdown_statsig() -> None:
    client = get_statsig_client()
    client.shutdown()
