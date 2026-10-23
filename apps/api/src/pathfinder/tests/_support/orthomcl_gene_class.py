from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
import pytest
import respx
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import WDKRecordType, get_site
from veupathdb_mcp.catalog import get_discovery_service

ORTHOMCL = "orthomcl"
RECORD_TYPES = ["group", "sequence", "helper"]
NO_GENE_RECORD_TYPE = "Resource 'record type: gene' does not exist."
NO_GENE_RECORDS = "orthomcl lists no gene record type, so it reads no gene by id"


@dataclass(frozen=True)
class GeneClassWire:
    gene_reads: respx.Route
    record_type_reads: respx.Route


def held_record_types(monkeypatch: pytest.MonkeyPatch) -> None:
    held = [WDKRecordType(url_segment=name) for name in RECORD_TYPES]

    def _held(site_id: str) -> list[WDKRecordType] | None:
        return held if site_id == ORTHOMCL else None

    monkeypatch.setattr(get_discovery_service(), "held_record_types", _held)


@contextmanager
def orthomcl_gene_class() -> Iterator[GeneClassWire]:
    site = get_site(ORTHOMCL)
    service = site.service_url
    token = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{site.web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": 376, "isGuest": False})
            )
            yield GeneClassWire(
                gene_reads=router.post(f"{service}/record-types/gene/records").mock(
                    return_value=httpx.Response(404, text=NO_GENE_RECORD_TYPE)
                ),
                record_type_reads=router.get(f"{service}/record-types").mock(
                    return_value=httpx.Response(200, json=RECORD_TYPES)
                ),
            )
    finally:
        veupathdb_auth_token_ctx.reset(token)
