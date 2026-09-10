"""Context variables the science owns. The runtime owns the rest."""

from contextvars import ContextVar

# Request base URL (e.g. "http://localhost:3000") for constructing full download URLs.
# Set from the Origin or Referer header so export URLs resolve correctly for the user.
request_base_url_ctx: ContextVar[str | None] = ContextVar(
    "request_base_url", default=None
)
