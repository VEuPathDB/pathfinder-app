"""The evidence card holds exactly what a live control test and a live read returned.

The step returns the P. falciparum genes of 10 to 20 kDa. The controls mix genes
of that step with genes of 60 to 70 kDa, which it cannot return, so each list of
the card is known before the test runs.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from veupathdb.wdk import (
    NewStepSpec,
    WDKSearchConfig,
    WDKStepTree,
    get_site,
    get_strategy_api,
)
from veupathdb_mcp.controls import run_step_control_tests
from veupathdb_mcp.tool_payloads import ControlOutcome
from veupathdb_mcp.wdk import fetch_gene_ids_from_step

from pathfinder.ai.lead.evidence_card import CardSources, assemble_evidence_card
from pathfinder.ai.tools.standalone.experiment import control_test_run
from pathfinder.domain.evidence import EvidenceVerdict, VerificationReview
from pathfinder.domain.strategy.build_outcome import NodeResult
from pathfinder.services.strategies.site_counts import read_step_counts

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"


async def _heavy_gene_ids() -> list[str]:
    """Genes of 60 to 70 kDa, none of which a 10 to 20 kDa step returns."""
    api = get_strategy_api(_SITE)
    step = await api.create_step(
        NewStepSpec(
            search_name="GenesByMolecularWeight",
            search_config=WDKSearchConfig(
                parameters={
                    "organism": '["Plasmodium falciparum 3D7"]',
                    "min_molecular_weight": "60000",
                    "max_molecular_weight": "70000",
                }
            ),
        ),
        record_type="transcript",
    )
    # The site reports a step only inside a strategy, and deletes both together.
    strategy = await api.create_strategy(
        WDKStepTree(step_id=step.id), name="pathfinder-live-lane", is_internal=True
    )
    try:
        return list(dict.fromkeys(await fetch_gene_ids_from_step(api, step_id=step.id)))
    finally:
        with contextlib.suppress(Exception):
            await api.delete_strategy(strategy.id)


async def test_the_card_holds_what_the_test_and_the_site_returned(
    owned_strategy: Callable[[str], Awaitable[tuple[int, int]]],
) -> None:
    strategy_id, step_id = await owned_strategy(_SITE)
    api = get_strategy_api(_SITE)
    light = list(dict.fromkeys(await fetch_gene_ids_from_step(api, step_id=step_id)))
    heavy = await _heavy_gene_ids()
    positives = [*light[:20], *heavy[:5]]
    negatives = [*light[20:22], *heavy[5:35]]

    measured = await run_step_control_tests(
        _SITE, step_id, positive_controls=positives, negative_controls=negatives
    )
    reported = ControlOutcome.model_validate(measured).model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )
    reported["targetLabel"] = "Genes by Molecular Weight"
    run = control_test_run(reported, tool_call_id="call_controls")
    assert run is not None
    details = await api.get_strategy(strategy_id)
    site_size = details.steps[str(step_id)].estimated_size

    card = assemble_evidence_card(
        CardSources(
            check_id="call_verify",
            revision="live",
            site_id=_SITE,
            labels={"s1": "Genes by Molecular Weight"},
            live_wdk_step_ids=frozenset({step_id}),
            wdk_strategy_id=strategy_id,
            root_wdk_step_id=step_id,
            node_results=(
                NodeResult(
                    node_id="s1",
                    search_name="GenesByMolecularWeight",
                    wdk_step_id=step_id,
                    count=site_size,
                    status="ok",
                ),
            ),
            spec=None,
            control_tests=(run,),
            verdict=EvidenceVerdict(supported=True),
            review=VerificationReview(),
        ),
        await read_step_counts(_SITE, strategy_id),
        checked_at=datetime.now(UTC),
    )

    tested = card.controls[0]
    assert tested.positive is not None
    assert tested.negative is not None
    assert tested.positive.returned == sorted(light[:20])
    assert tested.positive.not_returned == sorted(heavy[:5])
    assert tested.negative.returned == sorted(light[20:22])
    assert tested.negative.not_returned == sorted(heavy[5:35])
    assert [(step.recorded_count, step.site_count) for step in card.steps] == [
        (site_size, site_size)
    ]
    assert card.strategy_url == get_site(_SITE).strategy_url(strategy_id, step_id)
