"""Pipeline phase roles - leaf module so it has no cycles with agent modules."""

from __future__ import annotations

from typing import Literal

PhaseRole = Literal[
    "lead",
    "frame",
    "execution",
    "verification",
]

PHASE_ROLES: tuple[PhaseRole, ...] = (
    "lead",
    "frame",
    "execution",
    "verification",
)
