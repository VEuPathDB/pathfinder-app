from __future__ import annotations

import pytest
from fastapi import FastAPI

from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.http.test_audit_review_reads import reviewed_run

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)


async def test_a_run_lists_each_finding_its_two_reviews_dispute(app: FastAPI) -> None:
    owner, run_id, ids = await reviewed_run()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()

    assert [
        (line["id"], line["genes"], line["reviewsDisagree"], line["disagreementText"])
        for line in run["disputed"]
    ] == [
        (
            ids["yip1"],
            ["EXA_0102"],
            True,
            (
                "The two independent reviews disagree: the first finds no error, "
                "the second keeps the error"
            ),
        ),
        (
            ids["kinase"],
            ["EXA_0104"],
            True,
            (
                "The two independent reviews disagree: the first keeps the error, "
                "the second finds no error"
            ),
        ),
    ]
