"""Context variables the science owns. The runtime owns the rest."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from assistant_core.platform.types import ReasoningEffort
from pydantic import BaseModel, ConfigDict, Field

# Request base URL (e.g. "http://localhost:3000") for constructing full download URLs.
# Set from the Origin or Referer header so export URLs resolve correctly for the user.
request_base_url_ctx: ContextVar[str | None] = ContextVar(
    "request_base_url", default=None
)


class PhaseOverrides(BaseModel):
    """The per-phase model and reasoning picks one request carries.

    The roles and the model ids are validated on the request body; this is the
    validated pair, as the work a turn starts can read it.
    """

    model_config = ConfigDict(frozen=True)

    models: dict[str, str] = Field(default_factory=dict)
    reasoning: dict[str, ReasoningEffort] = Field(default_factory=dict)


_NO_OVERRIDES = PhaseOverrides()

# This turn's picks, for work that outlives the turn that started it.
phase_overrides_ctx: ContextVar[PhaseOverrides] = ContextVar(
    "phase_overrides", default=_NO_OVERRIDES
)


@contextmanager
def attach_phase_overrides(overrides: PhaseOverrides) -> Iterator[None]:
    """Run a turn under its own picks."""
    token = phase_overrides_ctx.set(overrides)
    try:
        yield
    finally:
        phase_overrides_ctx.reset(token)
