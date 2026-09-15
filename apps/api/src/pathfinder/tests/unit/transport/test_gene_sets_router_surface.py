"""The gene-set router's routes, in the order it registers them.

The published spec is compared as text, so the registration order is part of
the contract: a route that moves between sub-routers changes the document.
"""

from __future__ import annotations

from pathfinder.tests._support.routes import ApiRoute, api_routes
from pathfinder.transport.http.routers import gene_sets

_EXPECTED: list[tuple[str, str]] = [
    ("POST", "/api/v1/gene-sets"),
    ("GET", "/api/v1/gene-sets"),
    ("POST", "/api/v1/gene-sets/{gene_set_id}/retake"),
    ("DELETE", "/api/v1/gene-sets/{gene_set_id}"),
    ("POST", "/api/v1/gene-sets/{gene_set_id}/export"),
    ("POST", "/api/v1/gene-sets/import"),
    ("POST", "/api/v1/gene-sets/operations"),
    ("POST", "/api/v1/gene-sets/reverse-search"),
    ("POST", "/api/v1/gene-sets/ensemble"),
    ("POST", "/api/v1/gene-sets/{gene_set_id}/enrich"),
    ("GET", "/api/v1/gene-sets/{gene_set_id}/results/attributes"),
    ("GET", "/api/v1/gene-sets/{gene_set_id}/results/records"),
    (
        "GET",
        "/api/v1/gene-sets/{gene_set_id}/results/distributions/{attribute_name}",
    ),
    ("POST", "/api/v1/gene-sets/{gene_set_id}/results/record"),
    ("GET", "/api/v1/gene-sets/{gene_set_id}/experiments"),
    ("POST", "/api/v1/gene-sets/confidence"),
    ("POST", "/api/v1/gene-sets/{gene_set_id}/vdi-publication"),
    ("GET", "/api/v1/gene-sets/{gene_set_id}/vdi-publication"),
]

_EXPECTED_NAMES: list[str] = [
    "create_gene_set",
    "list_gene_sets",
    "retake_gene_set",
    "delete_gene_set",
    "export_gene_set_endpoint",
    "import_gene_set",
    "set_operations",
    "reverse_search",
    "ensemble_scoring",
    "enrich_gene_set",
    "get_gene_set_attributes",
    "get_gene_set_records",
    "get_gene_set_distribution",
    "get_gene_set_record_detail",
    "list_gene_set_experiments",
    "gene_confidence",
    "publish_gene_set_to_vdi",
    "get_gene_set_vdi_publication",
]


def _routes() -> list[ApiRoute]:
    return api_routes(gene_sets.router.routes)


def test_the_routes_are_registered_in_the_published_order() -> None:
    actual = [pair for route in _routes() for pair in route.pairs]

    assert actual == _EXPECTED


def test_every_route_keeps_its_operation_name() -> None:
    """The name is the operationId the spec publishes."""
    assert [route.name for route in _routes()] == _EXPECTED_NAMES


def test_every_route_carries_the_gene_sets_tag() -> None:
    assert {tag for route in _routes() for tag in route.tags} == {"gene-sets"}
