from __future__ import annotations

"""backend/app/config/settings.py

Application configuration using environment-driven settings.

This module centralizes:
- database connection URL
- Celery / Redis configuration
- CORS configuration
- Docker image names for tools
- Workspace root for scan artifacts
- Per-tool runtime defaults (timeouts, fuzz durations, etc.)
"""
from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  app_name: str = "fuzz-backend"
  environment: str = "development"

  # Database
  database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/scan"

  # Celery / Redis
  celery_broker_url: str = "redis://redis:6379/1"
  celery_result_backend: str = "redis://redis:6379/2"

  # CORS
  allowed_origins: List[AnyHttpUrl] = [
      "http://localhost:3000",
      "http://127.0.0.1:3000",
      "http://localhost:5173",
      "http://127.0.0.1:5173",
  ]

  # Docker tooling
  docker_binary: str = "docker"
  slither_image: str = "trailofbits/slither:latest"
  echidna_image: str = "trailofbits/echidna:latest"
  foundry_image: str = "ghcr.io/foundry-rs/foundry:latest"

  # On-disk workspace root (inside the backend container)
  workspace_root: str = "/workspaces"

  projects_host_root: str | None = None

  # Per-tool runtime defaults (seconds)
  slither_timeout_seconds: int = 600
  slither_max_runtime_seconds: int | None = 900

  echidna_timeout_seconds: int = 900
  echidna_max_runtime_seconds: int | None = 1200
  echidna_fuzz_duration_seconds: int | None = 600

  foundry_timeout_seconds: int = 900
  foundry_max_runtime_seconds: int | None = 1200

  model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
  """Return a cached Settings instance."""
  return Settings()
