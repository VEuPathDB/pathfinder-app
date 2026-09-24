"""A request's site_id is bounded, so an oversized value is a 422, not a 500.

The conversations column is String(50); an unbounded request field let a
longer value reach INSERT, where Postgres raises and the route answers 500.
"""

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, TypeAdapter, ValidationError

from pathfinder.transport.http.deps import RequiredSiteIdQuery, SiteIdQuery
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
from pathfinder.transport.http.schemas.gene_sets import GeneSetImportRequest

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
        (OpenConversationRequest, {"siteId": _LONG}),
        (BeginConversationRequest, {"siteId": _LONG}),
        (
            GeneSetImportRequest,
            {"name": "x", "siteId": _LONG, "rawText": "g1"},
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
def test_an_oversized_site_id_is_refused(
    model: type[BaseModel], payload: JSONObject
) -> None:
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


def test_the_site_id_query_annotations_are_bounded() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(RequiredSiteIdQuery).validate_python(_LONG)
    with pytest.raises(ValidationError):
        TypeAdapter(SiteIdQuery).validate_python(_LONG)
    assert TypeAdapter(SiteIdQuery).validate_python(None) is None
