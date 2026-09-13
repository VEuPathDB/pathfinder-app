"""Readiness-state tracking for the API lifecycle.

A single process-wide :class:`ReadinessState` records the init status of the
process subsystems - database, embedding backend, graph checkpointer, and
input screening where the deployment turns it on - and of each site catalog.
The process is ready when every reported subsystem is ready and at least one
catalog is loaded; a site whose catalog is not loaded is degraded, not fatal.
``/health/ready`` consults this state to return 200/503.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

_CATALOGS = "catalogs"

_FIXED_SUBSYSTEMS = (
    "database",
    "embedding_backend",
    "graph_checkpointer",
)

# A subsystem the deployment may not run. Absent means it holds nothing back.
_OPTIONAL_SUBSYSTEMS = ("input_screening",)


class SubsystemStatus(BaseModel):
    """Per-subsystem readiness record."""

    ready: bool = False
    error: str | None = None


class ReadinessState(BaseModel):
    """Aggregate readiness for the whole API process."""

    database: SubsystemStatus = Field(default_factory=SubsystemStatus)
    embedding_backend: SubsystemStatus = Field(default_factory=SubsystemStatus)
    graph_checkpointer: SubsystemStatus = Field(default_factory=SubsystemStatus)
    input_screening: SubsystemStatus | None = None
    catalogs: dict[str, SubsystemStatus] = Field(default_factory=dict)

    @property
    def _reported_optional(self) -> list[tuple[str, SubsystemStatus]]:
        """The optional subsystems this deployment runs, with their status."""
        return [
            (name, status)
            for name in _OPTIONAL_SUBSYSTEMS
            if (status := getattr(self, name)) is not None
        ]

    @property
    def all_ready(self) -> bool:
        return (
            self.database.ready
            and self.embedding_backend.ready
            and self.graph_checkpointer.ready
            and all(status.ready for _, status in self._reported_optional)
            and any(c.ready for c in self.catalogs.values())
        )

    @property
    def not_ready(self) -> list[str]:
        missing = [name for name in _FIXED_SUBSYSTEMS if not getattr(self, name).ready]
        missing += [
            name for name, status in self._reported_optional if not status.ready
        ]
        if not any(c.ready for c in self.catalogs.values()):
            missing.append(_CATALOGS)
        return missing

    @property
    def degraded(self) -> list[str]:
        """The sites whose catalog failed or is still loading."""
        return sorted(site_id for site_id, c in self.catalogs.items() if not c.ready)

    @property
    def first_ready_catalog(self) -> str | None:
        """The loaded site with the lowest id, or None while none is loaded."""
        return next(
            (
                site_id
                for site_id in sorted(self.catalogs)
                if self.catalogs[site_id].ready
            ),
            None,
        )

    def degraded_catalog(self, site_id: str) -> SubsystemStatus | None:
        """The status of a registered catalog that is not ready."""
        if site_id not in self.catalogs:
            return None
        status = self.catalogs[site_id]
        return None if status.ready else status

    def mark_ready(self, subsystem: str) -> None:
        if subsystem not in _FIXED_SUBSYSTEMS + _OPTIONAL_SUBSYSTEMS:
            msg = f"unknown subsystem: {subsystem}"
            raise ValueError(msg)
        setattr(self, subsystem, SubsystemStatus(ready=True))

    def mark_failed(self, subsystem: str, error: str) -> None:
        if subsystem not in _FIXED_SUBSYSTEMS + _OPTIONAL_SUBSYSTEMS:
            msg = f"unknown subsystem: {subsystem}"
            raise ValueError(msg)
        setattr(self, subsystem, SubsystemStatus(ready=False, error=error))

    def fail_loading(self, error: BaseException) -> None:
        """Fail every subsystem that is neither ready nor already failed.

        A catalog records the error class alone, because the sites response
        reports it and a message can carry a URL or a token.
        """
        detail = f"{type(error).__name__}: {error}"
        for name in _FIXED_SUBSYSTEMS:
            status: SubsystemStatus = getattr(self, name)
            if not status.ready and status.error is None:
                setattr(self, name, SubsystemStatus(ready=False, error=detail))
        for site_id, catalog in self.catalogs.items():
            if not catalog.ready and catalog.error is None:
                self.catalogs[site_id] = SubsystemStatus(
                    ready=False, error=type(error).__name__
                )

    def register_catalog(self, site_id: str) -> None:
        self.catalogs[site_id] = SubsystemStatus()

    def mark_catalog_ready(self, site_id: str) -> None:
        self.catalogs[site_id] = SubsystemStatus(ready=True)

    def mark_catalog_failed(self, site_id: str, error: str) -> None:
        self.catalogs[site_id] = SubsystemStatus(ready=False, error=error)


_state_holder: dict[str, ReadinessState] = {}


def get_readiness() -> ReadinessState:
    """Return the process-wide readiness state (lazily constructed)."""
    if "v" not in _state_holder:
        _state_holder["v"] = ReadinessState()
    return _state_holder["v"]


def reset_readiness() -> None:
    """Reset state. For tests and shutdown only."""
    _state_holder.clear()
