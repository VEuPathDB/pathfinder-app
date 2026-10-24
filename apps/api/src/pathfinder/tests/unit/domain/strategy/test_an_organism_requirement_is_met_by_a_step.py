from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.organism_steps import (
    limits_to_an_organism,
    organisms_no_step_limits,
)
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.organism_specs import (
    ME49,
    PF3D7,
    PROTEINS,
    chain,
    groups,
    id_list,
    proteins,
    single,
    taxon,
)


def test_a_phyletic_unit_does_not_meet_an_organism_requirement() -> None:
    spec = chain(groups(), proteins())

    assert organisms_no_step_limits([ME49, PROTEINS], [], spec) == ["R1"]


def test_a_taxonomy_step_meets_an_organism_requirement() -> None:
    spec = chain(groups(), proteins(), taxon())

    assert (limits_to_an_organism(taxon()), limits_to_an_organism(groups())) == (
        True,
        False,
    )
    assert organisms_no_step_limits([ME49, PROTEINS], [], spec) == []


def test_a_bound_organism_parameter_meets_an_organism_requirement() -> None:
    signal = Criterion(
        id="c_signal",
        text="genes with a signal peptide",
        search_name="GenesWithSignalPeptide",
        record_class="transcript",
        organism_param="organism",
        resolved_params=bound(
            {"organism": MultiPickValue(values=["Toxoplasma gondii ME49"])}
        ),
    )

    assert limits_to_an_organism(signal) is True


def test_a_request_with_no_organism_requirement_is_untouched() -> None:
    assert organisms_no_step_limits([PROTEINS], [], chain(groups(), proteins())) == []


def test_an_answer_of_groups_states_its_organism_in_the_expression() -> None:
    spec = OperationalSpec(
        goal="groups with a ME49 protein",
        criteria=[groups()],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_groups")
        ),
    )

    assert organisms_no_step_limits([ME49], [], spec) == []


def test_an_id_list_meets_an_organism_requirement() -> None:
    assert limits_to_an_organism(id_list()) is True
    assert organisms_no_step_limits([PF3D7], [], single(id_list())) == []
