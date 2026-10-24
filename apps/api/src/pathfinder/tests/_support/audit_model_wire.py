from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import respx
from pydantic import Base64Bytes, BaseModel, ConfigDict, Field, JsonValue
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import get_site

_WIRE = Path(__file__).resolve().parents[1] / "fixtures/audit_models/gt1_selk_wire.json"
_USER = 376


class RecordExchange(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_type: str
    primary_key: dict[str, str]
    tables: list[str]
    status: int
    body: JsonValue


class StoreExchange(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    byte_range: str
    status: int
    body: Base64Bytes


class RecordWire(BaseModel):
    model_config = ConfigDict(frozen=True)

    site: str
    records: list[RecordExchange]
    store: list[StoreExchange]


class _PrimaryKey(BaseModel):
    name: str
    value: str


class _RecordRequest(BaseModel):
    primary_key: list[_PrimaryKey] = Field(alias="primaryKey")
    tables: list[str] = []


SELK_WIRE = RecordWire.model_validate_json(_WIRE.read_text())


class ServedWire:
    def __init__(self, wire: RecordWire) -> None:
        self.wire = wire
        self.records: list[tuple[str, str, tuple[str, ...]]] = []
        self.store: list[tuple[str, str]] = []

    def record(self, request: httpx.Request) -> httpx.Response:
        asked = _RecordRequest.model_validate_json(request.content)
        key = {part.name: part.value for part in asked.primary_key}
        kind = request.url.path.split("/record-types/")[1].split("/")[0]
        exchange = self.wire.records[len(self.records)]
        self.records.append((kind, key["source_id"], tuple(asked.tables)))
        expected = (exchange.record_type, exchange.primary_key, exchange.tables)
        if (kind, key, asked.tables) != expected:
            return httpx.Response(500, json={"unexpected": [kind, key, asked.tables]})
        return httpx.Response(exchange.status, json=exchange.body)

    def read(self, request: httpx.Request) -> httpx.Response:
        asked = (str(request.url), request.headers.get("range", ""))
        self.store.append(asked)
        for exchange in self.wire.store:
            if (exchange.url, exchange.byte_range) == asked:
                return httpx.Response(exchange.status, content=exchange.body)
        return httpx.Response(404)


@contextmanager
def served_wire(wire: RecordWire) -> Iterator[ServedWire]:
    site = get_site(wire.site)
    service = site.service_url
    served = ServedWire(wire)
    token = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{site.web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
            )
            router.post(
                url__regex=rf"^{re.escape(service)}/record-types/\w+/records$"
            ).mock(side_effect=served.record)
            router.get(url__startswith=f"{service}/jbrowse/").mock(
                side_effect=served.read
            )
            yield served
    finally:
        veupathdb_auth_token_ctx.reset(token)
