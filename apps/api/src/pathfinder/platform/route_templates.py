from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from pydantic import BaseModel, ConfigDict
from starlette.routing import BaseRoute
from starlette.types import Scope


class TwoTemplatesError(ValueError):
    def __init__(self, templates: tuple[str, str]) -> None:
        super().__init__(f"one route is included under two templates: {templates}")
        self.templates = templates


class RouteTemplates:
    def __init__(self, routes: Sequence[BaseRoute]) -> None:
        self._templates: dict[int, str] = {}
        for context in iter_route_contexts(routes):
            template = context.path_format
            if template is None:
                continue
            key = id(context.original_route)
            if key in self._templates and self._templates[key] != template:
                raise TwoTemplatesError((self._templates[key], template))
            self._templates[key] = template

    def of(self, route: object) -> str | None:
        if id(route) not in self._templates:
            return None
        return self._templates[id(route)]


class _RoutedScope(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    app: FastAPI
    route: object = None


def install_route_templates(app: FastAPI) -> None:
    app.state.route_templates = RouteTemplates(app.routes)


def route_template(scope: Scope) -> str | None:
    routed = _RoutedScope.model_validate(scope)
    templates: RouteTemplates = routed.app.state.route_templates
    return templates.of(routed.route)


__all__ = [
    "RouteTemplates",
    "TwoTemplatesError",
    "install_route_templates",
    "route_template",
]
