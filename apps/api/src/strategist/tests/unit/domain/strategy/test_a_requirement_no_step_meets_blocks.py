from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.limit_messages import unmet_requirement_message
from strategist.ai.lead.sub_agent_dispatch import build_the_spec
from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
    OrthologValue,
    PropertyValue,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.requirement_coverage import requirements_no_step_meets
from strategist.platform.refusals import ProblemsRefusal
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ORGANISM = Constraint(
    id="d15923587319",
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium falciparum 3D7",
    label="Plasmodium falciparum 3D7",
    source=ConstraintSource.USER_EXPLICIT,
    quote="Plasmodium falciparum 3D7",
    value=OrganismValue(organism="Plasmodium falciparum 3D7"),
)
_SIGNAL = Constraint(
    id="9012efac96f1",
    kind=ConstraintKind.PROPERTY,
    requested_value="predicted signal peptide",
    label="predicted signal peptide",
    source=ConstraintSource.USER_EXPLICIT,
    quote="predicted signal peptide",
    value=PropertyValue(phrase="predicted signal peptide"),
)
_SYNTENIC = Constraint(
    id="b637e4b8916a",
    kind=ConstraintKind.ORTHOLOG,
    requested_value="syntenic orthologs in Toxoplasma gondii ME49",
    label="syntenic orthologs in Toxoplasma gondii ME49",
    source=ConstraintSource.USER_EXPLICIT,
    quote="syntenic orthologs in Toxoplasma gondii ME49",
    value=OrthologValue(organisms=["Toxoplasma gondii ME49"], syntenic=True),
)
_HELD = [_ORGANISM, _SIGNAL, _SYNTENIC]
_UNMET = (
    "The requirement 'syntenic orthologs in Toxoplasma gondii ME49' is not met by "
    "any step: asked syntenic orthologs, isSyntenic holds 'no'."
)


def _bound(value: MultiPickValue | SinglePickValue) -> BoundValue:
    return BoundValue(value=value, source="stated")


def _recorded_x5() -> OperationalSpec:
    """The recorded uat-x5 answer turn: the transform answers no requirement and
    binds isSyntenic to no."""
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_signal_peptide",
                text="Predicted signal peptide in Plasmodium falciparum 3D7 genes",
                search_name="GenesWithSignalPeptide",
                record_class="transcript",
                organism_param="organism",
                answers=[
                    RequirementLink(requirement=_ORGANISM.id, param="organism"),
                    RequirementLink(requirement=_SIGNAL.id),
                ],
                resolved_params={
                    "organism": _bound(
                        MultiPickValue(values=["Plasmodium falciparum 3D7"])
                    )
                },
            ),
            Criterion(
                id="c_syntenic_orthologs_tgme49",
                text="Carry the intersection to all orthologs in Toxoplasma gondii ME49",
                search_name="GenesByOrthologs",
                record_class="transcript",
                role="transform",
                organism_param="organism",
                resolved_params={
                    "organism": _bound(
                        MultiPickValue(values=["Toxoplasma gondii ME49"])
                    ),
                    "isSyntenic": _bound(SinglePickValue(value="no")),
                },
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c_syntenic_orthologs_tgme49",
                inputs=[StructureNode(kind="leaf", criterion_id="c_signal_peptide")],
            )
        ),
    )


def test_a_stated_requirement_no_step_meets_is_named_plainly() -> None:
    problems = requirements_no_step_meets(_HELD, _recorded_x5())

    assert [p.sentence for p in problems.found] == [_UNMET]


def test_a_requirement_the_researcher_dropped_does_not_block() -> None:
    held = [_ORGANISM, _SIGNAL]

    assert requirements_no_step_meets(held, _recorded_x5()).found == ()


def test_it_blocks_the_answer() -> None:
    grounded = {g.constraint.id: g for g in ground_against_spec(_HELD, _recorded_x5())}

    assert (grounded[_SYNTENIC.id]).blocks
    assert not (grounded[_SIGNAL.id]).blocks


async def test_it_blocks_the_build() -> None:
    domain = StrategyDomainState(requirements=_HELD, operational_spec=_recorded_x5())
    deps = lead_deps(pipeline_state("veupathdb", domain=domain))

    with pytest.raises(ProblemsRefusal) as refused:
        await build_the_spec(deps, call_id="call_build")

    assert _UNMET in str(refused.value)


def test_the_answer_states_it_plainly() -> None:
    assert (
        "The requirement 'syntenic orthologs in Toxoplasma gondii ME49' is not met "
        "by any step."
    ) in unmet_requirement_message(("syntenic orthologs in Toxoplasma gondii ME49",))


def _adopted() -> OperationalSpec:
    """A separation offer's tree: its leaf states the signal peptide and links nothing."""
    return OperationalSpec(
        criteria=[
            Criterion(
                id="cand_sp",
                text="Signal Peptide Prediction",
                search_name="GenesWithSignalPeptide",
                record_class="transcript",
                role="seed",
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="cand_sp")
        ),
    )


def test_a_requirement_the_steps_values_cannot_judge_does_not_block() -> None:
    grounded = ground_against_spec([_SIGNAL], _adopted())

    assert (
        requirements_no_step_meets([_SIGNAL], _adopted()).found,
        grounded[0].blocks,
    ) == (
        (),
        False,
    )


def test_orthologs_no_step_carries_the_records_to_block() -> None:
    problems = requirements_no_step_meets([_SYNTENIC], _adopted())

    assert [p.sentence for p in problems.found] == [
        (
            "The requirement 'syntenic orthologs in Toxoplasma gondii ME49' is not met "
            "by any step: asked orthologs in Toxoplasma gondii ME49, and no step of the "
            "strategy carries records to orthologs."
        )
    ]
