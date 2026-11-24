from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.parameters import HeldValue, StringValue
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyAPI
from veupathdb_mcp.wdk import WireStep

from strategist.domain.site_checks import SiteCheck
from strategist.services.strategies import held_values, site_changes
from strategist.tests.unit.ai.lead._d3_site import (
    bound,
    bound_values,
    site_step,
    the_recorded_site,
)

_REFUSED = WDKError("The search's parameters were not read", status=503)
_MOVED = "%hsap:Y%padl:Y%"


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    the_recorded_site(monkeypatch)


async def _unanswered(*_args: object) -> NoReturn:
    raise _REFUSED


async def _held_raw(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    del api
    for node in walk(payload.root):
        node.parameters = {
            name: HeldValue(wire=value)
            for name, value in wire[node.id].parameters.items()
        }


async def _search_unanswered(
    site_id: str, record_type: str, search_name: str
) -> NoReturn:
    del site_id, record_type, search_name
    raise _REFUSED


async def test_a_search_the_site_did_not_read_leaves_the_values_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(held_values, "catalog_search_definition", _search_unanswered)

    check = await bound_values(site_step(profile_pattern=_MOVED))

    assert check == SiteCheck(
        kind="bound_values",
        subject="the strategy on the site",
        status="unchecked",
        evidence=(
            "step 227357790 ('Orthology Phylogenetic Profile'): the site did not "
            "read the search's parameters: HTTP 503: VEuPathDB service error: The search's parameters were not read"
        ),
        why_unchecked="site_unanswered",
    )


async def test_values_the_site_did_not_decode_are_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _unanswered)

    check = await bound_values(site_step(profile_pattern=_MOVED))

    assert (check.status, check.why_unchecked, check.evidence) == (
        "unchecked",
        "site_unanswered",
        (
            "step 227357790 ('Orthology Phylogenetic Profile'): the site's values did "
            "not decode: HTTP 503: VEuPathDB service error: The search's parameters were not read"
        ),
    )


async def test_a_value_held_only_as_its_wire_text_is_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _held_raw)

    check = await bound_values(site_step(profile_pattern=_MOVED))

    assert (check.status, check.evidence) == (
        "unchecked",
        (
            "step 227357790 ('Orthology Phylogenetic Profile'): the site holds "
            "profile_pattern only as its wire text"
        ),
    )


async def test_a_bound_name_the_site_does_not_hold_is_a_difference() -> None:
    parameters = {**bound(), "min_count": StringValue(value="2")}

    check = await bound_values(site_step(), parameters)

    assert (check.status, check.evidence) == (
        "fail",
        (
            "step 227357790 ('Orthology Phylogenetic Profile') holds no value for "
            "min_count, the spec binds '2'"
        ),
    )


async def test_a_difference_outweighs_a_value_that_did_not_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _held_raw)
    parameters = {**bound(), "min_count": StringValue(value="2")}

    check = await bound_values(site_step(profile_pattern=_MOVED), parameters)

    assert (check.status, check.evidence) == (
        "fail",
        (
            "step 227357790 ('Orthology Phylogenetic Profile') holds no value for "
            "min_count, the spec binds '2'"
        ),
    )
