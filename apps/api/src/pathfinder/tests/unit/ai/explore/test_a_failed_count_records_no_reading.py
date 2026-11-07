from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.explore.explore_tools import propose_readings
from pathfinder.ai.explore.readings_card import counted_labels
from pathfinder.ai.models.mock.arc_args import SIGNALP_VERSIONS
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE
from pathfinder.services.experiment.variant_comparison import VariantInput
from pathfinder.tests._support.explore_turns import SITE, serve_recorded_readings
from pathfinder.tests._support.run_context import lead_run_context


def _reading(label: str, search_name: str, **parameters: Any) -> VariantInput:
    return VariantInput.model_validate(
        {"label": label, "search_name": search_name, "parameters": parameters}
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

    assert counted_labels(ctx.deps) == {}
