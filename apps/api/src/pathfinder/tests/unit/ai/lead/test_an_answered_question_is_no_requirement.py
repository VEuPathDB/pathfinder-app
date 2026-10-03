"""A question the researcher answered is a question, never a requirement: it
yields no retired row and no gap. A card answer on a dimension replaces the
requirement an earlier answer stated there, and the retired row names both in
the researcher's words."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)
from veupathdb.domain.parameters import SinglePickValue
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_consult
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import card_questions, consult_user
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    provisional_constraints,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    SlotQuestion,
    with_withdrawals,
)
from pathfinder.domain.turn_facts import RetiredFact
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_COMPARISONS = "samples_fc_direct_generic_page"
_AMA_TERM = "amastigoteVsPromastigote (microarray)"
_PNA_TERM = "pnaVsPromastigote (microarray)"


def _study() -> Criterion:
    return Criterion(
        id="step_bb9551dc",
        text="up-regulated in amastigotes compared with promastigotes",
        search_name="GenesByMicroarrayDirectWithConfidencelmajFriedlin",
        resolved_params={
            _COMPARISONS: BoundValue(
                value=SinglePickValue(value=_PNA_TERM), source="default"
            )
        },
        param_display_names={_COMPARISONS: "Comparisons"},
        measurements=[
            Measurement(
                kind="vocabulary_label",
                param=_COMPARISONS,
                label="PNA - Metacyclic Promastigote vs. Early Log Procyclic "
                "Promastigote (microarray)",
                reading=_PNA_TERM,
            )
        ],
    )


def _comparison_question() -> OpenQuestion:
    return SlotQuestion(
        question="Which comparison should the expression step use?",
        dimension=ConstraintKind.COMPARATOR,
        criterion_id="step_bb9551dc",
        param_name=_COMPARISONS,
        options=[_PNA_TERM, _AMA_TERM],
    ).typed(_study(), noun="gene")


def _deps(*questions: OpenQuestion) -> LeadDeps:
    return lead_deps(
        pipeline_state(
            "tritrypdb",
            user_prompt="an answer to the card",
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(criteria=[_study()]),
                open_questions=list(questions),
            ),
        )
    )


async def _answer(
    deps: LeadDeps, card: CardQuestion, label: str, call_id: str = "call_card"
) -> None:
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id=call_id, tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        call_id: [
            UserQuestionAnswer(
                question_id=card.id, prompt=card.prompt, chosen_labels=[label]
            )
        ]
    }
    await consult_user(
        run_context_for(deps, call_id), questions=[card], reply="One question."
    )


async def test_a_typed_card_answer_leaves_no_retired_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tritrypdb card answered with a value: the step holds it, and the
    facts show no retired row naming the card prompt."""

    async def _unread(**_kwargs: object) -> dict[str, list[ParameterInfo]]:
        return {}

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _unread)
    question = _comparison_question()
    deps = _deps(question)
    [card] = card_questions([question])
    ama = next(o.label for o in card.options if "amastigote" in o.label)

    await _answer(deps, card, ama)

    domain = deps.state.domain
    assert domain.retired_requirements == []
    assert [q.question for q in domain.answered_questions] == [question.question]
    assert turn_facts(deps).retired == []
    spec = domain.operational_spec
    assert spec is not None
    assert spec.criteria[0].resolved_params[_COMPARISONS].value == SinglePickValue(
        value=_AMA_TERM
    )


def test_a_row_that_restates_an_answered_question_is_no_gap() -> None:
    """The vectorbase shape: a question the thread asked is never unanswered."""
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text="Is there a better one on VectorBase for this question?",
                turn=3,
                how="search",
                status="unexpressed",
            ),
            RequirementCheck(
                text="signal peptide", turn=1, how="search", status="unmet"
            ),
        ]
    )

    gaps = check_gaps(
        structure=None,
        words=[],
        review=review,
        requirements=provisional_constraints(
            [requirement(ConstraintKind.OTHER, "localisation", "signal peptide")]
        ),
        asked=["Is there a better one on VectorBase for this question?"],
    )

    assert gaps == [RequirementGap(text="signal peptide", status="unmet")]


def _leads_card(prompt: str, *labels: str) -> CardQuestion:
    return CardQuestion(
        id="expression_study",
        prompt=prompt,
        dimension=ConstraintKind.DATA_TYPE,
        options=[ConsultOption(label=label) for label in labels],
    )


_LOOK = "Look for a different Leishmania major expression study"
_USE = "Use the available Leishmania major study"


async def test_a_later_answer_on_the_same_dimension_replaces_the_earlier() -> None:
    """Each answer is the researcher's own words on a question in words."""
    deps = _deps()
    await _answer(
        deps,
        _leads_card("Keep the study or look for another?"),
        _LOOK,
    )
    await _answer(
        deps,
        _leads_card("Use this study or another species?"),
        _USE,
        call_id="call_card_2",
    )

    domain = deps.state.domain
    assert [(c.kind, c.requested_value) for c in domain.requirements] == [
        (ConstraintKind.DATA_TYPE, _USE)
    ]
    assert turn_facts(deps).retired == [
        RetiredFact(requirement=_LOOK, state="replaced", replaced_by=_USE)
    ]
    review = VerificationReview(
        requirements=[
            RequirementCheck(text=_LOOK, turn=2, how="search", status="unmet")
        ]
    )
    assert (
        check_gaps(
            structure=None,
            words=[],
            review=review,
            requirements=[r.grounded() for r in domain.retired_requirements],
        )
        == []
    )


def test_answering_questions_retires_no_requirement() -> None:
    domain = StrategyDomainState(
        open_questions=[_comparison_question()],
        requirements=[requirement(ConstraintKind.OTHER, "localisation", "secreted")],
    )

    domain.answer_open_questions("Comparisons amastigote", on_card=True)

    assert domain.retired_requirements == []
    assert [c.requested_value for c in domain.requirements] == ["secreted"]
    assert [q.question for q in domain.answered_questions] == [
        "Which comparison should the expression step use?"
    ]


_SIGNALP_QUESTION = (
    "The BspA-like search is nonempty, but the SignalP-6.0 filter returns no "
    "proteins. Which available prediction version should I use for the "
    "signal-peptide filter?"
)


def test_an_answered_question_hides_no_requirement_its_words_carry() -> None:
    """A question carries the words of the requirements it is about, and each
    of those requirements stays a gap while nothing answers it."""
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text="BspA-like proteins", turn=1, how="search", status="unmet"
            ),
            RequirementCheck(
                text="signal peptide", turn=1, how="search", status="unmet"
            ),
        ]
    )

    gaps = check_gaps(
        structure=None,
        words=[],
        review=review,
        requirements=provisional_constraints(
            [
                requirement(ConstraintKind.OTHER, "gene class", "BspA-like proteins"),
                requirement(ConstraintKind.OTHER, "localisation", "signal peptide"),
            ]
        ),
        asked=[_SIGNALP_QUESTION],
    )

    assert gaps == [
        RequirementGap(text="BspA-like proteins", status="unmet"),
        RequirementGap(text="signal peptide", status="unmet"),
    ]


async def test_a_kept_requirement_stays_open_and_stays_a_gap() -> None:
    """Keep on the drop-or-keep card retires nothing, states nothing new, and
    the requirement no search states is still a gap."""
    fold = requirement(ConstraintKind.FOLD_CHANGE, "fold-change cutoff", "1.5-fold")
    [question] = with_withdrawals([], [fold])
    deps = _deps(question)
    deps.state.domain.requirements = [fold]
    [card] = card_questions([question])

    await _answer(deps, card, "Keep 1.5-fold")

    domain = deps.state.domain
    assert domain.requirements == [fold]
    assert domain.retired_requirements == []
    assert turn_facts(deps).retired == []
    review = VerificationReview(
        requirements=[
            RequirementCheck(text="1.5-fold", turn=1, how="search", status="unmet")
        ]
    )
    assert check_gaps(
        structure=None,
        words=[],
        review=review,
        requirements=[
            GroundedConstraint(constraint=fold, status=ConstraintStatus.UNGROUNDABLE)
        ],
        asked=[q.question for q in domain.answered_questions],
    ) == [RequirementGap(text="1.5-fold", status="unmet")]
