from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.errors import WDKError

from strategist.domain.strategy.operational_spec import BoundValue, Criterion
from strategist.domain.strategy.step_naming import criterion_title
from strategist.services.strategies import search_sheets
from strategist.services.strategies.search_sheets import radio_pairs_of

_INTERPRO = "GenesByInterproDomain"
_DOWN = WDKError("down", status=503)


async def _listed(_site: str, names: list[str]) -> dict[str, str]:
    return dict.fromkeys(names, "transcript")


async def _unread(*_args: object) -> NoReturn:
    raise _DOWN


def _named(pairs: dict[str, str]) -> str:
    return criterion_title(
        Criterion(
            id="c1",
            text="kinase domain",
            search_name=_INTERPRO,
            search_display_name="InterPro Domain",
            radio_pairs=pairs,
            resolved_params={
                "domain_typeahead": BoundValue(
                    value=StringValue(value="N/A"), source="chosen"
                ),
                "domain_accession": BoundValue(
                    value=StringValue(value="PF00069"), source="chosen"
                ),
            },
        )
    ).name


async def test_an_unread_definition_names_the_step_less_specifically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_sheets, "search_record_types", _listed)
    monkeypatch.setattr(search_sheets, "read_search_definition", _unread)

    pairs = await radio_pairs_of("plasmodb", [_INTERPRO])

    assert (pairs, _named({})) == ({}, "InterPro Domain")
    assert _named({"domain_typeahead": "domain_accession"}) == (
        "InterPro Domain: PF00069"
    )
