"""A question of the Lead's own offers no option, or the drop and keep options
of a requirement the thread holds: an option label is never a requirement, and
a question in words asks no dimension a parameter of the spec holds."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import (
    consult_user,
    refuse_a_card_that_binds_nothing,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_REPLY = "A card."
_UKMEL1 = requirement(
    ConstraintKind.ORGANISM, "organism", "Cryptosporidium meleagridis UKMEL1"
)
_SPORES = requirement(ConstraintKind.OTHER, "expression", "expressed in oocysts")


def _oocyst_proxy() -> Criterion:
    """The cryptodb C. hominis expression proxy, at its 80th percentile floor."""
    return Criterion(
        id="c_oocyst_expression_proxy",
        text="expressed in oocysts",
        search_name="GenesByRNASeqchomTU502_Lippuner_Oocyst_ebi_rnaSeq_RSRC",
        resolved_params={
            "min_expression_percentile": BoundValue(
                value=StringValue(value="80"), source="chosen"
            ),
            "protein_coding_only": BoundValue(
                value=StringValue(value="yes"), source="default"
            ),
        },
        param_display_names={
            "min_expression_percentile": "Minimum expression percentile",
            "protein_coding_only": "Protein Coding Only",
        },
        result_count=783,
    )


def _signal_peptide() -> Criterion:
    return Criterion(
        id="c_signal_peptide",
        text="predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=["Cryptosporidium meleagridis UKMEL1"]),
                source="stated",
            )
        },
        result_count=421,
    )


def _deps(
    spec: OperationalSpec | None, requirements: list[Constraint] | None = None
) -> LeadDeps:
    return lead_deps(
        pipeline_state(
            "cryptodb",
            user_prompt="an answer to the card",
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                operational_spec=spec,
                requirements=requirements or [_UKMEL1, _SPORES],
            ),
        )
    )


def _refusal(deps: LeadDeps, card: CardQuestion) -> str:
    try:
        refuse_a_card_that_binds_nothing(
            run_context_for(deps, "call_card"), [card], reply=_REPLY
        )
    except ModelRetry as refused:
        return str(refused)
    return ""


def _card(prompt: str, dimension: ConstraintKind, *labels: str) -> CardQuestion:
    return CardQuestion(
        id="q1",
        prompt=prompt,
        dimension=dimension,
        options=[ConsultOption(label=label) for label in labels],
    )


_SPEC = OperationalSpec(criteria=[_signal_peptide(), _oocyst_proxy()])


def test_the_cryptodb_widen_card_is_refused() -> None:
    """Both options leave the cross-organism INTERSECT at 0 genes."""
    card = _card(
        "The intersection of UKMEL1 signal-peptide genes with the C. hominis TU502 "
        "oocyst-expression proxy returned no genes. Which available expression "
        "setting should I relax for a broader result?",
        ConstraintKind.PERCENTILE,
        "Minimum expression percentile: 0",
        "Protein Coding Only: all",
    )

    refusal = _refusal(_deps(_SPEC), card)

    assert (
        "offers ['Minimum expression percentile: 0', 'Protein Coding Only: all'], "
        "which bind nothing"
    ) in refusal
    assert "dispatch edit_strategy, or frame_problem" in refusal


def test_the_piroplasmadb_card_over_no_spec_is_refused() -> None:
    card = _card(
        "No catalog search on this site states predicted GPI-anchor genes for "
        "Cytauxzoon felis Winnie. Should I proceed with the available "
        "signal-peptide search alone, or should you specify an alternative "
        "evidence type?",
        ConstraintKind.OTHER,
        "Proceed with signal peptide alone",
        "Specify an alternative evidence type",
    )

    assert "which bind nothing" in _refusal(_deps(None), card)


def test_a_question_in_words_on_a_parameter_the_spec_binds_is_refused() -> None:
    """No requirement states a percentile; the spec binds one."""
    card = _card("Which expression floor should I use?", ConstraintKind.PERCENTILE)

    refusal = _refusal(_deps(_SPEC), card)

    assert "asks the percentile, which a parameter of the spec sets" in refusal


def test_a_question_in_words_on_a_dimension_the_spec_leaves_open_is_asked() -> None:
    card = _card("Which expression floor should I use?", ConstraintKind.PERCENTILE)
    spec = OperationalSpec(criteria=[_signal_peptide()])

    assert _refusal(_deps(spec), card) == ""


def test_a_drop_or_keep_card_of_a_held_requirement_is_asked_and_binds() -> None:
    card = _card(
        "No search states oocyst expression in UKMEL1. Drop it?",
        ConstraintKind.OTHER,
        "Drop expressed in oocysts",
        "Keep expressed in oocysts",
    )
    deps = _deps(_SPEC)

    assert _refusal(deps, card) == ""


async def test_the_drop_option_of_the_leads_card_retires_the_requirement() -> None:
    card = _card(
        "No search states oocyst expression in UKMEL1. Drop it?",
        ConstraintKind.OTHER,
        "Drop expressed in oocysts",
        "Keep expressed in oocysts",
    )
    deps = _deps(_SPEC)
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1",
                prompt=card.prompt,
                chosen_labels=["Drop expressed in oocysts"],
            )
        ]
    }

    await consult_user(run_context_for(deps, "call_card"), [card], reply=_REPLY)

    domain = deps.state.domain
    assert [c.key for c in domain.requirements] == [_UKMEL1.key]
    assert [r.constraint.key for r in domain.retired_requirements] == [_SPORES.key]


def _obp_domain() -> Criterion:
    """The vectorbase InterPro step: a Pfam domain bound to PF03392."""
    return Criterion(
        id="c_obp_domain",
        text="odorant-binding protein",
        search_name="GenesByInterproDomain",
        resolved_params={
            "domain_database": BoundValue(
                value=StringValue(value="Pfam"), source="chosen"
            ),
            "domain_typeahead": BoundValue(
                value=MultiPickValue(values=["PF03392"]), source="chosen"
            ),
        },
        param_display_names={
            "domain_database": "Domain Database",
            "domain_typeahead": "Domain",
        },
        result_count=8,
    )


_OBP = requirement(ConstraintKind.OTHER, "annotation", "odorant-binding protein")


def test_a_free_text_question_on_other_passes_over_a_bound_domain() -> None:
    card = _card(
        "Which annotation should define an odorant-binding protein: the Pfam "
        "domain or the product text?",
        ConstraintKind.OTHER,
    )
    deps = _deps(OperationalSpec(criteria=[_obp_domain()]), [_OBP])

    assert _refusal(deps, card) == ""


def test_a_refused_card_names_the_keep_and_drop_labels_it_may_offer() -> None:
    card = _card(
        "Which annotation should define an odorant-binding protein?",
        ConstraintKind.OTHER,
        "Use explicit product/name annotation",
        "Keep the current protein-domain definition",
    )
    deps = _deps(OperationalSpec(criteria=[_obp_domain()]), [_OBP])

    assert (
        "The requirements the conversation holds offer: 'Drop odorant-binding "
        "protein', 'Keep odorant-binding protein'."
    ) in _refusal(deps, card)
