from __future__ import annotations

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.domain.parameters import ParamValue, StringValue, to_wire
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.parameter_facts import step_parameters
from pathfinder.domain.strategy.genome_group import GenomeGroup
from pathfinder.domain.strategy.genome_questions import genome_reading_questions
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.value_caveats import assumed_value_caveats
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_ONE = "At least one of 2 genomes (1,259 genes)"
_ALL = "All 2 genomes (501 genes)"


def _spec(
    any_strain: int | None = 1259, group: GenomeGroup | None = None
) -> OperationalSpec:
    values: dict[str, ParamValue] = {
        "profile_pattern": StringValue(value="%hsap:N%pber:Y%pfal:Y%"),
        "included_species": StringValue(value="pber, pfal"),
        "excluded_species": StringValue(value="hsap"),
    }
    params = {
        name: held.sourced("chosen", "the group")
        for name, held in bound(values).items()
    }
    return OperationalSpec(
        goal="orthologs",
        criteria=[
            Criterion(
                id="c_profile",
                text="an ortholog in the group",
                search_name="GenesByOrthologPattern",
                record_class="transcript",
                role="seed",
                result_count=501,
                genome_group=group,
                measurements=[
                    Measurement(
                        kind="any_strain", param="included_species", count=any_strain
                    ),
                    Measurement(
                        kind="all_strains", param="included_species", count=501
                    ),
                ],
                resolved_params=params,
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_profile")
        ),
    )


def _answered(label: str) -> OperationalSpec:
    state = pipeline_state()
    spec = _spec()
    state.domain.operational_spec = spec
    state.domain.record_questions(
        [q.typed(spec.criteria[0]) for q in genome_reading_questions(spec, noun="gene")]
    )
    prompt = state.domain.open_questions[0].question
    apply_option_bindings(
        state,
        [UserQuestionAnswer(question_id="q1", prompt=prompt, chosen_labels=[label])],
        sheets={},
    )
    read = state.domain.operational_spec
    assert read is not None
    return read


def _notes(criterion: Criterion) -> list[str]:
    return next(
        fact.notes
        for fact in step_parameters(criterion, "gene", [], [])
        if fact.name == "included_species"
    )


def test_all_binds_no_value_and_settles_the_criterion() -> None:
    read = _answered(_ALL)

    [settled] = read.criteria
    assert settled.param_values == _spec().criteria[0].param_values
    assert settled.result_count == 501
    assert settled.genome_group == GenomeGroup(reading="all", genomes=("pber", "pfal"))
    assert read.structure == _spec().structure
    assert genome_reading_questions(read, noun="gene") == []


def test_at_least_one_builds_the_minus_with_no_model_in_between() -> None:
    read = _answered(_ONE)

    left, right = read.criteria
    assert to_wire(left.resolved_params["profile_pattern"].value) == "%hsap:N%"
    assert (
        to_wire(right.resolved_params["profile_pattern"].value)
        == "%hsap:N%pber:N%pfal:N%"
    )
    assert read.structure is not None
    assert read.structure.root.operator is CombineOp.MINUS
    assert genome_reading_questions(read, noun="gene") == []


def test_the_facts_state_the_reading_built_and_the_other_count() -> None:
    left, right = _answered(_ONE).criteria

    assert _notes(left) == [
        "Built as at least one of 2 genomes: 1,259 genes; all 2 genomes: 501"
    ]
    assert _notes(right) == []


def test_the_facts_state_the_strict_reading_built() -> None:
    [settled] = _answered(_ALL).criteria

    assert _notes(settled) == [
        "Built as all 2 genomes: 501 genes; at least one of 2 genomes: 1,259"
    ]


def test_the_facts_say_when_the_other_count_was_not_read() -> None:
    group = GenomeGroup(reading="all", genomes=("pber", "pfal"))
    [settled] = _spec(None, group).criteria

    assert _notes(settled) == [
        (
            "Built as all 2 genomes: 501 genes; "
            "at least one of 2 genomes: count not read within the budget"
        )
    ]


def test_a_settled_reading_is_no_assumed_value() -> None:
    assert "with an ortholog in" in str(assumed_value_caveats(_spec()))
    assert "with an ortholog in" not in str(assumed_value_caveats(_answered(_ALL)))
