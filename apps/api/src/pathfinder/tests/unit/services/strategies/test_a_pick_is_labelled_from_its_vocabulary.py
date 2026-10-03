"""Each vocabulary pick carries the label its vocabulary gives it, from the
recorded search definition."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    FilterValue,
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
)
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.strategies.value_labels import (
    UnlabelledPick,
    vocabulary_labels,
)
from pathfinder.tests._support.recorded_searches import suite_search

_PCT = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")
_SNPS = suite_search("search_genes_by_ngs_snps")
_SAMPLES = "variation_sample_meta"
_SEX = "VAR_68bb04bd"
_YEAR = "VAR_dc0e1a57"
_SAMPLE_NAME = "VAR_41eb2167"
_PROFILESET = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Sense"
)


def _bound(params: dict[str, ParamValue]) -> dict[str, BoundValue]:
    return {
        name: BoundValue(value=value, source="stated") for name, value in params.items()
    }


def _sheet() -> list[ParameterInfo]:
    return format_param_info_typed(list(_PCT.parameters or []))


def _samples(*clauses: dict[str, object]) -> dict[str, BoundValue]:
    value = FilterValue.model_validate({"filters": list(clauses)})
    return _bound({_SAMPLES: value})


def _snps_sheet() -> list[ParameterInfo]:
    return format_param_info_typed(list(_SNPS.parameters or []))


def test_every_vocabulary_pick_is_labelled_from_the_vocabulary() -> None:
    params: dict[str, ParamValue] = {
        "profileset_generic": SinglePickValue(value=_PROFILESET),
        "samples_percentile_generic": MultiPickValue(values=["asexual blood stages"]),
        "min_expression_percentile": StringValue(value="80"),
        "max_expression_percentile": StringValue(value="100"),
        "any_or_all": SinglePickValue(value="any"),
        "protein_coding_only": SinglePickValue(value="yes"),
        "channel": SinglePickValue(value="Channel 1"),
    }

    labels = vocabulary_labels(_bound(params), _sheet())

    assert [(m.param, m.reading, m.label) for m in labels.labels] == [
        (
            "profileset_generic",
            _PROFILESET,
            (
                "Asexual blood stages, salivary gland sporozoite and midgut "
                "oocyst transcriptomes - Sense"
            ),
        ),
        (
            "samples_percentile_generic",
            "asexual blood stages",
            "asexual blood stages",
        ),
        ("any_or_all", "any", "any"),
        ("protein_coding_only", "yes", "protein coding"),
        ("channel", "Channel 1", "Channel 1"),
    ]
    assert labels.unlabelled == []


def test_a_pick_the_vocabulary_does_not_label_names_the_labels_it_holds() -> None:
    params: dict[str, ParamValue] = {
        "protein_coding_only": SinglePickValue(value="maybe")
    }

    labels = vocabulary_labels(_bound(params), _sheet())

    assert labels.unlabelled == [
        UnlabelledPick(
            param="protein_coding_only", term="maybe", labels=["protein coding", "all"]
        )
    ]


def test_each_filter_clause_is_labelled_by_the_display_of_its_field() -> None:
    bound = _samples(
        {"field": _SEX, "type": "string", "value": ["female", "male"]},
        {
            "field": _YEAR,
            "type": "number",
            "isRange": True,
            "value": {"min": 2010, "max": 2014},
        },
    )

    labels = vocabulary_labels(bound, _snps_sheet())

    assert [(m.param, m.reading, m.label) for m in labels.labels] == [
        (_SAMPLES, _SEX, "sex"),
        (_SAMPLES, _YEAR, "Collection Year"),
    ]
    assert labels.unlabelled == []


def test_a_member_past_the_listed_values_of_its_field_is_still_labelled() -> None:
    bound = _samples({"field": _SAMPLE_NAME, "value": ["PfSample-not-listed"]})

    labels = vocabulary_labels(bound, _snps_sheet())

    assert [(m.reading, m.label) for m in labels.labels] == [
        (_SAMPLE_NAME, "Sample name")
    ]
    assert labels.unlabelled == []


def test_a_clause_on_a_field_the_parameter_lacks_names_the_fields_it_has() -> None:
    bound = _samples({"field": "VAR_00000000", "value": ["female"]})
    fields = next(i for i in _snps_sheet() if i.name == _SAMPLES).filter_fields

    labels = vocabulary_labels(bound, _snps_sheet())

    assert labels.labels == []
    assert labels.unlabelled == [
        UnlabelledPick(
            param=_SAMPLES,
            term="VAR_00000000",
            labels=[f.display for f in fields],
        )
    ]
    assert len(labels.unlabelled[0].labels) == 27


def test_the_bound_label_joins_the_label_of_each_term() -> None:
    """The row's label and the per-term labels come from one reading."""
    picks: dict[str, ParamValue] = {
        "profileset_generic": SinglePickValue(value=_PROFILESET),
        "samples_percentile_generic": MultiPickValue(
            values=["asexual blood stages", "salivary gland sporozoite"]
        ),
        "protein_coding_only": SinglePickValue(value="maybe"),
    }
    clauses = _samples(
        {"field": _SEX, "type": "string", "value": ["female"]},
        {"field": "VAR_00000000", "value": ["female"]},
        {"field": _SAMPLE_NAME, "value": ["PfSample-not-listed"]},
    )
    read = [
        (
            vocabulary_labels(_bound(picks), _sheet()),
            bind_values(picks, "stated", _sheet()),
        ),
        (
            vocabulary_labels(clauses, _snps_sheet()),
            bind_values({_SAMPLES: clauses[_SAMPLES].value}, "stated", _snps_sheet()),
        ),
    ]

    for labels, bound in read:
        joined = {
            name: ", ".join(m.label for m in labels.labels if m.param == name)
            for name in bound
        }
        assert joined == {name: held.label for name, held in bound.items()}


def test_a_pick_label_that_leads_with_the_value_names_the_term_alone() -> None:
    """A typeahead label writes the accession before the term; the bound
    value's label is the term, so the value is never shown twice."""
    search = suite_search("search_genes_by_interpro_domain")
    sheet = format_param_info_typed(list(search.parameters or []))
    params: dict[str, ParamValue] = {
        "domain_typeahead": MultiPickValue(values=["PF00400"]),
    }

    bound = bind_values(params, "stated", sheet)

    assert bound["domain_typeahead"].label == "WD domain, G-beta repeat"
