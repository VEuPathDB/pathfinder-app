"""A request's site_id is bounded, so an oversized value is a 422, not a 500.

The conversations column is String(50); an unbounded request field let a
longer value reach INSERT, where Postgres raises and the route answers 500.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from pathfinder.transport.http.deps import RequiredSiteIdQuery, SiteIdQuery
from pathfinder.transport.http.routers.control_sets import CreateControlSetRequest
from pathfinder.transport.http.routers.evaluation import (
    BuildGoldRequest,
    FetchGeneIdsRequest,
)
from pathfinder.transport.http.schemas.conversations import (
    BeginConversationRequest,
    CreateConversationRequest,
    OpenConversationRequest,
    PushConversationRequest,
    StepCountsRequest,
)
from pathfinder.transport.http.schemas.experiments import CreateExperimentRequest
from pathfinder.transport.http.schemas.gene_sets import (
    CreateGeneSetRequest,
    GeneSetImportRequest,
    ReverseSearchRequest,
)

_LONG = "s" * 51
_AST = {"recordType": "transcript", "root": {"searchName": "GenesByTaxon"}}


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            CreateConversationRequest,
            {"name": "x", "siteId": _LONG, "strategyAst": _AST},
        ),
        (
            PushConversationRequest,
            {"name": "x", "siteId": _LONG, "strategyAst": _AST},
        ),
        (StepCountsRequest, {"siteId": _LONG, "strategyAst": _AST}),
        (
            CreateGeneSetRequest,
            {"name": "x", "siteId": _LONG, "geneIds": ["g1"]},
        ),
        (
            ReverseSearchRequest,
            {"positiveGeneIds": ["g1"], "siteId": _LONG},
        ),
        (OpenConversationRequest, {"siteId": _LONG}),
        (BeginConversationRequest, {"siteId": _LONG}),
        (
            CreateExperimentRequest,
            {
                "siteId": _LONG,
                "recordType": "transcript",
                "positiveControls": [],
                "negativeControls": [],
                "controlsSearchName": "GeneByLocusTag",
                "controlsParamName": "ds_gene_ids",
            },
        ),
        (
            GeneSetImportRequest,
            {"name": "x", "siteId": _LONG, "rawText": "g1"},
        ),
        (
            CreateControlSetRequest,
            {"name": "x", "siteId": _LONG, "recordType": "transcript"},
        ),
        (
            BuildGoldRequest,
            {"goldId": "g", "siteId": _LONG, "stepTree": {}},
        ),
        (
            FetchGeneIdsRequest,
            {
                "strategyId": "8f14e45f-ceea-467a-9e58-2b1c9d3e4a5b",
                "siteId": _LONG,
            },
        ),
    ],
)
def test_an_oversized_site_id_is_refused(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_a_real_site_id_still_passes() -> None:
    parsed = CreateConversationRequest.model_validate(
        {"name": "x", "siteId": "plasmodb", "strategyAst": _AST},
    )

    assert parsed.site_id == "plasmodb"


def test_an_empty_site_id_is_refused() -> None:
    with pytest.raises(ValidationError):
        StepCountsRequest.model_validate({"siteId": "", "strategyAst": _AST})


def test_oversized_gene_set_search_fields_are_refused() -> None:
    base = {"name": "x", "siteId": "plasmodb", "geneIds": ["g1"]}
    with pytest.raises(ValidationError):
        CreateGeneSetRequest.model_validate({**base, "searchName": "s" * 256})
    with pytest.raises(ValidationError):
        CreateGeneSetRequest.model_validate({**base, "recordType": "r" * 101})


def test_the_site_id_query_annotations_are_bounded() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(RequiredSiteIdQuery).validate_python(_LONG)
    with pytest.raises(ValidationError):
        TypeAdapter(SiteIdQuery).validate_python(_LONG)
    assert TypeAdapter(SiteIdQuery).validate_python(None) is None
