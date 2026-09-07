"""Health request/response DTOs."""

from datetime import datetime

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.platform.readiness import ReadinessState


class HealthResponse(CamelModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime


class ReadinessResponse(CamelModel):
    """Readiness check response, including per-subsystem detail."""

    status: str
    version: str
    timestamp: datetime
    readiness: ReadinessState
    not_ready: list[str] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list)


class SystemReadyResponse(CamelModel):
    """Aggregate readiness for the UI startup gate: API subsystems + worker."""

    ready: bool
    api_ready: bool
    worker_alive: bool
    not_ready: list[str] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list)


class ProviderStatus(CamelModel):
    """Per-provider API-key availability."""

    openai: bool
    anthropic: bool
    google: bool
    ollama: bool


class SystemConfigResponse(CamelModel):
    """System configuration status (unauthenticated)."""

    chat_provider: str
    llm_configured: bool
    providers: ProviderStatus
