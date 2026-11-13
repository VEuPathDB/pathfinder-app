import httpx


async def test_strategy_gene_ids_malformed_uuid_returns_422(
    authed_client: httpx.AsyncClient,
) -> None:
    resp = await authed_client.post(
        "/api/v1/eval/strategy-gene-ids",
        json={"strategyId": "not-a-uuid", "siteId": "plasmodb"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
