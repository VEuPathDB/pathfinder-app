from __future__ import annotations

import time
from wsgiref.simple_server import WSGIServer

from prometheus_client import Counter, Histogram, start_http_server
from pydantic import BaseModel, ConfigDict
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from veupathdb import MetricAttrs
from veupathdb.observability.otel import OpenTelemetryObserver
from veupathdb.wdk import list_sites

__all__ = [
    "CHAT_TURNS_FINISHED",
    "CHAT_TURNS_STARTED",
    "CHAT_TURN_DURATION",
    "MODEL_COST_USD",
    "MODEL_TOKENS",
    "TOOL_SOURCE_ERRORS",
    "WDK_SEARCH_WAIT",
    "HttpMetricsMiddleware",
    "PathfinderObserver",
    "observe_search_wait",
    "serve_metrics",
]

_UNMATCHED_ROUTE = "unmatched"
_OTHER = "other"
_SEARCH_WAIT_KINDS = frozenset({"turn", "site", "expensive"})
_OTHER_METHOD = "OTHER"
_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})

HTTP_REQUESTS = Counter(
    "pathfinder_http_requests_total",
    "HTTP requests the api answered, by method, route template and status class.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "pathfinder_http_request_duration_seconds",
    "Seconds from a request's arrival to its response headers.",
    ("method", "route"),
)
CHAT_TURNS_STARTED = Counter(
    "pathfinder_chat_turns_started_total",
    "Chat turns the api queued for the worker, by assistant.",
    ("assistant",),
)
CHAT_TURNS_FINISHED = Counter(
    "pathfinder_chat_turns_finished_total",
    "Chat turns the worker ended, by assistant, outcome and the model that read the prompt.",
    ("assistant", "outcome", "model"),
)
CHAT_TURN_DURATION = Histogram(
    "pathfinder_chat_turn_duration_seconds",
    "Seconds one chat turn ran in the worker.",
    ("assistant", "outcome"),
    buckets=(1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600, 1200),
)
MODEL_TOKENS = Counter(
    "pathfinder_model_tokens_total",
    "Tokens the finished turns recorded, by model and by whose key paid.",
    ("model", "payer"),
)
MODEL_COST_USD = Counter(
    "pathfinder_model_cost_usd_total",
    "US dollars the finished turns recorded, by model and by whose key paid.",
    ("model", "payer"),
)
TOOL_SOURCE_ERRORS = Counter(
    "pathfinder_tool_source_errors_total",
    "Tool source failures, by admitted source id and the stage that failed.",
    ("source", "stage"),
)

WDK_SEARCH_WAIT = Histogram(
    "pathfinder_wdk_search_wait_seconds",
    "Seconds a request that runs a WDK search waited in line before it was sent, by site and line.",
    ("site", "kind"),
    buckets=(0.05, 0.25, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)


def observe_search_wait(site_id: str, kind: str, seconds: float) -> None:
    known = {site.id for site in list_sites()}
    WDK_SEARCH_WAIT.labels(
        site_id if site_id in known else _OTHER,
        kind if kind in _SEARCH_WAIT_KINDS else _OTHER,
    ).observe(seconds)


class _SearchWait(BaseModel):
    model_config = ConfigDict(extra="ignore")

    site: str
    line: str


class PathfinderObserver(OpenTelemetryObserver):
    def on_wdk_search_wait(self, seconds: float, attrs: MetricAttrs, /) -> None:
        super().on_wdk_search_wait(seconds, attrs)
        wait = _SearchWait.model_validate(attrs)
        observe_search_wait(wait.site, wait.line, seconds)


def _method_of(scope: Scope) -> str:
    method: str = scope["method"]
    return method if method in _METHODS else _OTHER_METHOD


def _route_of(scope: Scope) -> str:
    route = scope.get("route")
    return route.path if isinstance(route, Route) else _UNMATCHED_ROUTE


class HttpMetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        answered: list[tuple[int, float]] = []

        async def observed(message: Message) -> None:
            if message["type"] == "http.response.start":
                answered.append((message["status"], time.perf_counter() - started))
            await send(message)

        try:
            await self.app(scope, receive, observed)
        finally:
            status, seconds = (
                answered[0] if answered else (500, time.perf_counter() - started)
            )
            method, route = _method_of(scope), _route_of(scope)
            HTTP_REQUESTS.labels(method, route, f"{status // 100}xx").inc()
            HTTP_REQUEST_DURATION.labels(method, route).observe(seconds)


def serve_metrics(port: int, addr: str) -> WSGIServer | None:
    if port == 0:
        return None
    server, _ = start_http_server(port, addr=addr)
    return server
