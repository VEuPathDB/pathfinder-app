from __future__ import annotations

import pytest
from assistant_core.capabilities.refused_calls import CallRefused

from pathfinder.ai.lead import lead_audit
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.audit.planning import PlanAsk, PlanRefusal
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.tests._support.audit_planning import (
    RNA_REFUSED,
    STRAINS,
    FakeSite,
    faked_site,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.audit.test_a_plan_names_only_held_genomes import (
    RECORDED_PLAN,
)
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)

RECORDED_REPLY = (
    "The audit finds that neither model is fully supported by RNA-seq junctions. "
    "Afu2g18040 has one supported intron, but its first annotated intron has no "
    "junction support; a strong replacement junction supports shifted splice "
    "boundaries instead. The corrected model therefore uses the replacement "
    "junction [record:Afu2g18040]. NCU00776 shows the same pattern: one intron is "
    "supported, while its second annotated intron lacks support and a strong "
    "replacement junction ends at a shifted boundary [record:NCU00776].\n\n"
    "Overall, both models receive a high-certainty shifted-splice-site error "
    "verdict. The evidence does not indicate a missing exon or an unexplained "
    "intron; it specifically supports revising the affected intron boundaries. "
    "The audit used the site's reference assemblies for each gene, so the "
    "corrections should be checked against any strain-specific annotation you "
    "intend to use."
)
_REFUSAL = (
    "The planner starts no audit: the site holds no genome named FungiDB. A "
    "genome is one of the site's organism names, written in full. For gene "
    "targets alone, send genomes: [] with the same targets. Nothing was started "
    "and no card was shown."
)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    return faked_site(monkeypatch)


def _audit_turn() -> LeadDeps:
    state = pipeline_state(user_prompt="Audit these gene models.")
    state.turn_markers.intent_classified = True
    return lead_deps(state, intent=user_intent(IntentClassification.GENE_MODEL_AUDIT))


async def _refused_plan() -> LeadDeps:
    deps = _audit_turn()
    with pytest.raises(CallRefused):
        await lead_audit.plan_gene_model_audit(
            run_context_for(deps), PlanAsk.model_validate(RECORDED_PLAN)
        )
    return deps


@pytest.mark.usefixtures("site")
async def test_the_recorded_answer_after_a_refused_plan_is_refused_once() -> None:
    deps = await _refused_plan()

    (mismatch,) = reconcile(reply(RECORDED_REPLY), turn_record(run_context_for(deps)))

    assert mismatch.kind == "unplanned_audit"
    assert mismatch.sentence == (
        "The planner refused this turn's audit plan, so no audit ran and no "
        f'card was shown. It said: "{_REFUSAL}" Call plan_gene_model_audit again '
        "with what it names, or ask the researcher."
    )


@pytest.mark.usefixtures("site")
async def test_a_question_after_a_refused_plan_stands() -> None:
    deps = await _refused_plan()
    asked = AskedQuestion(
        question="Which genome should the audit screen?",
        dimension=ConstraintKind.ORGANISM,
    )

    assert kinds(deps, reply(RECORDED_REPLY, questions=[asked])) == []


@pytest.mark.usefixtures("site")
async def test_a_plan_the_planner_then_accepts_owes_nothing() -> None:
    deps = await _refused_plan()

    await lead_audit.plan_gene_model_audit(
        run_context_for(deps), PlanAsk(genomes=(STRAINS[0],))
    )

    assert kinds(deps, reply(RECORDED_REPLY)) == []


def test_an_audit_turn_with_no_plan_owes_nothing() -> None:
    assert kinds(_audit_turn(), reply(RECORDED_REPLY)) == []


@pytest.mark.usefixtures("site")
async def test_a_refusal_no_new_plan_can_fix_takes_an_honest_reply() -> None:
    deps = _audit_turn()
    with pytest.raises(CallRefused) as refused:
        await lead_audit.plan_gene_model_audit(
            run_context_for(deps), PlanAsk(targets=(RNA_REFUSED,))
        )
    honest = reply(
        "No audit can run on EXB_0001: the site serves no RNA-seq junction "
        "track for its genome."
    )

    assert refused.value.message == (
        "The planner starts no audit: every gene target was refused. Nothing "
        "was started and no card was shown."
    )
    assert deps.state.turn_markers.refused_plan == PlanRefusal(
        sentence=refused.value.message, replannable=False
    )
    assert kinds(deps, honest) == []


@pytest.mark.usefixtures("site")
async def test_an_unheld_genome_is_a_refusal_a_new_plan_can_fix() -> None:
    deps = await _refused_plan()

    assert deps.state.turn_markers.refused_plan == PlanRefusal(
        sentence=_REFUSAL, replannable=True
    )
