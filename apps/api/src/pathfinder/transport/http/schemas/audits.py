"""The request bodies of the audit routes."""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.audit.run_state import RunAction


class AuditStart(CamelModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: RunAction
