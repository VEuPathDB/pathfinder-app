"""Whether the pinned EDA fixtures still describe the live deployment.

A failure here is the signal to re-record:
``python -m pathfinder.tests._support.eda_fixtures record``.
"""

from __future__ import annotations

import json

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import get_eda_client

from pathfinder.tests._support.eda_fixtures import (
    FIXTURES,
    SITE_ID,
    EdaFixtureRequest,
    body_shape,
    load_provenance,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
class TestThePinnedFixturesStillHold:
    async def test_the_stored_body_still_matches_its_provenance(
        self, fixture: EdaFixtureRequest
    ) -> None:
        """The file on disk is the response the provenance describes."""
        recorded = load_provenance()[fixture.name]
        stored = json.loads(fixture.file.read_text())

        assert body_shape(stored) == recorded.body_shape

    async def test_the_live_body_shape_is_unchanged(
        self, fixture: EdaFixtureRequest, require_wdk_creds: str
    ) -> None:
        recorded = load_provenance()[fixture.name]
        token = veupathdb_auth_token_ctx.set(require_wdk_creds)
        try:
            live = await get_eda_client(SITE_ID).request_json(
                fixture.method,
                fixture.path,
                json=fixture.body,
                params=fixture.params or None,
            )
        finally:
            veupathdb_auth_token_ctx.reset(token)

        assert body_shape(live) == recorded.body_shape


async def test_every_fixture_on_disk_is_in_the_manifest() -> None:
    """A fixture the manifest does not name has no provenance and no drift test."""
    named = {fixture.file.name for fixture in FIXTURES}
    on_disk = {
        path.name
        for path in FIXTURES[0].file.parent.glob("*.json")
        if path.name != "provenance.json"
    }

    assert on_disk == named
