"""A control result is backed by this message's control results or the last check's card.

A control result comes from a control test, a scored comparison or a sweep, and
a restatement of the previous message's check reads that check's card while the
strategy holds the revision that check judged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic_ai import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, hold_the_turn_contract
from pathfinder.ai.lead.verify_dispatch import verification_scope
from pathfinder.ai.tools.standalone import scored_comparison
from pathfinder.ai.tools.standalone.scored_comparison import compare_variants_scored
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    EvidenceCard,
    EvidenceVerdict,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.services.control_sets import ControlSetResponse
from pathfinder.services.experiment.scored_comparison import (
    ScoredComparison,
    ScoredVariant,
)
from pathfinder.services.experiment.variant_comparison import VariantSpec
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import detached_lead_context

_POSITIVES = [f"PF3D7_{index:07d}" for index in range(1133400, 1133410)]
_NEGATIVES = [f"PF3D7_{index:07d}" for index in range(1400001, 1400013)]


def _asking(prompt: str) -> LeadDeps:
    deps = lead_deps(pipeline_state(user_prompt=prompt))
    deps.state.turn_markers.intent_classified = True
    return deps


def _stands(deps: LeadDeps, prose: str) -> bool:
    report = LeadResponse(prose=prose, strategy_changed=False)
    return hold_the_turn_contract(run_context_for(deps), report) is report


def test_plain_biology_is_no_control_result() -> None:
    deps = _asking("What regulates egress?")

    assert _stands(deps, "Of the 48 genes, 5 of 7 positive regulators are present.")


def _strategy(text: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value=text)},
        ),
    )


def _checked(prompt: str, *, judged: StrategyAst, now: StrategyAst) -> LeadDeps:
    """A thread whose last check judged one tree and whose strategy holds another."""
    deps = _asking(prompt)
    deps.state.domain.answered_graph = now
    deps.state.domain.last_evidence_card = EvidenceCard(
        check_id="call_verify",
        revision=strategy_revision(judged),
        site_id="plasmodb",
        checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        site_read="read",
        steps=[],
        controls=[
            ControlTestEvidence(
                tested_label="Kinases",
                wdk_step_id=440299573,
                positive=ControlSetEvidence(
                    returned=_POSITIVES[:7], not_returned=_POSITIVES[7:]
                ),
            )
        ],
        citations=[],
        verdict=EvidenceVerdict(supported=True),
    )
    return deps


def test_the_last_checks_card_backs_a_restatement() -> None:
    kinases = _strategy("kinase")
    deps = _checked("Did anything change since the check?", judged=kinases, now=kinases)

    assert _stands(
        deps, "Your last check recovered 7 of 10 positive controls; nothing changed."
    )
    assert deps.state.turn_markers.contract_refused is False


def test_a_card_the_strategy_has_left_backs_no_claim() -> None:
    deps = _checked(
        "How does the new strategy do?",
        judged=_strategy("kinase"),
        now=_strategy("protease"),
    )

    with pytest.raises(ModelRetry) as raised:
        _stands(deps, "The strategy recovered 7 of 10 positive controls.")

    assert "no control result of this turn or of its last check" in str(raised.value)


def test_verify_reads_the_card_only_of_the_strategy_it_checks() -> None:
    kinases = _strategy("kinase")
    same = _checked("Check it again.", judged=kinases, now=kinases)
    moved = _checked("Check it again.", judged=kinases, now=_strategy("protease"))

    assert verification_scope(same, check_id="call_v2").last_card == (
        same.state.domain.last_evidence_card
    )
    assert verification_scope(moved, check_id="call_v2").last_card is None


async def test_a_scored_comparison_backs_the_counts_it_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_set = ControlSetResponse(
        id=str(uuid4()),
        name="egress controls",
        site_id="plasmodb",
        record_type="transcript",
        positive_ids=_POSITIVES,
        negative_ids=_NEGATIVES,
        tags=[],
        version=1,
        is_public=False,
        created_at="2026-09-24T00:00:00Z",
    )

    async def _get(
        _session: AsyncSession, _control_set_id: UUID, _user_id: UUID
    ) -> ControlSetResponse:
        return control_set

    async def _run(
        site_id: str, user_id: str | None, variants: object, **kwargs: object
    ) -> ScoredComparison:
        del site_id, user_id, variants, kwargs
        return ScoredComparison(
            variants=[
                ScoredVariant(
                    label="B",
                    search_name="GenesByText",
                    mcc=0.8,
                    control_hits=[*_POSITIVES[:9], _NEGATIVES[0]],
                )
            ],
            winner_label="B",
            objective="mcc",
        )

    monkeypatch.setattr(scored_comparison, "get_control_set", _get)
    monkeypatch.setattr(scored_comparison, "run_scored_comparison", _run)
    ctx = detached_lead_context()
    ctx.deps.state.turn_markers.intent_classified = True

    await compare_variants_scored(
        ctx,
        [
            VariantSpec(label="A", search_name="GenesByTaxon", parameters={}),
            VariantSpec(label="B", search_name="GenesByText", parameters={}),
        ],
        control_set_id=control_set.id,
    )

    assert [run.origin for run in ctx.deps.state.turn_markers.control_tests] == [
        "scored_comparison"
    ]
    assert _stands(
        ctx.deps,
        "Variant B wins on MCC: it recovered 9 of 10 positive controls and "
        "returned 1 of 12 negatives.",
    )
