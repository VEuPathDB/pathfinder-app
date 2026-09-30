"""A criterion is organism-only when its search's organism parameter is the one
value it states and every value it selects is an organism of the site."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)

from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.organism_scope import (
    organism_only,
    organism_params_of,
)
from pathfinder.tests._support.bound_values import bound

PEST = "Anopheles gambiae PEST"
ORGANISMS = (PEST, "Anopheles stephensi Indian", "Aedes aegypti LVP_AGWG")


def _gene_model(**stated: str) -> Criterion:
    """GenesByGeneModelChars as vectorbase publishes it, the organism stated."""
    values: dict[str, ParamValue] = {
        "organism_select_none": MultiPickValue(values=[PEST]),
        "gene_or_transcript": SinglePickValue(value="Genes"),
        "gene_model_char": StringValue(value='{"filters":[]}'),
    }
    values.update({name: StringValue(value=v) for name, v in stated.items()})
    return Criterion(
        id="c_pest",
        text=f"{PEST} genes",
        search_name="GenesByGeneModelChars",
        organism_param="organism_select_none",
        resolved_params=bound(
            values,
            defaulted=sorted({"gene_or_transcript", "gene_model_char"} - {*stated}),
        ),
    )


def test_a_binding_that_states_only_the_marked_organism_is_organism_only() -> None:
    assert organism_only(_gene_model(), ORGANISMS) is True


def test_another_stated_value_makes_it_more_than_the_organism() -> None:
    criterion = _gene_model(gene_model_char="organism=Anopheles gambiae PEST")

    assert organism_only(criterion, ORGANISMS) is False


def test_a_value_left_at_its_default_is_not_stated() -> None:
    criterion = _gene_model()

    assert criterion.defaulted() == ["gene_model_char", "gene_or_transcript"]
    assert organism_only(criterion, ORGANISMS) is True


def test_an_experiment_leaf_of_a_marked_vocabulary_is_not_an_organism() -> None:
    assay = Criterion(
        id="c_ms",
        text="proteins seen by mass spectrometry",
        search_name="GenesByMassSpec",
        organism_param="ms_assay",
        resolved_params=bound(
            {"ms_assay": MultiPickValue(values=["Salivary gland proteome (Dong)"])}
        ),
    )

    assert organism_only(assay, ORGANISMS) is False


def test_a_search_with_no_marked_parameter_is_never_organism_only() -> None:
    unmarked = _gene_model().model_copy(update={"organism_param": None})

    assert organism_only(unmarked, ORGANISMS) is False


def test_the_map_names_each_bound_search_by_its_marked_parameter() -> None:
    signal = Criterion(
        id="c_signal",
        text="signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
    )
    unbound = Criterion(id="c_open", text="an open criterion")

    assert organism_params_of([_gene_model(), signal, unbound]) == {
        "GenesByGeneModelChars": "organism_select_none",
        "GenesWithSignalPeptide": "organism",
    }
