from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue

from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.unread import Unread
from strategist.services.strategies.sheet_params import criterion_sheets
from strategist.tests._support.bound_values import bound
from strategist.tests._support.narrowing_refused import the_site_refuses_to_narrow
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import suite_search

_DOMAINS = "GenesByInterproDomain"


async def test_a_vocabulary_the_site_refuses_under_moved_parents_is_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = suite_search("search_genes_by_interpro_domain")
    the_site_refuses_to_narrow(monkeypatch, published)
    criterion = Criterion(
        id="dom",
        text="KH domain",
        search_name=_DOMAINS,
        record_class="transcript",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                "domain_database": SinglePickValue(value="Pfam"),
                "domain_typeahead": MultiPickValue(values=["PF00013"]),
            }
        ),
    )

    sheets = await criterion_sheets(
        "plasmodb", [criterion], {_DOMAINS: sheet_of(published.parameters or [])}
    )

    assert sheets == {
        "dom": Unread(
            reason=(
                "the vocabulary under the values it holds was not read: HTTP 503: "
                "VEuPathDB service error: Request failed after retries: "
                "Service Unavailable"
            )
        )
    }
