"""A question of the Lead's own binds nothing unless it offers to drop or keep
a requirement, so a card whose options are labels is refused, and a question in
words is refused on every named dimension a parameter of the spec holds. A
parameter of no named dimension names no question. The cards below are the ones
the Lead asked over a built step."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import ConsultOption
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import SinglePickValue, StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import refuse_a_card_that_binds_nothing
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)


def _refusal(
    site_id: str,
    criterion: Criterion,
    requirements: list[Constraint],
    card: CardQuestion,
) -> str:
    state = pipeline_state(
        site_id,
        user_prompt="an answer to the card",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[criterion]),
            requirements=requirements,
        ),
    )
    try:
        refuse_a_card_that_binds_nothing(
            run_context_for(lead_deps(state), "call_card"), [card], reply="A card."
        )
    except ModelRetry as refused:
        return str(refused)
    return ""


def _card(
    question_id: str, prompt: str, dimension: ConstraintKind, *labels: str
) -> CardQuestion:
    return CardQuestion(
        id=question_id,
        prompt=prompt,
        dimension=dimension,
        options=[ConsultOption(label=label) for label in labels],
    )


def _signalp_step() -> Criterion:
    """The trichdb signal peptide step, at the site's default SignalP-6.0."""
    return Criterion(
        id="step_signalp",
        text="predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        resolved_params={
            "signalp_version": BoundValue(
                value=SinglePickValue(value="SignalP-6.0"), source="default"
            )
        },
        param_display_names={"signalp_version": "SignalP version"},
        result_count=0,
    )


_TRICHDB = [
    requirement(ConstraintKind.ORGANISM, "organism", "Trichomonas vaginalis G3"),
    requirement(ConstraintKind.OTHER, "gene class", "BspA-like proteins"),
    requirement(ConstraintKind.OTHER, "localisation", "predicted signal peptide"),
]
_SIGNALP_CARD = _card(
    "signalp_version",
    "The BspA-like search is nonempty, but the SignalP-6.0 filter returns no "
    "proteins. Which available prediction version should I use for the "
    "signal-peptide filter?",
    ConstraintKind.OTHER,
    "SignalP-5.0",
    "SignalP-4.1",
)


def test_the_trichdb_signalp_card_is_refused() -> None:
    refusal = _refusal("trichdb", _signalp_step(), _TRICHDB, _SIGNALP_CARD)

    assert "offers ['SignalP-5.0', 'SignalP-4.1'], which bind nothing" in refusal
    assert "dispatch edit_strategy, or frame_problem" in refusal


def _lmajor_study() -> Criterion:
    return Criterion(
        id="step_bb9551dc",
        text="up-regulated in amastigotes compared with promastigotes",
        search_name=(
            "GenesByMicroarrayDirectWithConfidencelmajFriedlin_microarrayExpression_"
            "E-MEXP-1864_Beverley_Steve_LifeStages_RSRC"
        ),
        resolved_params={
            "samples_fc_direct_generic_page": BoundValue(
                value=SinglePickValue(value="pnaVsPromastigote (microarray)"),
                source="default",
            ),
            "fold_change": BoundValue(value=StringValue(value="2"), source="default"),
        },
        result_count=142,
    )


_TRITRYPDB = [
    requirement(ConstraintKind.ORGANISM, "organism", "Leishmania major Friedlin"),
    requirement(
        ConstraintKind.COMPARATOR,
        "comparison",
        "amastigotes compared with promastigotes",
    ),
    requirement(ConstraintKind.OTHER, "localisation", "signal peptide"),
]


def test_the_tritrypdb_study_card_on_the_comparator_is_refused() -> None:
    card = _card(
        "expression_study_choice",
        "The selected experiment has no amastigote-versus-promastigote comparison. "
        "Should I keep the available two-promastigote comparison, or should I look "
        "for a different Leishmania major expression study?",
        ConstraintKind.COMPARATOR,
        "Keep the available two-promastigote comparison",
        "Look for a different Leishmania major expression study",
    )

    refusal = _refusal("tritrypdb", _lmajor_study(), _TRITRYPDB, card)

    assert "which bind nothing" in refusal
    assert "dispatch edit_strategy, or frame_problem" in refusal


def test_the_tritrypdb_species_card_on_other_is_refused() -> None:
    card = _card(
        "expression_species_or_comparison",
        "The site has no realizable Leishmania major Friedlin amastigote-versus-"
        "promastigote expression comparison. Should I use the available "
        "Leishmania major study despite its two-promastigote comparison, or "
        "change to an amastigote/promastigote study from another Leishmania "
        "species?",
        ConstraintKind.OTHER,
        "Use the available Leishmania major study",
        "Use another Leishmania species",
    )

    refusal = _refusal("tritrypdb", _lmajor_study(), _TRITRYPDB, card)

    assert "which bind nothing" in refusal
    assert "dispatch edit_strategy, or frame_problem" in refusal


def test_the_amoebadb_definition_card_is_refused() -> None:
    text_search = Criterion(
        id="step_lectin",
        text="annotated as Gal/GalNAc lectin subunits",
        search_name="GenesByText",
        resolved_params={
            "text_expression": BoundValue(
                value=StringValue(value='"Gal/GalNAc lectin subunit"'),
                source="stated",
            )
        },
        result_count=2,
    )
    card = _card(
        "lectin_specificity",
        "How should I define every subunit for the revised search?",
        ConstraintKind.OTHER,
        "Strict named subunits",
        "Strict plus putative matches",
    )

    refusal = _refusal(
        "amoebadb",
        text_search,
        [
            requirement(
                ConstraintKind.ORGANISM, "organism", "Entamoeba histolytica HM-1:IMSS"
            ),
            requirement(
                ConstraintKind.OTHER,
                "annotation",
                "annotated as Gal/GalNAc lectin subunits",
            ),
        ],
        card,
    )

    assert "which bind nothing" in refusal
    assert "dispatch edit_strategy, or frame_problem" in refusal


def test_the_same_question_in_words_on_a_parameter_of_no_named_dimension_is_asked() -> (
    None
):
    card = _card(
        "signalp_version",
        "Which available prediction version should I use for the "
        "signal-peptide filter?",
        ConstraintKind.OTHER,
    )

    assert _refusal("trichdb", _signalp_step(), _TRICHDB, card) == ""


def test_a_question_in_words_on_a_dimension_the_spec_leaves_open_is_accepted() -> None:
    card = _card(
        "coding",
        "Should the result keep only protein-coding genes?",
        ConstraintKind.DATA_TYPE,
    )

    assert _refusal("trichdb", _signalp_step(), _TRICHDB, card) == ""


def test_a_question_the_researcher_answered_is_refused() -> None:
    card = _card(
        "coding",
        "Should the result keep only protein-coding genes?",
        ConstraintKind.DATA_TYPE,
        "Protein-coding only",
        "Every gene",
    )
    state = pipeline_state(
        "trichdb",
        user_prompt="an answer to the card",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[_signalp_step()]),
            requirements=_TRICHDB,
            answered_questions=[
                AskedQuestion(
                    question=card.prompt, options=["Protein-coding only", "Every gene"]
                ).typed()
            ],
        ),
    )

    try:
        refuse_a_card_that_binds_nothing(
            run_context_for(lead_deps(state), "call_card"), [card], reply="A card."
        )
    except ModelRetry as refused:
        refusal = str(refused)
    else:
        refusal = ""

    assert (
        "'Should the result keep only protein-coding genes?' was answered already"
        in refusal
    )
