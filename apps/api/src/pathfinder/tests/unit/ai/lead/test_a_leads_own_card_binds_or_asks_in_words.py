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
from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import (
    consult_user,
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


def _card(prompt: str, dimension: ConstraintKind, *labels: str) -> CardQuestion:
    return CardQuestion(
        id="q1",
        prompt=prompt,
        dimension=dimension,
        options=[ConsultOption(label=label) for label in labels],
    )


_SPEC = OperationalSpec(criteria=[_signal_peptide(), _oocyst_proxy()])


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
