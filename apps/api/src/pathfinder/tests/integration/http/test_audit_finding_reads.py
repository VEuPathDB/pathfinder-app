"""A finding read from its routes names the verdict its check gave and whether it is a gene target."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from pathfinder.tests.integration.http._audit_reads import (
    screened_genome_run,
    stored_intron_run,
    stored_pair_run,
)
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)


async def test_a_finding_names_its_verdict_and_where_it_came_from(
    app: FastAPI,
) -> None:
    owner, run_id, pair_id = await stored_pair_run()
    screened_owner, screened_run = await screened_genome_run()
    async with client_for(app, owner.user_id) as client:
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id}")
        ).json()
    async with client_for(app, screened_owner.user_id) as client:
        screened = (await client.get(f"/api/v1/audits/{screened_run}/findings")).json()
    assert [(f["id"], f["verdict"], f["fromTarget"]) for f in page["findings"]] == [
        (pair_id, "INTACT", True),
        (pair_id + 1, None, True),
    ]
    assert (detail["finding"]["verdict"], detail["finding"]["fromTarget"]) == (
        "INTACT",
        True,
    )
    assert [
        (f["verdictText"], f["checkTitle"], f["errorTitle"]) for f in page["findings"]
    ] == [
        (
            "The strain's DNA encodes the whole protein, so the pseudogene call is wrong",
            "Pseudogene calls on intact genes",
            "Intact gene called a pseudogene",
        ),
        (None, "Gene length against orthologs", None),
    ]
    assert [group["kind"] for group in detail["facts"]] == ["confirmation"]
    assert detail["facts"][0]["facts"][0] == {
        "label": "Reference coding sequence",
        "value": "1,386 bases",
    }
    assert [(f["verdict"], f["fromTarget"]) for f in screened["findings"]] == [
        (None, False),
        (None, False),
    ]


async def test_an_intron_finding_reads_with_its_verdict(app: FastAPI) -> None:
    owner, run_id, finding_id = await stored_intron_run()
    async with client_for(app, owner.user_id) as client:
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
    assert [
        (f["id"], f["check"], f["verdict"], f["errorType"]) for f in page["findings"]
    ] == [(finding_id, "intron_support", "UNSUPPORTED_MISSING_EXON", "missing_exon")]
