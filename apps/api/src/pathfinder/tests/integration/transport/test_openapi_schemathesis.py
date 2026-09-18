"""Schemathesis fuzz harness for the documented OpenAPI surface.

Every documented operation except the streaming ones becomes a parametrized
case against the in-process app. The status-code check stays off, because a
generated path parameter names no real record and the spec rarely documents
the resulting 404.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
import schemathesis
from assistant_core.platform import db
from fastapi import FastAPI
from hypothesis import HealthCheck, settings
from schemathesis import Case
from schemathesis.checks import load_all_checks, not_a_server_error
from schemathesis.config import (
    GenerationConfig,
    OperationConfig,
    OperationsConfig,
    PhasesConfig,
    ProjectConfig,
    ProjectsConfig,
    SchemathesisConfig,
)
from schemathesis.config import HealthCheck as STHealthCheck
from schemathesis.core.result import Ok
from schemathesis.core.transport import Response
from schemathesis.filters import FilterSet
from schemathesis.generation import GenerationMode
from schemathesis.openapi import from_asgi
from schemathesis.schemas import APIOperation, BaseSchema
from schemathesis.specs.openapi.checks import (
    content_type_conformance,
    response_headers_conformance,
    response_schema_conformance,
)

from pathfinder.platform.security import create_user_token
from pathfinder.tests._support.memory_store_double import LoopFreeMemoryStore
from pathfinder.tests._support.openapi_negation import (
    labels_with_uncomplementable_union,
)

load_all_checks()

# The test client waits for the response generator to finish, so an endpoint
# that holds an open stream never returns.
_STREAMING_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/chat",
        "/api/v1/conversations/{conversation_id}/events",
    }
)

_EXCLUDED_PATHS: frozenset[str] = _STREAMING_PATHS

_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")


def _event_stream_labels() -> frozenset[str]:
    # The labels come from the committed spec, so a new streaming endpoint
    # excludes itself.
    for parent in Path(__file__).resolve().parents:
        spec_path = parent / "packages" / "spec" / "openapi.json"
        if spec_path.is_file():
            break
    else:
        msg = "packages/spec/openapi.json not found"
        raise FileNotFoundError(msg)
    spec = json.loads(spec_path.read_text())
    return frozenset(
        f"{method.upper()} {path}"
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in _HTTP_METHODS
        for response in operation.get("responses", {}).values()
        if "text/event-stream" in (response.get("content") or {})
    )


_STREAMING_LABELS: frozenset[str] = _event_stream_labels()


@dataclass(frozen=True, slots=True)
class _SchemaArtifacts:
    """The schema and the credentials that the parametrized test uses."""

    schema: BaseSchema
    user_id: UUID
    auth_token: str


@pytest.fixture(scope="session")
def schemathesis_config(patched_app: tuple[FastAPI, UUID]) -> SchemathesisConfig:
    app, _ = patched_app
    # A negative case draws from the complement of a barred keyword. The
    # canonical form cannot spell the complement of a union whose branches
    # declare one property name at two types, so those operations stay positive.
    positive_only = FilterSet()
    positive_only.include(
        name=sorted(labels_with_uncomplementable_union(app.openapi()))
    )
    project = ProjectConfig(
        generation=GenerationConfig(
            allow_x00=False,
            deterministic=True,
        ),
        phases=PhasesConfig(),
        operations=OperationsConfig(
            operations=[
                OperationConfig(
                    filter_set=positive_only,
                    generation=GenerationConfig(modes=[GenerationMode.POSITIVE]),
                )
            ]
        ),
    )
    return SchemathesisConfig(
        projects=ProjectsConfig(default=project),
        suppress_health_check=[
            STHealthCheck.too_slow,
            STHealthCheck.filter_too_much,
            STHealthCheck.data_too_large,
        ],
    )


@pytest.fixture(scope="session")
def api_schema(
    patched_app: tuple[FastAPI, UUID],
    schemathesis_config: SchemathesisConfig,
) -> _SchemaArtifacts:
    app, user_id = patched_app
    schema = from_asgi("/openapi.json", app=app, config=schemathesis_config)
    return _SchemaArtifacts(
        schema=schema,
        user_id=user_id,
        auth_token=create_user_token(user_id),
    )


@pytest.fixture(scope="session")
def api_schema_only(api_schema: _SchemaArtifacts) -> BaseSchema:
    return api_schema.schema


# An exclude on the lazy schema filters at collection time, so the excluded
# operations never become cases at all.
schema = (
    schemathesis.pytest.from_fixture("api_schema_only")
    .exclude(path=list(_EXCLUDED_PATHS))
    .exclude(func=lambda ctx: ctx.operation.label in _STREAMING_LABELS)
)

# The check list is explicit, so a library upgrade cannot change what this
# test enforces.
_CHECKS: list[Callable[..., Any]] = [
    not_a_server_error,
    content_type_conformance,
    response_headers_conformance,
    response_schema_conformance,
]


@schema.parametrize()
@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.filter_too_much,
        HealthCheck.data_too_large,
        HealthCheck.function_scoped_fixture,
    ],
)
def test_openapi_conformance(
    case: Case[APIOperation[Any, Any, Any, Any]],
    api_schema: _SchemaArtifacts,
    seeded_memories: LoopFreeMemoryStore,
) -> None:
    """Fuzz one operation and validate the response against its schema."""
    del seeded_memories
    response: Response = case.call_and_validate(
        checks=_CHECKS,
        cookies={"pathfinder-auth": api_schema.auth_token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code >= 100
    assert response.status_code < 600


def _parsed_operations(schema: BaseSchema) -> list[APIOperation[Any, Any, Any, Any]]:
    """Every operation the schema parses. One it cannot parse fails the test."""
    found: list[APIOperation[Any, Any, Any, Any]] = []
    for result in schema.get_all_operations():
        if isinstance(result, Ok):
            found.append(result.ok())
            continue
        msg = f"the schema did not parse an operation: {result.err()}"
        raise AssertionError(msg)
    return found


def test_negative_generation_stays_on_where_a_complement_exists(
    api_schema: _SchemaArtifacts,
) -> None:
    """Only the operations with an uncomplementable union drop negative cases."""
    schema = api_schema.schema
    named = labels_with_uncomplementable_union(schema.raw_schema)
    modes = {
        operation.label: schema.config.generation_for(
            operation=operation, phase="fuzzing"
        ).modes
        for operation in _parsed_operations(schema)
    }

    assert modes["POST /api/v1/gene-sets"] == [GenerationMode.POSITIVE]
    assert set(modes["GET /api/v1/sites"]) == set(GenerationMode)
    positive_only = {
        label for label, asked in modes.items() if asked == [GenerationMode.POSITIVE]
    }
    assert positive_only == named & set(modes)


def test_schema_loads_and_covers_documented_surface(
    api_schema: _SchemaArtifacts,
) -> None:
    """The schema carries operations, and every excluded path is still in the
    spec."""
    raw = api_schema.schema.raw_schema
    documented_paths: set[str] = set(raw["paths"].keys())
    missing = _EXCLUDED_PATHS - documented_paths
    assert missing == set(), (
        f"Excluded path(s) no longer present in spec: {sorted(missing)}"
    )
    operation_count = sum(1 for _ in api_schema.schema.get_all_operations())
    assert operation_count >= 50

    # Every fuzzed case needs the patched engine.
    assert db._engine is not None


def test_the_memory_backed_operations_are_fuzzed(
    api_schema: _SchemaArtifacts,
) -> None:
    """The purge and the three memories operations reach the conformance run."""
    fuzzed = {
        operation.label
        for operation in _parsed_operations(api_schema.schema)
        if operation.path not in _EXCLUDED_PATHS
        and operation.label not in _STREAMING_LABELS
    }
    assert {
        "DELETE /api/v1/user/data",
        "GET /api/v1/memories",
        "GET /api/v1/memories/search",
        "PATCH /api/v1/memories/{key}",
        "DELETE /api/v1/memories/{key}",
    } <= fuzzed


async def test_health_ready_is_200_in_conformance_app(
    patched_app: tuple[FastAPI, UUID],
) -> None:
    app, _ = patched_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 200, resp.text
