from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from pathfinder.domain.audit.words import (
    CHECK_TITLES,
    ERROR_TYPE_DESCRIPTIONS,
    ERROR_TYPE_TITLES,
    HALT_SENTENCES,
    LITERATURE_SENTENCES,
    REVIEW_STATUS_SENTENCES,
    UNCHECKED_SENTENCES,
    UNRESOLVED_WORDS,
    VERDICT_KIND_SENTENCES,
)
from pathfinder.transport.http.routers.audits import router

WEB_FIXTURE = (
    Path(__file__).resolve().parents[7] / "packages" / "spec" / "audit_words.json"
)


async def _words() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/audits/words")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def test_the_words_route_serves_every_table_entry_for_entry() -> None:
    assert await _words() == {
        "checks": CHECK_TITLES,
        "errorTypes": ERROR_TYPE_TITLES,
        "errorDescriptions": ERROR_TYPE_DESCRIPTIONS,
        "findingStatuses": UNCHECKED_SENTENCES,
        "unresolved": UNRESOLVED_WORDS,
        "halts": HALT_SENTENCES,
        "verdictKinds": VERDICT_KIND_SENTENCES,
        "literature": LITERATURE_SENTENCES,
        "reviewStatuses": REVIEW_STATUS_SENTENCES,
    }


async def test_the_words_route_keeps_each_table_in_its_order() -> None:
    body = await _words()
    assert list(body["unresolved"]) == list(UNRESOLVED_WORDS)
    assert list(body["checks"]) == list(CHECK_TITLES)


async def test_the_web_fixture_is_the_body_the_route_serves() -> None:
    assert json.loads(WEB_FIXTURE.read_text()) == await _words()
