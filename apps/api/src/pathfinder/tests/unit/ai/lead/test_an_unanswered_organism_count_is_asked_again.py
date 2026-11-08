from __future__ import annotations

import pytest

from pathfinder.tests._support.step_tally_site import ToolServer
from pathfinder.tests.unit.ai.lead._site_verdict import UNANSWERED_DIGEST, verify
from pathfinder.tests.unit.ai.lead.test_a_refused_organism_count import (
    _LARGE,
    _PF,
    _connect_error,
    _organism,
    _organisms,
    _Pages,
    _site,
)
from pathfinder.tests.unit.ai.lead.test_a_second_organism_fails_the_verdict import (
    _EXPORTED,
    _exported_deps,
)

pytestmark = pytest.mark.usefixtures("collector")


async def test_an_organism_count_answered_on_the_second_ask_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(
        counts=_organisms((_PF, _LARGE)), refusal=_connect_error(), refused_asks=1
    )
    _site(monkeypatch, _LARGE, server, _Pages())

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    assert (len(server.counted), _organism(digest.review.checks).status) == (2, "pass")
    assert (digest.success, digest.not_checked) == (True, False)


async def test_the_verdict_names_the_one_read_the_site_did_not_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _site(monkeypatch, _LARGE, ToolServer(refusal=_connect_error()), _Pages())

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    passed = sum(check.status == "pass" for check in digest.review.checks)
    assert digest.reason == (
        f"{passed} checks passed; the site did not answer the organism count of "
        f"step {_EXPORTED} ('Text'), so that is not checked"
    )
    assert passed == 3
