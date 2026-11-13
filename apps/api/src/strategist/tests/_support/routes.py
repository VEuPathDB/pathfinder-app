"""The API routes an app or a router serves, resolved through its includes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts
from pydantic import BaseModel
from starlette.routing import BaseRoute

_FRAMEWORK_VERBS = frozenset({"HEAD", "OPTIONS"})


@dataclass(frozen=True)
class ApiRoute:
    """One API route, with every field a route-table test reads already bound."""

    path: str
    methods: frozenset[str]
    name: str
    tags: tuple[str | Enum, ...]
    endpoint: Callable[..., Any]
    dependant: Dependant
    body_model: type[BaseModel] | None

    @property
    def pairs(self) -> list[tuple[str, str]]:
        """The verb and path pairs the route answers, verbs in order.

        HEAD and OPTIONS are the framework's, so a route table names neither.
        """
        return [
            (method, self.path) for method in sorted(self.methods - _FRAMEWORK_VERBS)
        ]


def api_routes(routes: Sequence[BaseRoute]) -> list[ApiRoute]:
    """Every ``APIRoute`` under ``routes``, in registration order."""
    return [
        _bound(context)
        for context in iter_route_contexts(routes)
        if isinstance(context.original_route, APIRoute)
    ]


def _bound(context: RouteContext) -> ApiRoute:
    """Read one route context as the record, or name the field it lacks."""
    path, methods, endpoint = context.path, context.methods, context.endpoint
    if path is None or methods is None or endpoint is None:
        msg = f"an API route with no path, methods or endpoint: {context.name}"
        raise AssertionError(msg)
    return ApiRoute(
        path=path,
        methods=frozenset(methods),
        name=context.name or "",
        tags=tuple(context.tags),
        endpoint=endpoint,
        dependant=_dependant(context),
        body_model=_body_model(context),
    )


def _dependant(context: RouteContext) -> Dependant:
    """The dependant the effective route context carries, includes merged in."""
    found: object = context.dependant
    if isinstance(found, Dependant):
        return found
    msg = f"the API route {context.path} carries no dependant"
    raise AssertionError(msg)


def _body_model(context: RouteContext) -> type[BaseModel] | None:
    """The model a route's request body carries, for a route that takes one."""
    body = context.body_field
    if body is None:
        return None
    annotation: object = body.field_info.annotation
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None
