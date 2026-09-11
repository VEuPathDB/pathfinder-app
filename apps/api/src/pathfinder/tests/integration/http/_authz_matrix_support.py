"""Route classification for the authorization matrix.

Owns which mutating routes address a user-owned resource, and the shape of one
matrix case. The requests themselves live in ``_authz_matrix_cases``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, get_args
from uuid import UUID

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from pathfinder.tests._support.routes import ApiRoute, api_routes

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
REFUSAL_STATUSES = frozenset({403, 404})
# A route that refuses its own owner cannot prove anything about a non-owner.
OWNER_REFUSAL_STATUSES = frozenset({401, 403, 404})

ROOT_STEP_ID = "root"
SITE_ID = "plasmodb"
MEMORY_KIND = "knowledge"
GENE_IDS = ("PF3D7_0100100", "PF3D7_0100200")


@dataclass(frozen=True)
class Resource:
    """A user-owned resource kind and the names that address one instance.

    ``prefix`` scopes a whole router, for an id key too generic to match on.
    """

    name: str
    keys: frozenset[str] = frozenset()
    prefix: str = ""


CONVERSATION = Resource(
    "conversation",
    frozenset(
        {
            "conversation_id",
            "conversationId",
            "chat_id",
            "chatId",
            "strategy_id",
            "strategyId",
        }
    ),
)
EXPERIMENT = Resource(
    "experiment",
    frozenset(
        {
            "experiment_id",
            "experimentId",
            "experiment_ids",
            "experimentIds",
            "parent_experiment_id",
            "parentExperimentId",
        }
    ),
)
GENE_SET = Resource(
    "gene set",
    frozenset(
        {
            "gene_set_id",
            "geneSetId",
            "gene_set_ids",
            "geneSetIds",
            "set_a_id",
            "setAId",
            "set_b_id",
            "setBId",
        }
    ),
)
CONTROL_SET = Resource("control set", frozenset({"control_set_id", "controlSetId"}))
MEMORY = Resource("memory", prefix="/api/v1/memories")

RESOURCES = (CONVERSATION, EXPERIMENT, GENE_SET, CONTROL_SET, MEMORY)

# Routes that carry a resource key but read or write no instance of it.
NOT_RESOURCE_SCOPED: dict[tuple[str, str, str], str] = {
    (
        CONVERSATION.name,
        "POST",
        "/api/v1/feedback/actions",
    ): "Langfuse telemetry: the id is an analytics label, and the route reads "
    "and writes no PathFinder-owned resource.",
    (
        CONTROL_SET.name,
        "POST",
        "/api/v1/experiments",
    ): "controlSetId is provenance on the experiment config. The controls come "
    "from the request body, and no code path loads the control set by that id.",
    (
        CONTROL_SET.name,
        "POST",
        "/api/v1/experiments/batch",
    ): "Same provenance-only controlSetId, reached through the nested base config.",
    (
        CONTROL_SET.name,
        "POST",
        "/api/v1/experiments/benchmark",
    ): "Same provenance-only controlSetId, in the nested base config and in each "
    "control set entry.",
    (
        EXPERIMENT.name,
        "POST",
        "/api/v1/experiments",
    ): "parentExperimentId is provenance on the experiment config. Nothing loads "
    "an experiment by it; it is only stored and serialized.",
    (
        EXPERIMENT.name,
        "POST",
        "/api/v1/experiments/batch",
    ): "Same provenance-only parentExperimentId, in the nested base config.",
    (
        EXPERIMENT.name,
        "POST",
        "/api/v1/experiments/benchmark",
    ): "Same provenance-only parentExperimentId, in the nested base config.",
}

# Routes whose owner request is answered by WDK, which VEuPathDB serves to
# registered users only. Their owner contrast carries the test account's token.
WDK_BACKED: dict[tuple[str, str], str] = {
    (
        "POST",
        "/api/v1/experiments/{experiment_id}/results/record",
    ): "the record comes from WDK",
    (
        "POST",
        "/api/v1/gene-sets/{gene_set_id}/enrich",
    ): "the enrichment runs on WDK",
    (
        "POST",
        "/api/v1/gene-sets/{gene_set_id}/results/record",
    ): "the record comes from WDK",
}


@dataclass(frozen=True)
class OwnerContrastWaiver:
    """Why the owner half of a case does not run, and the one status a non-owner may get.

    A 404 is only unambiguous when the owned resource is the request's sole
    lookup; a request that also names another id could be missing that id.
    """

    reason: str
    non_owner_status: int


# Routes whose owner request cannot run in this suite.
NO_OWNER_CONTRAST: dict[tuple[str, str], OwnerContrastWaiver] = {
    (
        "POST",
        "/api/v1/conversations/{conversation_id:uuid}/insert-saved",
    ): OwnerContrastWaiver(
        "The owner needs a saved WDK strategy id, which only a live WDK write "
        "produces. WDK answers 404 for the placeholder id.",
        non_owner_status=403,
    ),
    (
        "POST",
        "/api/v1/gene-sets/{gene_set_id}/vdi-publication",
    ): OwnerContrastWaiver(
        "The owner request creates a dataset in the researcher's VEuPathDB "
        "account. The set lookup is the route's first step and the only id "
        "the request names, so the non-owner's 404 is the ownership refusal.",
        non_owner_status=404,
    ),
}


@dataclass(frozen=True)
class Case:
    """One request the matrix issues, as the owner and as a non-owner."""

    method: str
    route: str
    url: str
    resources: frozenset[str]
    body: dict[str, Any] | None = None


@dataclass(frozen=True)
class Owned:
    """One instance of every owned resource kind, all held by ``user_id``."""

    user_id: UUID
    conversation_id: UUID
    unclaimed_conversation_id: UUID
    note_id: str
    message_id: UUID
    experiment_ids: tuple[str, str]
    gene_set_ids: tuple[str, str]
    control_set_id: UUID
    memory_key: str


def _path_keys(path: str) -> set[str]:
    return {token.split(":")[0] for token in re.findall(r"\{([^}]+)\}", path)}


def _nested_models(annotation: object) -> Iterator[type[BaseModel]]:
    """Yield the models one field annotation holds, through any generics.

    A model can sit behind any depth of container, as ``list[X] | None`` does.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for arg in get_args(annotation):
        yield from _nested_models(arg)


def _model_keys(model: type[BaseModel], depth: int) -> set[str]:
    keys: set[str] = set()
    for name, field in model.model_fields.items():
        keys.add(name)
        if field.alias:
            keys.add(field.alias)
        if depth > 0:
            for nested in _nested_models(field.annotation):
                keys |= _model_keys(nested, depth - 1)
    return keys


def _body_keys(route: ApiRoute) -> set[str]:
    """Field names of the request body, one level into nested models."""
    if route.body_model is None:
        return set()
    return _model_keys(route.body_model, depth=1)


def _is_scoped(route: ApiRoute, resource: Resource) -> bool:
    if resource.prefix and route.path.startswith(resource.prefix):
        return True
    return bool((_path_keys(route.path) | _body_keys(route)) & resource.keys)


def scoped_routes(app: FastAPI, resource: Resource) -> set[tuple[str, str]]:
    """Mutating routes that address an instance of ``resource``."""
    found: set[tuple[str, str]] = set()
    for route in api_routes(app.routes):
        if not _is_scoped(route, resource):
            continue
        found |= {
            (method, route.path)
            for method in route.methods & MUTATING_METHODS
            if (resource.name, method, route.path) not in NOT_RESOURCE_SCOPED
        }
    return found


def registered_routes(app: FastAPI) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in api_routes(app.routes):
        found |= {(method, route.path) for method in route.methods}
    return found


def stale_exclusions(app: FastAPI) -> list[str]:
    """Report every exclusion the classifier would no longer make.

    Such an exclusion hides nothing, and its reason no longer describes the app.
    """
    by_name = {resource.name: resource for resource in RESOURCES}
    routes: dict[tuple[str, str], ApiRoute] = {}
    for route in api_routes(app.routes):
        routes.update({(method, route.path): route for method in route.methods})
    stale: list[str] = []
    for (resource_name, method, path), reason in NOT_RESOURCE_SCOPED.items():
        excluded = routes.get((method, path))
        if excluded is None or not _is_scoped(excluded, by_name[resource_name]):
            stale.append(f"{resource_name} {method} {path} ({reason})")
    return stale


def wdk_backed_indexes(blueprints: Sequence[Case]) -> tuple[int, ...]:
    """Positions in ``blueprints`` whose owner request is answered by WDK."""
    return tuple(
        index
        for index, case in enumerate(blueprints)
        if (case.method, case.route) in WDK_BACKED
    )


async def status_for(client: httpx.AsyncClient, case: Case) -> int:
    """The status the route answers with. A stream answers at its status line."""
    response = await client.request(case.method, case.url, json=case.body, timeout=60.0)
    return response.status_code
