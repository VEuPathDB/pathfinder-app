from __future__ import annotations

import json

import pytest

from strategist.domain.site_checks import SiteCheck
from strategist.tests.unit.ai.lead._d3_site import (
    D3,
    bound_values,
    site_step,
    the_recorded_site,
)


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    the_recorded_site(monkeypatch)


def test_the_push_sent_the_leaves_of_the_bound_parent() -> None:
    sent = json.loads(D3["pushed"]["searchConfig"]["parameters"]["organism"])

    assert (D3["boundParameters"]["organism"]["values"], len(sent)) == (
        ["Plasmodium"],
        61,
    )


async def test_the_site_holding_the_leaves_the_push_sent_passes() -> None:
    check = await bound_values(site_step())

    assert check == SiteCheck(
        kind="bound_values",
        subject="the strategy on the site",
        status="pass",
        evidence="the site holds every value the spec binds on 1 search step",
    )


async def test_a_site_holding_other_leaves_still_fails() -> None:
    check = await bound_values(site_step(organism='["Plasmodium berghei ANKA"]'))

    assert (check.status, check.evidence) == (
        "fail",
        (
            "step 227357790 ('Orthology Phylogenetic Profile') holds "
            "'[\"Plasmodium berghei ANKA\"]' for "
            "organism, the spec binds '[\"Plasmodium\"]'"
        ),
    )
