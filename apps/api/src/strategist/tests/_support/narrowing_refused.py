from __future__ import annotations

import httpx
import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.strategy import StepValidation
from veupathdb.wdk import VEuPathDBClient, WDKSearch, WDKSearchResponse, get_site
from veupathdb_mcp.catalog import get_discovery_service

from strategist.tests._support.site_failures import unavailable


def the_site_refuses_to_narrow(
    monkeypatch: pytest.MonkeyPatch, published: WDKSearch
) -> None:
    """The catalog holds ``published`` and the site answers every read under
    parent values with a 503."""
    view = WDKSearchResponse(
        search_data=published,
        validation=StepValidation(level="NONE", is_valid=False),
    )

    async def _held(
        ctx: SearchContext, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del ctx, expand_params
        return view

    narrow = VEuPathDBClient.get_search_details_with_params

    async def _refused(
        client: VEuPathDBClient,
        record_type: str,
        search_name: str,
        context: dict[str, str],
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        site = VEuPathDBClient(
            base_url=get_site(client.site_id).service_url,
            auth_token="registered",
            transport=httpx.MockTransport(unavailable),
        )
        try:
            return await narrow(
                site, record_type, search_name, context, expand_params=expand_params
            )
        finally:
            await site.close()

    monkeypatch.setattr(get_discovery_service(), "get_search_details", _held)
    monkeypatch.setattr(VEuPathDBClient, "get_search_details_with_params", _refused)
