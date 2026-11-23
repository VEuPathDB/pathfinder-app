from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.domain.parameters import MultiPickValue, ParamValue

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.lead_consult import apply_option_bindings
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.organism_picks import (
    OrganismPick,
    organism_questions,
)
from strategist.tests.unit.ai.lead.conftest import pipeline_state

_SPECIES = "Plasmodium falciparum"
_STRAIN = "Plasmodium falciparum 3D7"
_OTHER = "Plasmodium vivax P01"


def _criterion(criterion_id: str, search_name: str, *organisms: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=criterion_id,
        search_name=search_name,
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=list(organisms)), source="stated"
            )
        },
    )


def _organisms_after_the_pick() -> dict[str, ParamValue]:
    requirement = Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value=_SPECIES,
        label="organism",
        source=ConstraintSource.USER_EXPLICIT,
        quote=_SPECIES,
    )
    [question] = organism_questions(
        [requirement],
        [OrganismPick(quote=_SPECIES, offered=[_STRAIN, "Plasmodium falciparum IT"])],
    )
    state = pipeline_state(
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            open_questions=[question],
            operational_spec=OperationalSpec(
                goal="vaccine candidates",
                criteria=[
                    _criterion("c_signal", "GenesWithSignalPeptide", _SPECIES),
                    _criterion("c_tm", "GenesByTransmembraneDomains", _SPECIES),
                    _criterion("c_vivax", "GenesByTaxon", _OTHER),
                    _criterion("c_both", "GenesByTaxon", _SPECIES, _OTHER),
                ],
            ),
        ),
    )
    state.domain.requirements = [requirement]

    apply_option_bindings(
        state,
        [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=[_STRAIN]
            )
        ],
        sheets={},
    )

    spec = state.domain.operational_spec
    assert spec is not None
    return {c.id: c.param_values["organism"] for c in spec.criteria}


def test_a_consulted_strain_reaches_every_criterion_naming_its_species() -> None:
    assert _organisms_after_the_pick() == {
        "c_signal": MultiPickValue(values=[_STRAIN]),
        "c_tm": MultiPickValue(values=[_STRAIN]),
        "c_vivax": MultiPickValue(values=[_OTHER]),
        "c_both": MultiPickValue(values=[_STRAIN, _OTHER]),
    }
