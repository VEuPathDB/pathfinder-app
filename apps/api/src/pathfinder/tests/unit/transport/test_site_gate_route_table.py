"""Which routes refuse a site whose catalog is not loaded, named one by one.

The rule: a route carries the gate when the request itself names the site, in
its path or its query. A route that changes category has to change this list,
and a route that reaches a site without the gate has to state why here.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant

from pathfinder.main import create_app
from pathfinder.tests._support.routes import ApiRoute, api_routes
from pathfinder.transport.http.deps import (
    require_available_site,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.routers.chat import require_available_chat_site

GATED: frozenset[tuple[str, str]] = frozenset(
    {
        # The catalog itself: these routes read what did not load.
        ("GET", "/api/v1/sites/{siteId}/record-types"),
        ("GET", "/api/v1/sites/{siteId}/searches"),
        ("POST", "/api/v1/sites/{siteId}/searches/{recordType}/{searchName}/validate"),
        (
            "POST",
            "/api/v1/sites/{siteId}/searches/{recordType}/{searchName}/param-specs",
        ),
        (
            "POST",
            (
                "/api/v1/sites/{siteId}/searches/{recordType}/{searchName}"
                "/refreshed-dependent-params"
            ),
        ),
        ("GET", "/api/v1/sites/{siteId}/organisms"),
        ("GET", "/api/v1/sites/{siteId}/genes/search"),
        ("POST", "/api/v1/sites/{siteId}/genes/resolve"),
        # The account listing reads the site the path names.
        ("GET", "/api/v1/sites/{siteId}/strategies"),
        # EDA: the study set the request names lives on the site.
        ("GET", "/api/v1/eda/studies"),
        ("GET", "/api/v1/eda/studies/{dataset_id}"),
        ("POST", "/api/v1/eda/count"),
        ("POST", "/api/v1/eda/distribution"),
        ("POST", "/api/v1/eda/viz"),
        # Strategy writes: every one of them runs a step on the site.
        ("POST", "/api/v1/conversations/{strategyId:uuid}/operations"),
        ("POST", "/api/v1/conversations/{conversation_id:uuid}/insert-saved"),
        ("POST", "/api/v1/conversations/{conversation_id:uuid}/save-substrategy"),
    }
)

# The turn's site rides the request body, so the gate reads the body instead
# of a parameter. The refusal is the same one.
BODY_GATED: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/chat"): "The site is `siteId` on the chat body.",
}

# Routes that reach a site without the gate, and the reason each one may.
UNGATED_BUT_REACHES_A_SITE: dict[tuple[str, str], str] = {
    (
        "POST",
        "/api/v1/veupathdb/auth/login",
    ): "Obtains the session every other route needs; refusing it would sign "
    "the caller out of every site at once.",
    ("POST", "/api/v1/veupathdb/auth/logout"): "Ends the session the token names.",
    (
        "POST",
        "/api/v1/veupathdb/auth/refresh",
    ): "Re-derives the internal token from a live VEuPathDB session.",
    (
        "GET",
        "/api/v1/veupathdb/auth/status",
    ): "Reads the caller's own session and answers 'signed out' without one.",
    (
        "GET",
        "/api/v1/conversations/{conversation_id}/eda",
    ): "The site comes from the thread's binding row, not from the request.",
    (
        "PATCH",
        "/api/v1/conversations/{conversation_id}/eda",
    ): "Same shape: the binding row names the site.",
    (
        "POST",
        "/api/v1/experiments/seed",
    ): "Its site is optional, so the required site dependency cannot bind it; "
    "the identity gate refuses a degraded one and the seed stream reports each "
    "site's own failure.",
}

# Routes that name a site in a request body other than the chat body. Their
# call goes to WDK under its own timeout and never touches the catalog.
BODY_SITE_UNGATED: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/conversations"),
        ("POST", "/api/v1/conversations/open"),
        ("POST", "/api/v1/conversations/step-counts"),
        ("POST", "/api/v1/control-sets"),
        ("POST", "/api/v1/eval/build-gold"),
        ("POST", "/api/v1/eval/strategy-gene-ids"),
        ("POST", "/api/v1/experiments"),
        ("POST", "/api/v1/gene-sets"),
        ("POST", "/api/v1/gene-sets/import"),
        ("POST", "/api/v1/gene-sets/reverse-search"),
    }
)

# Routes whose only site id is the WDK identity gate's optional ``siteId``.
# Naming a degraded site refuses the request before the identity read; naming
# none reads the account on a site this process loaded. The site the route
# then works on comes from a stored row, not from the request.
IDENTITY_SITE_GATED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/experiments/{experiment_id}/results/attributes"),
        (
            "GET",
            "/api/v1/experiments/{experiment_id}/results/distributions/{attribute_name}",
        ),
        ("GET", "/api/v1/experiments/{experiment_id}/results/records"),
        ("GET", "/api/v1/gene-sets/{gene_set_id}/results/attributes"),
        (
            "GET",
            "/api/v1/gene-sets/{gene_set_id}/results/distributions/{attribute_name}",
        ),
        ("GET", "/api/v1/gene-sets/{gene_set_id}/results/records"),
        ("GET", "/api/v1/gene-sets/{gene_set_id}/vdi-publication"),
        ("POST", "/api/v1/conversations/{conversation_id}/revert-to-message"),
        ("POST", "/api/v1/conversations/{strategyId:uuid}/fork"),
        ("POST", "/api/v1/experiments/batch"),
        ("POST", "/api/v1/experiments/benchmark"),
        ("POST", "/api/v1/experiments/{experiment_id}/results/record"),
        ("POST", "/api/v1/experiments/{experiment_id}/threshold-sweep"),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/enrich"),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/results/record"),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/retake"),
        ("POST", "/api/v1/gene-sets/{gene_set_id}/vdi-publication"),
    }
)


# Routes that carry a site id and touch only this deployment's own rows.
LOCAL_READ_UNGATED: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/control-sets"),
        ("GET", "/api/v1/conversations"),
        ("GET", "/api/v1/conversations/dismissed"),
        ("GET", "/api/v1/conversations/saved-strategy-consumers"),
        ("POST", "/api/v1/conversations/{conversation_id}/begin"),
        ("GET", "/api/v1/gene-sets"),
        ("DELETE", "/api/v1/user/data"),
    }
)


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app()


def _carries(dependant: Dependant, call: object) -> bool:
    return any(
        sub.call is call or _carries(sub, call) for sub in dependant.dependencies
    )


def _routes_with(app: FastAPI, call: object) -> set[tuple[str, str]]:
    return {
        pair
        for route in api_routes(app.routes)
        if _carries(route.dependant, call)
        for pair in route.pairs
    }


def _all_routes(app: FastAPI) -> set[tuple[str, str]]:
    return {pair for route in api_routes(app.routes) for pair in route.pairs}


def _flat(dependant: Dependant) -> Iterator[Dependant]:
    yield dependant
    for sub in dependant.dependencies:
        yield from _flat(sub)


def _names_a_site(route: ApiRoute) -> bool:
    """Whether the request itself carries a site id, in a parameter or a body."""
    for dependant in _flat(route.dependant):
        for param in dependant.path_params + dependant.query_params:
            if "site" in param.alias.lower():
                return True
    if route.body_model is None:
        return False
    return any("site" in name.lower() for name in route.body_model.model_fields)


def _site_scoped_routes(app: FastAPI) -> set[tuple[str, str]]:
    return {
        pair
        for route in api_routes(app.routes)
        if _names_a_site(route)
        for pair in route.pairs
    }


def test_every_route_that_names_a_site_is_in_exactly_one_list(app: FastAPI) -> None:
    """The list is total: a new site-scoped route has to choose a category."""
    listed = (
        GATED
        | BODY_GATED.keys()
        | UNGATED_BUT_REACHES_A_SITE.keys()
        | BODY_SITE_UNGATED
        | IDENTITY_SITE_GATED
        | LOCAL_READ_UNGATED
    )
    unlisted = sorted(_site_scoped_routes(app) - listed)

    assert unlisted == [], f"site-scoped routes no list names: {unlisted}"


def test_exactly_the_listed_routes_refuse_a_degraded_site(app: FastAPI) -> None:
    gated = _routes_with(app, require_available_site)

    assert sorted(gated - GATED) == [], (
        "routes gained the gate without joining the list"
    )
    assert sorted(GATED - gated) == [], "listed routes no longer carry the gate"


def test_every_identity_site_gated_route_carries_the_identity_gate(
    app: FastAPI,
) -> None:
    """Their only refusal is that gate, so losing it would lose the refusal."""
    behind_identity = _routes_with(app, require_registered_wdk_identity)

    assert sorted(IDENTITY_SITE_GATED - behind_identity) == []


def test_exactly_the_chat_route_reads_the_site_from_a_body(app: FastAPI) -> None:
    assert _routes_with(app, require_available_chat_site) == set(BODY_GATED)


def test_every_listed_route_still_exists(app: FastAPI) -> None:
    listed = (
        GATED
        | BODY_GATED.keys()
        | UNGATED_BUT_REACHES_A_SITE.keys()
        | BODY_SITE_UNGATED
        | IDENTITY_SITE_GATED
        | LOCAL_READ_UNGATED
    )
    missing = sorted(listed - _all_routes(app))

    assert missing == [], f"the list names routes the app no longer serves: {missing}"


def test_no_exception_is_secretly_gated(app: FastAPI) -> None:
    """An exception that gained the gate is a reason nobody needs any more."""
    gated = _routes_with(app, require_available_site) | _routes_with(
        app, require_available_chat_site
    )
    exceptions = (
        UNGATED_BUT_REACHES_A_SITE.keys() | BODY_SITE_UNGATED | LOCAL_READ_UNGATED
    )
    stale = sorted(exceptions & gated)

    assert stale == [], f"exceptions that now carry the gate: {stale}"


def test_every_site_path_parameter_is_named_the_same(app: FastAPI) -> None:
    """A second spelling of the site id would need a second dependency."""
    site_paths = sorted(
        path
        for route in api_routes(app.routes)
        for _method, path in route.pairs
        if "site_id" in path
    )

    assert site_paths == []


def test_every_site_parameter_is_named_the_same(app: FastAPI) -> None:
    """The wire spelling is ``siteId`` in a query as well as in a path."""
    misspelled = sorted(
        (method, path, param.alias)
        for route in api_routes(app.routes)
        for dependant in _flat(route.dependant)
        for param in dependant.path_params + dependant.query_params
        if "site" in param.alias.lower() and param.alias != "siteId"
        for method, path in route.pairs
    )

    assert misspelled == []
