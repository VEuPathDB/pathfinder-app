import httpx
from veupathdb.domain.parameters.values import SinglePickValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.transport.http.schemas import StepCountsRequest


async def test_step_counts_unknown_site_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    leaf = StrategyStepNode(
        search_name="GenesByTaxon",
        display_name="Taxon",
        parameters={"organism": SinglePickValue(value="Plasmodium falciparum 3D7")},
        id="step_leaf01",
    )
    request = StepCountsRequest(
        site_id="not-a-real-site",
        strategy_ast=StrategyAst(record_type="transcript", root=leaf),
    )
    resp = await authed_client.post(
        "/api/v1/conversations/step-counts",
        json=request.model_dump(by_alias=True, mode="json"),
    )
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
