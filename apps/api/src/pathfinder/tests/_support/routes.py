"""The API routes an app or a router serves, resolved through its includes."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from starlette.routing import BaseRoute


def api_routes(routes: Sequence[BaseRoute]) -> list[RouteContext]:
    """Every ``APIRoute`` under ``routes``, in registration order."""
    return [
        context
        for context in iter_route_contexts(routes)
        if isinstance(context.original_route, APIRoute)
    ]
