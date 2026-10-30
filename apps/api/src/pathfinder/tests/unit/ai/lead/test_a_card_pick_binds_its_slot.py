"""A pick on a card binds the slot its question asked, and states no requirement."""

from __future__ import annotations

from collections.abc import Collection
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_consult
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.questions import OpenQuestion, SlotQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_CRITERION = "c_interpro_protein_kinase_domain"
_SLOT = "domain_typeahead"
_PICKED = "Specific Domain(s) IPR000719"
_REQUEST = "Find genes with the InterPro protein kinase domain in P. falciparum 3D7"
_LEADS_PROMPT = (
    "Which specific InterPro entry should define the protein kinase domain? The "
    "recommended broad match is the protein kinase-like entry; other available "
    "matches are narrower protein kinase entries."
)


@pytest.fixture(autouse=True)
def _no_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(
        *, site_id: str, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, search_names
        return {}

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)


def _interpro() -> Criterion:
    return Criterion(
        id=_CRITERION,
        text="InterPro protein kinase domain",
        search_name="GenesByInterproDomain",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=["Plasmodium falciparum 3D7"]),
                source="stated",
            ),
            "domain_database": BoundValue(
                value=SinglePickValue(value="INTERPRO"), source="stated"
            ),
        },
        param_display_names={_SLOT: "Specific Domain(s)"},
        open_params=[OpenSlot(criterion_id=_CRITERION, param_name=_SLOT)],
    )


def _frames_question() -> OpenQuestion:
    return SlotQuestion(
        question=(
            "Which specific InterPro entry should define the protein kinase domain? "
            "The recommended broad match is `IPR011009`; other available matches "
            "include `IPR000719` and `IPR001245`."
        ),
        dimension=ConstraintKind.DATA_TYPE,
        recommended_value="IPR011009",
        criterion_id=_CRITERION,
        param_name=_SLOT,
        options=["IPR011009", "IPR000719", "IPR001245"],
        requirements=["R2"],
    ).typed(_interpro(), noun="gene")


def _leads_card() -> list[CardQuestion]:
    return [
        CardQuestion(
            id="q1",
            prompt=_LEADS_PROMPT,
            dimension=ConstraintKind.DATA_TYPE,
            requirement=_CRITERION,
            options=[
                ConsultOption(
                    label="Broad protein kinase-like entry", recommended=True
                ),
                ConsultOption(label="Narrow protein kinase entry A"),
                ConsultOption(label="Narrow protein kinase entry B"),
                ConsultOption(label="Other available InterPro entry"),
            ],
        )
    ]


async def _answered() -> LeadDeps:
    """V7's answer turn: the answers carry the prompts of the Lead's own card."""
    state = pipeline_state(
        "plasmodb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(
                goal=_REQUEST,
                criteria=[_interpro()],
                structure=SpecStructure(
                    root=StructureNode(kind="leaf", criterion_id=_CRITERION)
                ),
            ),
            open_questions=[_frames_question()],
            requirements=[
                requirement(
                    ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum 3D7"
                ),
                requirement(
                    ConstraintKind.OTHER,
                    "InterPro protein kinase domain",
                    "InterPro protein kinase domain",
                ),
            ],
        ),
    )
    deps = lead_deps(state)
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=_LEADS_PROMPT, chosen_labels=[_PICKED]
            ),
        ]
    }
    await consult_user(
        run_context_for(deps, "call_card"), questions=_leads_card(), reply=""
    )
    return deps


def _classified_answer() -> UserIntent:
    return UserIntent(
        classification=IntentClassification.CLARIFICATION_RESPONSE,
        inferred_goal=(
            "Use the selected narrower InterPro protein kinase entry to find the "
            "corresponding genes in Plasmodium falciparum 3D7."
        ),
        explicit_constraints=[
            Constraint(
                kind=ConstraintKind.DATA_TYPE,
                requested_value=_PICKED,
                label="specific InterPro entry",
                source=ConstraintSource.USER_EXPLICIT,
                hard=True,
            )
        ],
    )


async def test_the_pick_binds_the_slot_its_card_question_asked() -> None:
    deps = await _answered()

    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert spec.criteria[0].resolved_params[_SLOT].value == StringValue(
        value="IPR000719"
    )


async def test_no_pick_of_the_card_is_a_requirement() -> None:
    deps = await _answered()

    assert [c.requested_value for c in deps.state.domain.requirements] == [
        "Plasmodium falciparum 3D7",
        "InterPro protein kinase domain",
    ]


async def test_the_classified_pick_is_the_binding_and_no_requirement() -> None:
    deps = await _answered()

    deps.state.domain.record_intent(_classified_answer(), request_text=_REQUEST)

    assert [c.kind for c in deps.state.domain.requirements] == [
        ConstraintKind.ORGANISM,
        ConstraintKind.OTHER,
    ]
