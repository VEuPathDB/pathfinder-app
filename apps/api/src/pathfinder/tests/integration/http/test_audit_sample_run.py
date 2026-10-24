"""The sample run reads through the routes exactly as the web fixture holds it."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from veupathdb_mcp.audit import INTRON_STORE_READS

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ForbiddenError
from pathfinder.services.audit.sample_run import SampleRunIds, store_sample_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.transport.http.routers import dev

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

REPO = Path(__file__).resolve().parents[7]
FIXTURE = REPO / "apps/web/src/features/audit/__fixtures__/sampleRun.json"
RUN_ID = "00000000-0000-4000-8000-000000000001"
CONVERSATION_ID = "00000000-0000-4000-8000-000000000002"
AT = "2026-10-22T00:00:00Z"
SAMPLE_ROUTE = "/api/v1/dev/audits/sample"

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None


def _field(key: str, item: Json, ids: dict[str, Json]) -> Json:
    match key:
        case "createdAt" | "finishedAt" | "deadlineAt" if item is not None:
            return AT
        case "id" | "conversationId" if str(item) in ids:
            return ids[str(item)]
        case _:
            return _fixed(item, ids)


def _fixed(value: Json, ids: dict[str, Json]) -> Json:
    match value:
        case dict():
            return {key: _field(key, item, ids) for key, item in value.items()}
        case list():
            return [_fixed(item, ids) for item in value]
        case _:
            return value


def fixed_ids(body: Json, stored: SampleRunIds, conversation_id: UUID) -> Json:
    ids: dict[str, Json] = {
        str(stored.run_id): RUN_ID,
        str(conversation_id): CONVERSATION_ID,
        **{str(fid): place for place, fid in enumerate(stored.finding_ids, start=1)},
    }
    return _fixed(body, ids)


async def test_the_sample_run_reads_as_the_web_fixture_holds_it(app: FastAPI) -> None:
    user = (await seed_thread()).user_id
    stored = await store_sample_run(user)
    async with client_for(app, user) as client:
        run = (await client.get(f"/api/v1/audits/{stored.run_id}")).json()
        findings = (
            await client.get(
                f"/api/v1/audits/{stored.run_id}/findings", params={"limit": 50}
            )
        ).json()
        details = [
            (await client.get(f"/api/v1/audits/{stored.run_id}/findings/{fid}")).json()
            for fid in stored.finding_ids
        ]
    read = fixed_ids(
        {"run": run, "findings": findings, "details": details},
        stored,
        UUID(run["run"]["conversationId"]),
    )
    if not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(read, indent=2) + "\n")
    assert json.loads(FIXTURE.read_text()) == read
    assert (run["run"]["phase"], run["action"], run["left"]["total"]) == (
        "finished",
        "retry",
        4,
    )
    assert [f["impact"] for f in findings["findings"][:5]] == [
        0.5,
        0.25,
        0.25,
        0.25,
        0.25,
    ]
    assert [line["id"] for line in run["headline"]] == [
        stored.finding_ids[i] for i in (0, 7, 8, 9)
    ]
    assert (run["reviewState"]["status"], run["reviewState"]["done"]) == (
        "synthesized",
        5,
    )
    assert (run["agreement"]["sampled"], run["agreement"]["agreed"]) == (2, 1)
    assert (run["requests"], run["storeReads"]) == (21, INTRON_STORE_READS)
    assert sum(g["geneCount"] for g in run["genomes"] if g["role"] == "audited") == 2
    assert details[9]["models"]["proposed"]["cds"][1] == [1381887, 1382044]
    assert [d["models"]["kind"] if d["models"] else None for d in details] == [
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "strain",
        None,
        "intron",
    ]


async def test_the_sample_route_stores_one_run_with_ten_findings(app: FastAPI) -> None:
    user = (await seed_thread()).user_id
    async with client_for(app, user) as client:
        response = await client.post(SAMPLE_ROUTE)
        body = response.json()
        run = await client.get(f"/api/v1/audits/{body['runId']}")
    assert (response.status_code, sorted(body), len(body["findingIds"])) == (
        200,
        ["findingIds", "runId"],
        10,
    )
    assert body["findingIds"] == sorted(body["findingIds"])
    assert (run.status_code, run.json()["run"]["status"]) == (200, "finished")


async def test_the_sample_route_refuses_outside_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = (await seed_thread()).user_id
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "openai")

    with pytest.raises(ForbiddenError, match="Only available in mock mode"):
        await dev.store_sample_audit_run(user)
