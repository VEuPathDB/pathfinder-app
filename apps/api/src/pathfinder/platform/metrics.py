from __future__ import annotations

import time
from wsgiref.simple_server import WSGIServer

from prometheus_client import Counter, Histogram, start_http_server
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "CHAT_TURNS_FINISHED",
    "CHAT_TURNS_STARTED",
    "CHAT_TURN_DURATION",
    "MODEL_COST_USD",
    "MODEL_TOKENS",
    "TOOL_SOURCE_ERRORS",
    "HttpMetricsMiddleware",
    "serve_metrics",
]

_UNMATCHED_ROUTE = "unmatched"

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
            method, route = scope["method"], _route_of(scope)
            HTTP_REQUESTS.labels(method, route, f"{status // 100}xx").inc()
            HTTP_REQUEST_DURATION.labels(method, route).observe(seconds)


def serve_metrics(port: int, addr: str) -> WSGIServer | None:
    if port == 0:
        return None
    server, _ = start_http_server(port, addr=addr)
    return server
