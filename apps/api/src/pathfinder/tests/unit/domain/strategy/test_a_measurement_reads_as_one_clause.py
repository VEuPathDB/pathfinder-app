"""Each measurement a criterion holds reads as one clause, by the parameter's
display name, with the count at the bound value beside the other reading's."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue

from pathfinder.domain.strategy.measurement_clauses import (
    counted_clauses,
    measurement_clauses,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    ValueSource,
)


def _criterion(
    name: str,
    value: str,
    source: ValueSource,
    measurement: Measurement,
    result_count: int | None,
    display: str,
) -> Criterion:
    return Criterion(
        id="c1",
        text="text",
        resolved_params={
            name: BoundValue(value=StringValue(value=value), source=source)
        },
        param_display_names={name: display},
        measurements=[measurement],
        result_count=result_count,
    )


def _percentile(source: ValueSource, result_count: int | None = 1087) -> Criterion:
    return _criterion(
        "min_expression_percentile",
        "80",
        source,
        Measurement(
            kind="loosest_bound",
            param="min_expression_percentile",
            count=5318,
            reading="0",
        ),
        result_count,
        "Minimum expression percentile",
    )


def test_a_default_reads_with_the_count_at_its_loosest_bound() -> None:
    assert measurement_clauses(_percentile("default"), noun="gene") == [
        (
            "Minimum expression percentile at the site's default of 80: "
            "1,087 genes; at 0: 5,318"
        )
    ]


def test_a_chosen_value_reads_as_chosen() -> None:
    assert measurement_clauses(_percentile("chosen"), noun="gene") == [
        "Minimum expression percentile at the chosen 80: 1,087 genes; at 0: 5,318"
    ]


def test_a_criterion_with_no_count_reads_the_other_reading_alone() -> None:
    assert measurement_clauses(_percentile("default", None), noun="gene") == [
        "Minimum expression percentile at 0: 5,318 genes"
    ]


def test_a_phrase_reads_its_wildcard_and_its_site_search_counts() -> None:
    wildcard = _criterion(
        "text_expression",
        '"VSP"',
        "chosen",
        Measurement(
            kind="wildcard_phrase", param="text_expression", count=207, reading="VSP*"
        ),
        196,
        "Text term (use * as wildcard)",
    )
    reach = wildcard.model_copy(
        update={
            "measurements": [
                Measurement(
                    kind="site_search_reach",
                    param="text_expression",
                    count=333,
                    reading='"VSP"',
                )
            ]
        }
    )

    assert [measurement_clauses(c, noun="gene") for c in (wildcard, reach)] == [
        ['Text term (use * as wildcard) as "VSP": 196 genes; as VSP*: 207'],
        ['the site search finds 333 genes for "VSP"'],
    ]


def test_a_species_group_reads_both_ways() -> None:
    group = _criterion(
        "included_species",
        "tgar, tgca",
        "chosen",
        Measurement(
            kind="any_strain",
            param="included_species",
            count=497,
            reading="at least one of 15 species",
        ),
        484,
        "Included Species",
    )
    group.measurements.append(
        Measurement(
            kind="all_strains",
            param="included_species",
            count=484,
            reading="all 15 species",
        )
    )

    assert measurement_clauses(group, noun="gene") == [
        "Included Species with an ortholog in at least one of 15 species: 497 genes",
        "Included Species with an ortholog in all 15 species: 484 genes",
    ]


def test_a_vocabulary_pick_reads_with_its_label() -> None:
    criterion = Criterion(
        id="c1",
        text="protein coding genes",
        resolved_params={
            "protein_coding_only": BoundValue(
                value=SinglePickValue(value="yes"), source="default"
            )
        },
        param_display_names={"protein_coding_only": "Protein Coding Only:"},
        measurements=[
            Measurement(
                kind="vocabulary_label",
                param="protein_coding_only",
                label="protein coding",
                reading="yes",
            )
        ],
    )

    assert measurement_clauses(criterion, noun="gene") == [
        "Protein Coding Only: yes is labelled 'protein coding'"
    ]


def test_a_reading_that_did_not_arrive_reads_as_not_measured() -> None:
    unread = _percentile("default").model_copy(
        update={
            "measurements": [
                Measurement(
                    kind="loosest_bound",
                    param="min_expression_percentile",
                    reading="0",
                )
            ]
        }
    )
    uncounted = unread.model_copy(update={"result_count": None})

    assert [measurement_clauses(c, noun="gene") for c in (unread, uncounted)] == [
        [
            (
                "Minimum expression percentile at the site's default of 80: 1,087 "
                "genes; at 0: not measured"
            )
        ],
        ["Minimum expression percentile at 0: not measured"],
    ]


def test_a_species_group_whose_count_did_not_arrive_reads_as_not_measured() -> None:
    group = _criterion(
        "included_species",
        "tgar, tgca",
        "chosen",
        Measurement(
            kind="any_strain",
            param="included_species",
            reading="at least one of 15 species",
        ),
        484,
        "Included Species",
    )

    assert measurement_clauses(group, noun="gene") == [
        "Included Species with an ortholog in at least one of 15 species: not measured"
    ]


def test_a_count_is_named_in_the_noun_of_the_record_type() -> None:
    compound = _percentile("chosen", 1)

    assert measurement_clauses(compound, noun="compound") == [
        "Minimum expression percentile at the chosen 80: 1 compound; at 0: 5,318"
    ]
    assert counted_clauses(
        compound.model_copy(update={"result_count": None}),
        "min_expression_percentile",
        noun="compound",
    ) == ["Minimum expression percentile at 0: 5,318 compounds"]


def test_each_word_measurement_reads_as_one_clause() -> None:
    fields = "text_fields"
    measured = [
        Measurement(kind="site_default", param=fields, count=10, reading="all 26"),
        Measurement(
            kind="options_not_taken",
            param=fields,
            unchosen=["Gene ID", "GO terms"],
            unchosen_count=2,
        ),
        Measurement(kind="options_not_taken", param=fields, unchosen_count=212),
        Measurement(kind="bound_count", param=fields, reading="product"),
        Measurement(kind="not_measurable", param=fields, reading="it has no bound"),
    ]
    criterion = _criterion(
        fields, "product", "chosen", measured[0], 2, "Fields"
    ).model_copy(update={"measurements": measured})

    assert measurement_clauses(criterion, noun="gene") == [
        "Fields as product: 2 genes; at the site's default, all 26: 10",
        "Fields did not take Gene ID, GO terms",
        "Fields did not take 212 options",
        "Fields at the chosen product: not measured",
        "Fields: not measurable, it has no bound",
    ]


# The N. fowleri peptidase bind: 50 of 66 Pfam ids, 148 genes; all 66: 162.
_PEPTIDASES = [f"PF{n:05d}" for n in range(1, 51)]


def test_a_long_pick_is_named_by_its_size_in_a_clause() -> None:
    criterion = Criterion(
        id="c_peptidase",
        text="peptidase domain",
        resolved_params={
            "pfam_domains": BoundValue(
                value=MultiPickValue(values=_PEPTIDASES), source="chosen"
            )
        },
        param_display_names={"pfam_domains": "Specific Domain(s)"},
        measurements=[
            Measurement(
                kind="site_default",
                param="pfam_domains",
                count=162,
                reading="all 66 options",
            )
        ],
        result_count=148,
    )

    assert measurement_clauses(criterion, noun="gene") == [
        (
            "Specific Domain(s) as 50 values: 148 genes; at the site's default, "
            "all 66 options: 162"
        )
    ]


def test_a_count_of_options_not_taken_is_written_with_its_separator() -> None:
    criterion = Criterion(
        id="c_pfam",
        text="peptidase domain",
        resolved_params={
            "pfam_domains": BoundValue(
                value=MultiPickValue(values=["PF00001"]), source="chosen"
            )
        },
        param_display_names={"pfam_domains": "Specific Domain(s)"},
        measurements=[
            Measurement(
                kind="options_not_taken", param="pfam_domains", unchosen_count=2440
            )
        ],
        result_count=37,
    )

    assert measurement_clauses(criterion, noun="gene") == [
        "Specific Domain(s) did not take 2,440 options"
    ]


def test_a_pick_from_a_long_cut_list_is_counted_with_its_separator() -> None:
    criterion = Criterion(
        id="c_pfam",
        text="kinase domain",
        resolved_params={
            "pfam_domains": BoundValue(
                value=MultiPickValue(values=_PEPTIDASES), source="stated"
            )
        },
        param_display_names={"pfam_domains": "Specific Domain(s)"},
        measurements=[
            Measurement(
                kind="picked_from_a_cut_list",
                param="pfam_domains",
                count=50,
                unchosen_count=2391,
                reading="'kinase'",
            )
        ],
    )

    assert measurement_clauses(criterion, noun="gene") == [
        (
            "Specific Domain(s) took 50 of the 2,441 entries that match 'kinase'; "
            "the list it was picked from showed only part of them"
        )
    ]


def test_a_value_its_count_measures_is_never_shown_as_not_measurable() -> None:
    """giardiadb: the organism tree pick, counted at all 18 of its options."""
    measured = [
        Measurement(
            kind="loosest_bound",
            param="organism",
            count=47060,
            reading="all 18 options",
        ),
        Measurement(
            kind="not_measurable",
            param="organism",
            reading=(
                "options not taken: not applicable, since a parent term takes the "
                "options under it"
            ),
        ),
    ]
    criterion = _criterion(
        "organism",
        "Giardia Assemblage A isolate WB",
        "chosen",
        measured[0],
        4497,
        "Organism",
    ).model_copy(update={"measurements": measured})

    assert counted_clauses(criterion, "organism", noun="gene") == [
        (
            "Organism at the chosen Giardia Assemblage A isolate WB: 4,497 genes; "
            "at all 18 options: 47,060"
        )
    ]
