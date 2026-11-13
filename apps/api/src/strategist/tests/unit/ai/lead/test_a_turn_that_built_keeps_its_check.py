"""A turn that built keeps its check, and a record the Lead reads again does not
reach the site."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import (
    ToolReturnPart,
)

from strategist.ai.lead.intent import IntentClassification
from strategist.ai.lead.intent_gate import BUILDING_TOOLS, tools_the_turn_offers
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.lead.scripted_scope import bind_scripted_scope
from strategist.ai.lead.turn_contract import LeadResponse
from strategist.ai.models.mock import get_mock_model
from strategist.ai.models.mock.site_values import SiteValues
from strategist.services.gene_records import read
from strategist.services.gene_records.read import GeneRecordSummary
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

# The fifth turn of the microsporidiadb polar tube conversation.
_POLAR_TUBE_T5 = (
    "Keep the product-field search as my strategy. Separately, just to answer "
    "my question, run the exact phrase and tell me which genes it matches "
    "beyond EBI_26400, without changing the strategy."
)

pytestmark = pytest.mark.usefixtures("recorded_site_organisms")


def test_a_turn_that_built_keeps_its_check_under_a_question_classification() -> None:
    state = pipeline_state("microsporidiadb", user_prompt=_POLAR_TUBE_T5)
    state.turn_markers.intent_classified = True
    state.turn_markers.built = True
    deps = lead_deps(
        state,
        intent=user_intent(IntentClassification.FOLLOW_UP_QUESTION),
        strategy_session=session_with_one_step("microsporidiadb"),
    )

    assert "verify_strategy" in tools_the_turn_offers(deps, BUILDING_TOOLS)


async def test_the_read_again_arc_on_the_real_lead_reads_each_record_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each record the arc reads twice reaches the site once."""
    asked: list[str] = []

    async def _read(
        site_id: str, gene_id: str, *, ortholog_organism: str | None = None
    ) -> GeneRecordSummary:
        del ortholog_organism
        asked.append(gene_id)
        return GeneRecordSummary(
            site_id=site_id,
            gene_id=gene_id,
            record_url=f"https://qa.plasmodb.org/plasmo.qa/app/record/gene/{gene_id}",
        )

    monkeypatch.setattr(read, "read_gene_record", _read)
    prompt = "List those genes again [[arc:read-again]]"
    bind_scripted_scope("plasmodb", prompt)
    state = pipeline_state("plasmodb", user_prompt=prompt)

    result = await build_lead_agent().run(
        prompt, deps=lead_deps(state), model=get_mock_model()
    )

    shown = list(SiteValues.for_site("plasmodb").controls.positive_ids[:3])
    outcomes = [
        part.outcome
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "read_gene_record"
    ]
    assert isinstance(result.output, LeadResponse)
    assert (asked, outcomes) == (shown, [*["success"] * 3, *["failed"] * 3])
