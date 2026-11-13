from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import ModelRetry

from strategist.ai.explore.explore_tools import ProposedCount, propose_readings
from strategist.ai.explore.readings_card import proposal_counts
from strategist.ai.models.mock.arc_args import SIGNALP_VERSIONS
from strategist.ai.models.mock.site_values import SiteValues
from strategist.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE
from strategist.services.experiment.reading_count import ProposedReading
from strategist.tests._support.explore_turns import (
    GENE_TYPE_REPORT,
    SIGNAL_PEPTIDE_REPORT,
    SITE,
    serve_recorded_readings,
)
from strategist.tests._support.recorded_counts import recorded_count
from strategist.tests._support.run_context import lead_run_context

_ORGANISM = {
    "type": "multi-pick-vocabulary",
    "values": [SiteValues.for_site(SITE).organism],
}
_PEPTIDE: dict[str, Any] = {
    "label": "peptide",
    "searchName": SIGNAL_PEPTIDE,
    "parameters": {
        "organism": _ORGANISM,
        "signalp_version": {
            "type": "single-pick-vocabulary",
            "value": SIGNALP_VERSIONS[0],
        },
    },
}
_CODING: dict[str, Any] = {
    "label": "coding",
    "searchName": GENE_TYPE,
    "parameters": {
        "organism": _ORGANISM,
        "geneType": {"type": "multi-pick-vocabulary", "values": ["protein coding"]},
    },
}
_MINUS = {
    "kind": "combine",
    "operator": "MINUS",
    "inputs": [
        {"kind": "leaf", "criterionId": "coding"},
        {"kind": "leaf", "criterionId": "peptide"},
    ],
}


_PROPOSED: TypeAdapter[list[ProposedCount]] = TypeAdapter(list[ProposedCount])


def _proposal(**fields: Any) -> ProposedReading:
    return ProposedReading.model_validate({"title": "a plan", **fields})


async def test_a_combined_proposal_is_counted_and_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)

    result = await propose_readings(
        ctx,
        [
            _proposal(
                title="Coding genes with no signal peptide",
                searches=[_CODING, _PEPTIDE],
                structure=_MINUS,
            )
        ],
    )

    expected = recorded_count(GENE_TYPE_REPORT) - recorded_count(SIGNAL_PEPTIDE_REPORT)
    [proposed] = _PROPOSED.validate_python(result.return_value)
    domain = ctx.deps.state.domain
    assert proposed.gene_count == expected
    assert proposed.label == "Coding genes with no signal peptide"
    assert " MINUS " in proposed.plan
    assert proposal_counts(ctx.deps) == {proposed.label: expected}
    assert ctx.deps.state.turn_markers.proposed_readings == [proposed.label]
    assert [c.id for c in domain.offered_readings[proposed.label].spec.criteria] == [
        "coding",
        "peptide",
    ]


async def test_one_search_needs_no_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)

    result = await propose_readings(ctx, [_proposal(searches=[_PEPTIDE])])

    assert [p.gene_count for p in _PROPOSED.validate_python(result.return_value)] == [
        recorded_count(SIGNAL_PEPTIDE_REPORT)
    ]


async def test_words_beside_the_plan_are_kept_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)
    also = "Then map the result to orthologs in Plasmodium berghei."

    result = await propose_readings(ctx, [_proposal(searches=[_PEPTIDE], also=also)])

    [proposed] = _PROPOSED.validate_python(result.return_value)
    assert proposed.also == also
    assert ctx.deps.state.domain.offered_readings[proposed.label].also == also


async def test_two_proposals_of_one_plan_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)

    with pytest.raises(ModelRetry):
        await propose_readings(
            ctx,
            [
                _proposal(title="one", searches=[_PEPTIDE]),
                _proposal(title="two", searches=[_PEPTIDE]),
            ],
        )

    assert ctx.deps.state.domain.offered_readings == {}


def test_two_searches_need_a_structure() -> None:
    with pytest.raises(ValidationError, match="states how its 2 searches combine"):
        _proposal(searches=[_CODING, _PEPTIDE])


def test_a_structure_that_leaves_out_a_search_is_refused() -> None:
    with pytest.raises(ValidationError, match="leaves out peptide"):
        _proposal(
            searches=[_CODING, _PEPTIDE],
            structure={"kind": "leaf", "criterionId": "coding"},
        )


async def test_a_later_call_replaces_the_turns_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)
    await propose_readings(ctx, [_proposal(searches=[_PEPTIDE])])

    result = await propose_readings(
        ctx,
        [_proposal(title="later", searches=[_CODING, _PEPTIDE], structure=_MINUS)],
    )

    [proposed] = _PROPOSED.validate_python(result.return_value)
    assert ctx.deps.state.turn_markers.proposed_readings == [proposed.label]


async def test_one_title_for_two_plans_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_readings(monkeypatch)
    ctx = lead_run_context(site_id=SITE)

    with pytest.raises(ModelRetry, match="same title"):
        await propose_readings(
            ctx,
            [
                _proposal(title="signal", searches=[_PEPTIDE]),
                _proposal(title="signal", searches=[_CODING]),
            ],
        )
