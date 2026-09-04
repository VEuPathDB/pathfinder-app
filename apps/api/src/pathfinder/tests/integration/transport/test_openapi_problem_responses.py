from typing import Any

import httpx
from fastapi import FastAPI


def _op(spec: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    return spec["paths"][path][method]


async def test_route_miss_404_is_problem_json(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/no-such-route")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_download_routes_declare_real_content_types(app: FastAPI) -> None:
    spec = app.openapi()
    download = _op(spec, "/api/v1/exports/{export_id}", "get")
    download_types = download["responses"]["200"]["content"]
    assert "text/csv" in download_types, download_types
    assert "application/json" in download_types, download_types


def test_streaming_route_declares_event_stream(app: FastAPI) -> None:
    spec = app.openapi()
    op = _op(spec, "/api/v1/experiments/{experiment_id}/threshold-sweep", "post")
    content = op["responses"]["200"]["content"]
    assert "text/event-stream" in content, content


def test_problem_detail_is_a_declared_component(app: FastAPI) -> None:
    spec = app.openapi()
    schemas = spec["components"]["schemas"]
    assert "ProblemDetail" in schemas
    # ProblemDetail references the ErrorCode enum, which must also be declared.
    assert "ErrorCode" in schemas


def test_validation_response_declares_problem_json(app: FastAPI) -> None:
    spec = app.openapi()
    # GET /api/v1/gene-sets has a validated query param, so FastAPI emits a 422.
    responses = _op(spec, "/api/v1/gene-sets", "get")["responses"]
    assert "422" in responses
    content = responses["422"]["content"]
    assert "application/problem+json" in content, content
    ref = content["application/problem+json"]["schema"]["$ref"]
    assert ref.endswith("/ProblemDetail"), ref


def test_resource_ops_declare_404_problem_json(app: FastAPI) -> None:
    spec = app.openapi()
    responses = _op(spec, "/api/v1/conversations/{strategyId}", "get")["responses"]
    assert "404" in responses, responses
    ref = responses["404"]["content"]["application/problem+json"]["schema"]["$ref"]
    assert ref.endswith("/ProblemDetail"), ref


def test_paramless_op_has_no_404(app: FastAPI) -> None:
    # A collection endpoint with no path param should not claim a 404.
    spec = app.openapi()
    responses = _op(spec, "/api/v1/gene-sets", "get")["responses"]
    assert "404" not in responses, responses


def test_problem_json_schema_is_object_not_string(app: FastAPI) -> None:
    spec = app.openapi()
    problem = spec["components"]["schemas"]["ProblemDetail"]
    assert problem["type"] == "object"
    assert "title" in problem["properties"]
    assert "status" in problem["properties"]


def test_problem_detail_has_no_response_defaults(app: FastAPI) -> None:
    # Response schemas carry no input defaults; a null default makes Kubb emit
    # invalid zod (``.default({})``).
    spec = app.openapi()
    problem = spec["components"]["schemas"]["ProblemDetail"]
    for name, prop in problem["properties"].items():
        assert "default" not in prop, (name, prop)
