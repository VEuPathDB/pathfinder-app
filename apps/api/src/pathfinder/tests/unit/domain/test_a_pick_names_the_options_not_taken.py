"""A pick the request did not state names the options it did not take, and a
pick that narrows beside its site default shows both counts. A value whose
own count did not arrive says its effect was not measured."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, NumberValue, SinglePickValue

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
)
from pathfinder.domain.value_caveats import (
    ChoiceCaveat,
    UnmeasuredValueCaveat,
    assumed_value_caveats,
)

# The text search's Fields vocabulary, as plasmodb publishes it.
_FIELD_LABELS = {
    "apolloCommentContent": "Apollo Annotations",
    "ECNumbers": "EC descriptions and numbers",
    "Epitopes": "Epitopes from IEDB",
    "GeneLinkouts": "External links",
    "primary_key": "Gene ID",
    "name": "Gene name or symbol",
    "gene_type": "Gene type",
    "GeneModelCharacteristics": "GeneModel Characteristics",
    "sequence_id": "Genomic sequence ID",
    "GOTerms": "GO terms",
    "InterPro": "InterPro domains",
    "MetabolicPathways": "Metabolic pathways",
    "Alias": "Names, IDs, and aliases",
    "Notes": "Notes from annotators",
    "organism_full": "Organism",
    "orthomcl_name": "Ortholog group",
    "Orthologs": "Orthologs",
    "PdbSimilarities": "PDB chains",
    "PhenotypeCategoricalValues": "Phenotype values",
    "product": "Product description",
    "Products": "Product descriptions (all)",
    "PubMed": "PubMed",
    "so_id": "Sequence Ontology ID",
    "so_term_name": "Sequence Ontology term",
    "GeneTranscripts": "Transcripts",
    "UserCommentContent": "User comments",
}
_CHOSEN_FIELDS = ["product", "Products", "Notes"]
_NOT_TAKEN = [
    label for term, label in _FIELD_LABELS.items() if term not in _CHOSEN_FIELDS
]


def _spec(criterion: Criterion) -> OperationalSpec:
    return OperationalSpec(criteria=[criterion])


def _spore_wall() -> Criterion:
    """The microsporidiadb spore wall bind: three of 26 fields, 2 genes; all 26: 10."""
    return Criterion(
        id="c_spore_wall",
        text="spore wall proteins",
        search_name="GenesByText",
        resolved_params={
            "text_fields": BoundValue(
                value=MultiPickValue(values=_CHOSEN_FIELDS), source="chosen"
            )
        },
        param_display_names={"text_fields": "Fields"},
        measurements=[
            Measurement(
                kind="site_default",
                param="text_fields",
                count=10,
                reading="all 26 options",
            ),
            Measurement(
                kind="options_not_taken",
                param="text_fields",
                unchosen=_NOT_TAKEN,
                unchosen_count=23,
            ),
        ],
        result_count=2,
    )


def test_a_chosen_subset_of_fields_shows_both_counts_and_the_fields_not_taken() -> None:
    sentences = [c.sentence for c in assumed_value_caveats(_spec(_spore_wall()))]

    assert sentences == [
        (
            "Fields is product, Products, Notes, chosen: 2 genes at that value, 10 "
            "at the site's default, all 26 options"
        ),
        (
            "Fields is product, Products, Notes, chosen; the options not taken: "
            + ", ".join(_NOT_TAKEN)
        ),
    ]


def _life_stages() -> Criterion:
    """The tritrypdb bind whose hidden Experiment default chose the comparison."""
    return Criterion(
        id="c_up",
        text="up in amastigotes compared with promastigotes",
        search_name="GenesByMicroarrayDirectWithConfidence",
        resolved_params={
            "profileset_generic": BoundValue(
                value=SinglePickValue(value="pnaVsPromastigote"), source="default"
            )
        },
        param_display_names={"profileset_generic": "Experiment"},
        measurements=[
            Measurement(
                kind="options_not_taken",
                param="profileset_generic",
                unchosen=["amastigoteVsPromastigote"],
                unchosen_count=1,
            )
        ],
        result_count=142,
    )


def test_a_default_pick_names_the_option_it_did_not_take() -> None:
    (caveat,) = assumed_value_caveats(_spec(_life_stages()))

    assert caveat == ChoiceCaveat(
        criterion_id="c_up",
        param_display_name="Experiment",
        value="pnaVsPromastigote",
        source="default",
        unchosen=["amastigoteVsPromastigote"],
        unchosen_count=1,
    )
    assert caveat.sentence == (
        "Experiment is pnaVsPromastigote, the site's default; the options not "
        "taken: amastigoteVsPromastigote"
    )


def test_a_vocabulary_too_large_to_list_is_named_by_its_size() -> None:
    caveat = ChoiceCaveat(
        criterion_id="c_org",
        param_display_name="Organism",
        value="Leishmania major strain Friedlin",
        source="chosen",
        unchosen_count=212,
    )

    assert caveat.sentence == (
        "Organism is Leishmania major strain Friedlin, chosen; 212 options not taken"
    )


def test_a_value_whose_own_count_did_not_arrive_was_not_measured() -> None:
    criterion = Criterion(
        id="c_ring_expression",
        text="expressed in rings",
        search_name="GenesByRNASeqPercentile",
        resolved_params={
            "min_expression_percentile": BoundValue(
                value=NumberValue(value=80), source="default"
            )
        },
        param_display_names={
            "min_expression_percentile": "Minimum expression percentile"
        },
        measurements=[
            Measurement(
                kind="bound_count", param="min_expression_percentile", reading="80"
            )
        ],
    )

    (caveat,) = assumed_value_caveats(_spec(criterion))

    assert isinstance(caveat, UnmeasuredValueCaveat)
    assert caveat.sentence == (
        "Minimum expression percentile is 80, the site's default: its effect was "
        "not measured, since the count of the search at 80 did not arrive"
    )


def test_a_value_whose_kind_is_not_measurable_is_no_caveat() -> None:
    criterion = Criterion(
        id="c_date",
        text="released after 2020",
        search_name="GenesByDate",
        resolved_params={
            "date": BoundValue(value=NumberValue(value=2020), source="chosen")
        },
        measurements=[
            Measurement(
                kind="not_measurable",
                param="date",
                reading="the site publishes no wider reading of a date",
            )
        ],
        result_count=5,
    )

    assert assumed_value_caveats(_spec(criterion)) == []


def test_a_long_pick_is_named_by_its_size_in_its_caveat() -> None:
    """The caveat names the row's value by its size; the row shows it whole."""
    peptidases = [f"PF{n:05d}" for n in range(1, 51)]
    criterion = Criterion(
        id="c_peptidase",
        text="peptidase domain",
        resolved_params={
            "pfam_domains": BoundValue(
                value=MultiPickValue(values=peptidases), source="chosen"
            )
        },
        param_display_names={"pfam_domains": "Specific Domain(s)"},
        measurements=[
            Measurement(
                kind="options_not_taken",
                param="pfam_domains",
                unchosen_count=16,
            )
        ],
        result_count=148,
    )

    assert [c.sentence for c in assumed_value_caveats(_spec(criterion))] == [
        "Specific Domain(s) is 50 values, chosen; 16 options not taken"
    ]


def test_a_count_of_options_not_taken_is_written_with_its_separator() -> None:
    caveat = ChoiceCaveat(
        criterion_id="c_pfam",
        param_display_name="Specific Domain(s)",
        value="50 values",
        source="chosen",
        unchosen_count=2424,
    )

    assert caveat.sentence == (
        "Specific Domain(s) is 50 values, chosen; 2,424 options not taken"
    )
