from __future__ import annotations

import pytest

from strategist.domain.audit.offered import offers_audits


@pytest.mark.parametrize(
    ("base_url", "offered"),
    [
        ("https://muharram.plasmodb.org/plasmo.amuharram/service", True),
        ("https://muharram.veupathdb.org/eupathdb.amuharram/service", True),
        ("https://qa.plasmodb.org/plasmo.qa/service", False),
        ("https://beta.example.org/site.beta/service", False),
        ("https://example.org/site/service", False),
        ("https://notmuharram.plasmodb.org/plasmo/service", False),
    ],
)
def test_audits_are_offered_only_on_the_muharram_sites(
    base_url: str, offered: bool
) -> None:
    assert offers_audits(base_url) is offered
