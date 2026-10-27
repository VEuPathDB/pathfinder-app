"""A question card offers the options FRAME recorded, and an answer applies the
binding of the option it picks with no model in between: values into the spec
as the card's, a withdrawal, or a requirement in the researcher's words."""

from __future__ import annotations

from collections.abc import Collection
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import CombineOp, flatten_tree
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_consult
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import (
    consult_user,
)
from pathfinder.ai.lead.recorded_cards import card_questions, the_card_asked
from pathfinder.ai.lead.sub_agent_dispatch import minted_spec
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._frame_sources import bound_values
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.question_options import Keep, TypedOption, Withdraw
from pathfinder.domain.strategy.questions import OpenQuestion, SlotQuestion
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_FLOOR = "min_expression_percentile"
_TROPHOZOITE = (
    "GenesByRNASeqehisHM1IMSS_Trophozoite_transcriptome_ebi_rnaSeq_RSRCPercentile"
)
_DETECTED = "Minimum expression percentile 1: 17 genes"
_DEFAULT = "Minimum expression percentile 80"
_REPLY = "One value decides the trophozoite step, so I ask it before I build."


@pytest.fixture(autouse=True)
def _published_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    """A recorded RNA-Seq percentile sheet stands in for the trophozoite search:
    the two recorded percentile searches publish the floor alike."""
    sheet = format_param_info_typed(
        suite_search("search_genes_by_rnaseq_gomez_diaz_percentile").parameters or []
    )

    async def _sheets(
        *, site_id: str, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id
        return {name: sheet for name in search_names if name == _TROPHOZOITE}

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)


def _trophozoite() -> Criterion:
    """The amoebadb trophozoite step with its floor open, as FRAME left it."""
    return Criterion(
        id="c_troph",
        text="expressed in trophozoites",
        search_name=_TROPHOZOITE,
        resolved_params={
            "profileset_generic": BoundValue(
                value=StringValue(
                    value="Trophozoite transcriptome of E. histolyticaunstranded"
                ),
                source="default",
            ),
            "any_or_all": BoundValue(value=StringValue(value="all"), source="chosen"),
        },
        param_display_names={_FLOOR: "Minimum expression percentile"},
        open_params=[OpenSlot(criterion_id="c_troph", param_name=_FLOOR)],
        measurements=[
            Measurement(kind="loosest_bound", param=_FLOOR, count=17, reading="1")
        ],
    )


def _proteases() -> Criterion:
    return Criterion(
        id="c_go",
        text="cysteine-type peptidase activity",
        search_name="GenesByGoTerm",
        resolved_params={
            "go_typeahead": BoundValue(
                value=StringValue(value="GO:0008234"), source="chosen"
            )
        },
        result_count=74,
    )


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="E. histolytica cysteine proteases expressed in trophozoites",
        criteria=[_proteases(), _trophozoite()],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_go"),
                    StructureNode(kind="leaf", criterion_id="c_troph"),
                ],
            )
        ),
    )


def _floor_question() -> OpenQuestion:
    return SlotQuestion(
        question="How strictly must the genes be expressed in trophozoites?",
        dimension=ConstraintKind.PERCENTILE,
        recommended_value="1",
        criterion_id="c_troph",
        param_name=_FLOOR,
        options=["1", "80"],
    ).typed(_trophozoite(), noun="gene")


def _deps(*questions: OpenQuestion) -> LeadDeps:
    state = pipeline_state(
        "amoebadb",
        user_prompt="Also require that they are expressed in trophozoites.",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=_spec(),
            open_questions=list(questions),
            requirements=[
                requirement(ConstraintKind.OTHER, "expression", "trophozoites")
            ],
        ),
    )
    return lead_deps(state)


def _answer(deps: LeadDeps, prompt: str, *labels: str, note: str = "") -> None:
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=prompt, chosen_labels=list(labels), note=note
            )
        ]
    }


async def _answered_floor(label: str) -> LeadDeps:
    """The amoebadb card: two floors, the researcher picks one."""
    question = _floor_question()
    deps = _deps(question)
    _answer(deps, question.question, label)
    await consult_user(
        run_context_for(deps, "call_card"),
        questions=card_questions([question]),
        reply=_REPLY,
    )
    return deps


class TestTheCardOffersWhatFrameRecorded:
    def test_the_card_asks_each_recorded_question_with_its_labels(self) -> None:
        assert card_questions([_floor_question()]) == [
            CardQuestion(
                id="q1",
                prompt="How strictly must the genes be expressed in trophozoites?",
                dimension=ConstraintKind.PERCENTILE,
                options=[
                    ConsultOption(label=_DETECTED, recommended=True),
                    ConsultOption(label=_DEFAULT),
                ],
            )
        ]

    def test_a_card_that_leaves_a_recorded_question_out_still_asks_it(self) -> None:
        question = _floor_question()
        written = [CardQuestion(id="q1", prompt="Anything else?")]

        assert the_card_asked(written, [question]) == [
            *card_questions([question]),
            CardQuestion(id="own-1", prompt="Anything else?"),
        ]

    def test_a_card_that_rewrites_the_options_asks_the_recorded_ones(self) -> None:
        question = _floor_question()
        written = [
            CardQuestion(
                id="q1",
                prompt=question.question,
                options=[
                    ConsultOption(label="Detected consistently"),
                    ConsultOption(label="Detected at all"),
                ],
            )
        ]

        assert the_card_asked(written, [question]) == card_questions([question])


class TestAnAnswerAppliesItsBinding:
    async def test_the_picked_floor_is_bound_as_the_cards(self) -> None:
        deps = await _answered_floor(_DETECTED)

        spec = deps.state.domain.operational_spec
        assert spec is not None
        troph = next(c for c in spec.criteria if c.id == "c_troph")
        assert troph.resolved_params[_FLOOR] == BoundValue(
            value=StringValue(value="1"),
            source="card",
            basis="1",
            display_name="Minimum expression percentile",
            number=True,
            decimals=0,
        )
        assert troph.open_params == []
        assert troph.result_count is None
        assert spec.ready_to_build

    async def test_the_answer_the_next_pass_reads_names_the_value_bound(
        self,
    ) -> None:
        deps = await _answered_floor(_DETECTED)

        answered = deps.state.turn_markers.answered
        assert answered is not None
        assert answered.answer == (
            '"How strictly must the genes be expressed in trophozoites?" -> '
            f'{_DETECTED} (sets {_FLOOR} to "1")'
        )

    async def test_a_bound_option_adds_no_requirement(self) -> None:
        deps = await _answered_floor(_DETECTED)

        assert [c.requested_value for c in deps.state.domain.requirements] == [
            "trophozoites"
        ]
        assert deps.state.domain.open_questions == []

    async def test_the_build_carries_the_value_the_card_bound(self) -> None:
        deps = await _answered_floor(_DETECTED)

        minted = minted_spec(deps.state.domain.operational_spec)

        steps = flatten_tree(minted.tree.root)
        troph = steps[minted.tree.step_id_by_criterion["c_troph"]]
        assert troph.parameters[_FLOOR].to_wire() == "1"

    async def test_the_other_floor_binds_the_default_instead(self) -> None:
        deps = await _answered_floor(_DEFAULT)

        spec = deps.state.domain.operational_spec
        assert spec is not None
        troph = next(c for c in spec.criteria if c.id == "c_troph")
        assert troph.resolved_params[_FLOOR].value.to_wire() == "80"
        assert troph.resolved_params[_FLOOR].basis == "80"

    async def test_the_frame_rebind_reads_the_value_as_the_cards(self) -> None:
        deps = await _answered_floor(_DETECTED)
        spec = deps.state.domain.operational_spec
        assert spec is not None
        troph = next(c for c in spec.criteria if c.id == "c_troph")

        rebound = bound_values(
            {_FLOOR: NumberValue(value=1)},
            infos=[],
            site_supplied=set(),
            request_texts=["Also require that they are expressed in trophozoites."],
            reason="",
            card_values=troph.set_by("card"),
        )

        assert rebound[_FLOOR] == BoundValue(
            value=NumberValue(value=1), source="card", basis="1"
        )

    async def test_a_withdraw_option_retires_the_requirement(self) -> None:
        drop = OpenQuestion(
            question="No search states trophozoite expression. Keep it?",
            options=[
                TypedOption(
                    id="drop-it",
                    label="Drop the trophozoite requirement",
                    binding=Withdraw(constraint_id="other:trophozoites"),
                ),
                TypedOption(
                    id="keep-it",
                    label="Keep the trophozoite requirement",
                    binding=Keep(constraint_id="other:trophozoites"),
                ),
            ],
        )
        deps = _deps(drop)
        _answer(deps, drop.question, "Drop the trophozoite requirement")

        await consult_user(
            run_context_for(deps, "call_card"),
            questions=card_questions([drop]),
            reply=_REPLY,
        )

        domain = deps.state.domain
        assert domain.requirements == []
        assert [
            r.lifecycle
            for r in domain.retired_requirements
            if r.constraint.key == "other:trophozoites"
        ] == [WithdrawnLifecycle(turn_id=str(deps.state.user_message_id))]


def test_a_question_asked_again_holds_the_options_of_the_newest_pass() -> None:
    """The card is held to the options the latest pass recorded."""
    older = SlotQuestion(
        question="How strictly must the genes be expressed in trophozoites?",
        criterion_id="c_troph",
        param_name=_FLOOR,
        options=["80", "90"],
    ).typed()
    domain = StrategyDomainState(open_questions=[older])

    domain.record_questions([_floor_question()])

    assert [o.label for q in domain.open_questions for o in q.options] == [
        _DETECTED,
        _DEFAULT,
    ]
