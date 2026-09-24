"""The workbench routes are gone, and the seed route has its own path.

A removed route answers what HTTP says for a path no route serves: 404 when no
route template covers the path, 405 when a kept route covers it for another verb.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Match

from pathfinder.main import create_app
from pathfinder.tests._support.routes import api_routes

_UNSERVED: list[tuple[str, str]] = [
    ("POST", "/api/v1/gene-sets/gs-1/enrich"),
    ("POST", "/api/v1/gene-sets/gs-1/retake"),
    ("GET", "/api/v1/gene-sets/gs-1/results/attributes"),
    ("GET", "/api/v1/gene-sets/gs-1/results/records"),
    ("GET", "/api/v1/gene-sets/gs-1/results/distributions/gene_product"),
    ("POST", "/api/v1/gene-sets/gs-1/results/record"),
    ("GET", "/api/v1/gene-sets/gs-1/experiments"),
    ("POST", "/api/v1/experiments"),
    ("POST", "/api/v1/experiments/batch"),
    ("POST", "/api/v1/experiments/benchmark"),
    ("POST", "/api/v1/experiments/seed"),
    ("POST", "/api/v1/experiments/exp-1/custom-enrich"),
    ("POST", "/api/v1/experiments/exp-1/threshold-sweep"),
    ("GET", "/api/v1/experiments/exp-1/results/attributes"),
    ("GET", "/api/v1/experiments/exp-1/results/records"),
    ("POST", "/api/v1/experiments/exp-1/results/record"),
    ("GET", "/api/v1/experiments/exp-1/results/distributions/gene_product"),
    ("GET", "/api/v1/control-sets"),
    ("POST", "/api/v1/control-sets"),
    ("GET", "/api/v1/sites/plasmodb/organisms"),
    ("GET", "/api/v1/sites/plasmodb/genes/search"),
    ("POST", "/api/v1/sites/plasmodb/genes/resolve"),
]

# GET /api/v1/gene-sets and DELETE /api/v1/gene-sets/{gene_set_id} stay, so
# these paths still match a kept route template for another verb.
_WRONG_VERB: list[tuple[str, str]] = [
    ("POST", "/api/v1/gene-sets"),
    ("POST", "/api/v1/gene-sets/operations"),
    ("POST", "/api/v1/gene-sets/reverse-search"),
    ("POST", "/api/v1/gene-sets/ensemble"),
    ("POST", "/api/v1/gene-sets/confidence"),
]


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app(include_dev_routes=False)


def _matches(app: FastAPI, method: str, path: str) -> set[Match]:
    scope = {"type": "http", "method": method, "path": path, "root_path": ""}
    return {route.matches(scope)[0] for route in app.router.routes}


@pytest.mark.parametrize(("method", "path"), _UNSERVED)
def test_a_removed_route_is_not_found(app: FastAPI, method: str, path: str) -> None:
    assert _matches(app, method, path) == {Match.NONE}
    response = TestClient(app).request(
        method, path, headers={"X-Requested-With": "test"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize(("method", "path"), _WRONG_VERB)
def test_a_removed_verb_on_a_kept_path_is_not_allowed(
    app: FastAPI, method: str, path: str
) -> None:
    assert Match.FULL not in _matches(app, method, path)
    assert Match.PARTIAL in _matches(app, method, path)
    response = TestClient(app).request(
        method, path, headers={"X-Requested-With": "test"}
    )
    assert response.status_code == 405


def test_the_seed_route_is_mounted_at_its_own_path(app: FastAPI) -> None:
    pairs = {pair for route in api_routes(app.routes) for pair in route.pairs}

    assert ("POST", "/api/v1/seed") in pairs
