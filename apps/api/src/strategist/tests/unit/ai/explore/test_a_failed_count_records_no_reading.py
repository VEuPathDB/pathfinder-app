from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry

from strategist.ai.explore.explore_tools import propose_readings
from strategist.ai.explore.readings_card import proposal_counts
from strategist.ai.models.mock.arc_args import SIGNALP_VERSIONS
from strategist.ai.models.mock.site_values import SiteValues
from strategist.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE
from strategist.services.experiment.reading_count import ProposedReading
from strategist.tests._support.explore_turns import SITE, serve_recorded_readings
from strategist.tests._support.run_context import lead_run_context


def _reading(label: str, search_name: str, **parameters: Any) -> ProposedReading:
    return ProposedReading.model_validate(
        {
            "title": label,
            "searches": [
                {"label": label, "searchName": search_name, "parameters": parameters}
            ],
        }
    )


async def test_a_failed_call_records_none_of_its_readings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)
    organism = {
        "type": "multi-pick-vocabulary",
        "values": [SiteValues.for_site(SITE).organism],
    }
    readings = [
        _reading(
            "signal peptide",
            SIGNAL_PEPTIDE,
            organism=organism,
            signalp_version={
                "type": "single-pick-vocabulary",
                "value": SIGNALP_VERSIONS[0],
            },
        ),
        _reading(
            "no such gene type",
            GENE_TYPE,
            organism=organism,
            geneType={"type": "multi-pick-vocabulary", "values": ["no such type"]},
        ),
    ]

    with pytest.raises(ModelRetry):
        await propose_readings(ctx, readings)

    assert (proposal_counts(ctx.deps), ctx.deps.state.domain.offered_readings) == (
        {},
        {},
    )
