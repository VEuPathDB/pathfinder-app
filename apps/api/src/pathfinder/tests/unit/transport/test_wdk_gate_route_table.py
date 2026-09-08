"""Which routes require a registered VEuPathDB login, named one by one.

The rule: a route carries the gate when one of its normal paths reads or writes
the caller's WDK account. A route that changes category has to change this list,
and a route that reaches WDK without the gate has to state why here.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant

from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.main import create_app
from pathfinder.services.wdk_identity import require_registered_wdk_login
from pathfinder.tests._support.routes import api_routes
from pathfinder.transport.http.deps import require_registered_wdk_identity
from pathfinder.transport.http.routers.chat import resolve_chat_assistant

# Routes whose gate is the resolved assistant's, not the route's. The refusal
# is the same one; which assistant answers decides whether it runs.
SPEC_GATED: dict[tuple[str, str], str] = {
    (
        "POST",
        "/api/v1/chat",
    ): "The turn's assistant declares the requirement; PathFinder's spec "
    "names the registered login, and the dependency runs it before dispatch, "
    "so the worker never builds a strategy without the user's token.",
}

GATED: frozenset[tuple[str, str]] = frozenset(
    {
        # Conversations: the subroutes that act on the user's WDK strategies.
        ("POST", "/api/v1/conversations/step-counts"),
        ("POST", "/api/v1/conversations/open"),
        ("POST", "/api/v1/conversations/{strategyId:uuid}/operations"),
        ("POST", "/api/v1/conversations/{strategyId:uuid}/fork"),
        ("POST", "/api/v1/conversations/{conversation_id}/revert-to-message"),
        ("POST", "/api/v1/conversations/{conversation_id:uuid}/save-substrategy"),
        ("POST", "/api/v1/conversations/{conversation_id:uuid}/insert-saved"),
        # Gene sets: the routes that materialize or read a WDK dataset.
        ("POST", "/api/v1/gene-sets"),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/retake"),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/enrich"),
        ("GET", "/api/v1/gene-sets/{gene_set_id}/results/attributes"),
        ("GET", "/api/v1/gene-sets/{gene_set_id}/results/records"),
        (
            "GET",
            "/api/v1/gene-sets/{gene_set_id}/results/distributions/{attribute_name}",
        ),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/results/record"),
        # Publishing a set writes a dataset into the researcher's own account.
        ("POST", "/api/v1/gene-sets/{gene_set_id}/vdi-publication"),
        ("GET", "/api/v1/gene-sets/{gene_set_id}/vdi-publication"),
        # Experiments: the routes that run or read a WDK strategy.
        ("POST", "/api/v1/experiments"),
        ("POST", "/api/v1/experiments/batch"),
        ("POST", "/api/v1/experiments/benchmark"),
        ("POST", "/api/v1/experiments/seed"),
        ("POST", "/api/v1/experiments/{experiment_id}/threshold-sweep"),
        ("GET", "/api/v1/experiments/{experiment_id}/results/attributes"),
        ("GET", "/api/v1/experiments/{experiment_id}/results/records"),
        (
            "GET",
            "/api/v1/experiments/{experiment_id}/results/distributions/{attribute_name}",
        ),
        ("POST", "/api/v1/experiments/{experiment_id}/results/record"),
        # EDA: every route reads the caller's own EDA account, and resolving
        # the analysis user goes through WDK.
        ("GET", "/api/v1/eda/studies"),
        ("GET", "/api/v1/eda/studies/{dataset_id}"),
        ("POST", "/api/v1/eda/count"),
        ("POST", "/api/v1/eda/distribution"),
        ("POST", "/api/v1/eda/viz"),
        ("GET", "/api/v1/conversations/{conversation_id}/eda"),
        ("PATCH", "/api/v1/conversations/{conversation_id}/eda"),
        # Eval: both routes build or read a WDK strategy in the caller's account.
        ("POST", "/api/v1/eval/build-gold"),
        ("POST", "/api/v1/eval/strategy-gene-ids"),
    }
)

# Routes that can reach WDK without the gate, and the reason each one may.
UNGATED_BUT_REACHES_WDK: dict[tuple[str, str], str] = {
    (
        "DELETE",
        "/api/v1/conversations/{strategyId:uuid}",
    ): "The WDK delete is opt-in (deleteFromWdk) and best-effort; gating the "
    "route would stop a signed-out user removing their own local rows.",
    (
        "DELETE",
        "/api/v1/user/data",
    ): "Same shape: the WDK purge is opt-in (deleteWdk) and best-effort, and "
    "the local purge must run either way.",
    (
        "GET",
        "/api/v1/sites/{siteId}/record-types",
    ): "User-independent catalog read.",
    ("GET", "/api/v1/sites/{siteId}/searches"): "User-independent catalog read.",
    ("GET", "/api/v1/sites/{siteId}/organisms"): "User-independent vocabulary read.",
    ("GET", "/api/v1/sites/{siteId}/genes/search"): "User-independent answer read.",
    ("POST", "/api/v1/sites/{siteId}/genes/resolve"): "User-independent answer read.",
    (
        "POST",
        "/api/v1/sites/{siteId}/searches/{recordType}/{searchName}/validate",
    ): "User-independent parameter metadata read.",
    (
        "POST",
        "/api/v1/sites/{siteId}/searches/{recordType}/{searchName}/param-specs",
    ): "User-independent parameter metadata read.",
    (
        "POST",
        "/api/v1/sites/{siteId}/searches/{recordType}/{searchName}/refreshed-dependent-params",
    ): "User-independent parameter metadata read.",
    (
        "GET",
        "/api/v1/veupathdb/auth/status",
    ): "Reads the caller's own WDK session, and answers 'signed out' when the "
    "request carries no token.",
    (
        "POST",
        "/api/v1/veupathdb/auth/login",
    ): "Obtains the token the gate requires; gating it would deadlock.",
    ("POST", "/api/v1/veupathdb/auth/logout"): "Ends the session the token names.",
    (
        "POST",
        "/api/v1/veupathdb/auth/refresh",
    ): "Re-derives the internal token from a live VEuPathDB session.",
}


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app()


def _carries_gate(dependant: Dependant) -> bool:
    return any(
        sub.call is require_registered_wdk_identity or _carries_gate(sub)
        for sub in dependant.dependencies
    )


def _gated_routes(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in api_routes(app.routes)
        if _carries_gate(route.dependant)
        for method in route.methods - {"HEAD", "OPTIONS"}
    }


def _all_routes(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, route.path)
        for route in api_routes(app.routes)
        for method in route.methods - {"HEAD", "OPTIONS"}
    }


def test_exactly_the_listed_routes_require_a_registered_login(app: FastAPI) -> None:
    gated = _gated_routes(app)

    assert sorted(gated - GATED) == [], (
        "routes gained the gate without joining the list"
    )
    assert sorted(GATED - gated) == [], "listed routes no longer carry the gate"


def test_every_listed_route_still_exists(app: FastAPI) -> None:
    registered = _all_routes(app)
    listed = GATED | UNGATED_BUT_REACHES_WDK.keys() | SPEC_GATED.keys()
    missing = sorted(listed - registered)

    assert missing == [], f"the list names routes the app no longer serves: {missing}"


def test_no_exception_is_secretly_gated(app: FastAPI) -> None:
    """An exception that gained the gate is a reason nobody needs any more."""
    gated = _gated_routes(app)
    stale = sorted(UNGATED_BUT_REACHES_WDK.keys() & gated)

    assert stale == [], f"exceptions that now carry the gate: {stale}"


def test_a_spec_gated_route_carries_no_route_gate(app: FastAPI) -> None:
    """Two gates on one route would refuse an assistant that declares none."""
    gated = _gated_routes(app)

    assert sorted(SPEC_GATED.keys() & gated) == []


def _carries(dependant: Dependant, call: object) -> bool:
    return any(
        sub.call is call or _carries(sub, call) for sub in dependant.dependencies
    )


def test_every_spec_gated_route_resolves_its_assistant(app: FastAPI) -> None:
    """A listed route with no resolver would serve every assistant ungated."""
    resolving = {
        (method, route.path)
        for route in api_routes(app.routes)
        if _carries(route.dependant, resolve_chat_assistant)
        for method in route.methods - {"HEAD", "OPTIONS"}
    }

    assert resolving == set(SPEC_GATED)


def test_pathfinder_still_declares_the_registered_login() -> None:
    """The gate the chat route stopped carrying is the one the spec names."""
    registry = get_assistant_registry()
    spec = registry.resolve(registry.default_id)

    assert spec.identity_gate is require_registered_wdk_login
