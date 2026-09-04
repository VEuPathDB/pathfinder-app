"""The wire models are the shapes the pure predicates are declared over."""

from __future__ import annotations

import json
from pathlib import Path

from pathfinder.domain.eda import find_gene_entity, validate_filters
from pathfinder.domain.eda_compute_config import (
    ComputeConfigFacts,
    validate_compute_config,
)
from pathfinder.domain.eda_filter_checks import (
    DateSetFacts,
    FilterFacts,
    LongitudeBoundsFacts,
    MultiFilterFacts,
    NumberSetFacts,
    RangeBoundsFacts,
    StringSetFacts,
    SubFilterFacts,
)
from pathfinder.domain.eda_study import (
    EntityFacts,
    StudyFacts,
    ValueVariableFacts,
    VariableFacts,
)
from pathfinder.integrations.eda.models import (
    EdaCategoryVariable,
    EdaComparator,
    EdaDateRangeFilter,
    EdaDateSetFilter,
    EdaDateVariable,
    EdaDifferentialExpressionConfig,
    EdaEntity,
    EdaIntegerVariable,
    EdaLabeledRange,
    EdaLongitudeRangeFilter,
    EdaLongitudeVariable,
    EdaMultiFilter,
    EdaNumberRangeFilter,
    EdaNumberSetFilter,
    EdaNumberVariable,
    EdaStringSetFilter,
    EdaStringVariable,
    EdaStudyDetail,
    EdaStudyDetailResponse,
    EdaSubFilter,
    EdaVariableSpec,
)

FIXTURES = Path(__file__).parent / "fixtures"

_SAMPLES = "ENT_8151325d"
_COUNTS = "ENT_fd574cd6"
_TEMPERATURE = "VAR_081ab087"


def _de_study() -> EdaStudyDetail:
    return EdaStudyDetailResponse.model_validate(
        json.loads((FIXTURES / "study_detail_de.json").read_text())
    ).study


def _typed_study() -> EdaStudyDetail:
    """A study with every variable type the filter union can target."""
    return EdaStudyDetail(
        id="STUDY_typed",
        root_entity=EdaEntity(
            id="E",
            variables=[
                EdaStringVariable(id="S", vocabulary=["no", "yes"]),
                EdaIntegerVariable(id="I"),
                EdaNumberVariable(id="N"),
                EdaDateVariable(id="D"),
                EdaLongitudeVariable(id="L"),
                EdaCategoryVariable(id="CAT", display_type="multifilter"),
                EdaStringVariable(id="CHILD", parent_id="CAT", vocabulary=["Yes"]),
            ],
        ),
    )


def test_the_study_detail_is_a_study_facts() -> None:
    study: StudyFacts = _de_study()
    entity: EntityFacts = study.root_entity
    assert study.id == "STUDY_e973eadd57"
    assert entity.id == _SAMPLES
    assert [child.id for child in entity.children] == [_COUNTS]


def test_every_variable_union_member_is_a_variable_facts() -> None:
    variables: list[VariableFacts] = list(_typed_study().root_entity.variables)
    assert [variable.type for variable in variables] == [
        "string",
        "integer",
        "number",
        "date",
        "longitude",
        "category",
        "string",
    ]
    category: VariableFacts = EdaCategoryVariable(id="CAT", display_type="multifilter")
    assert category.display_type == "multifilter"
    valued: ValueVariableFacts = EdaStringVariable(
        id="S", vocabulary=["a"], is_multi_valued=True
    )
    assert valued.vocabulary == ["a"]
    assert valued.is_multi_valued is True


def test_every_wire_filter_is_a_filter_facts() -> None:
    filters: list[FilterFacts] = [
        EdaStringSetFilter(entity_id="E", variable_id="S", string_set=["yes"]),
        EdaNumberSetFilter(entity_id="E", variable_id="I", number_set=[1.0]),
        EdaDateSetFilter(
            entity_id="E", variable_id="D", date_set=["2017-05-05T00:00:00"]
        ),
        EdaNumberRangeFilter(entity_id="E", variable_id="I", min=0.0, max=1.0),
        EdaDateRangeFilter(
            entity_id="E",
            variable_id="D",
            min="2017-05-05T00:00:00",
            max="2017-05-08T00:00:00",
        ),
        EdaLongitudeRangeFilter(entity_id="E", variable_id="L", left=0.0, right=1.0),
        EdaMultiFilter(
            entity_id="E",
            variable_id="CAT",
            operation="union",
            sub_filters=[EdaSubFilter(variable_id="CHILD", string_set=["Yes"])],
        ),
    ]
    assert [entry.type for entry in filters] == [
        "stringSet",
        "numberSet",
        "dateSet",
        "numberRange",
        "dateRange",
        "longitudeRange",
        "multiFilter",
    ]
    assert validate_filters(_typed_study(), filters) == []


def test_each_payload_protocol_is_satisfied_by_its_wire_filter() -> None:
    strings: StringSetFacts = EdaStringSetFilter(
        entity_id="E", variable_id="S", string_set=["yes"]
    )
    numbers: NumberSetFacts = EdaNumberSetFilter(
        entity_id="E", variable_id="I", number_set=[1.0]
    )
    dates: DateSetFacts = EdaDateSetFilter(
        entity_id="E", variable_id="D", date_set=["2017-05-05T00:00:00"]
    )
    number_bounds: RangeBoundsFacts = EdaNumberRangeFilter(
        entity_id="E", variable_id="I", min=0.0, max=1.0
    )
    date_bounds: RangeBoundsFacts = EdaDateRangeFilter(
        entity_id="E",
        variable_id="D",
        min="2017-05-05T00:00:00",
        max="2017-05-08T00:00:00",
    )
    longitude: LongitudeBoundsFacts = EdaLongitudeRangeFilter(
        entity_id="E", variable_id="L", left=0.0, right=1.0
    )
    sub: SubFilterFacts = EdaSubFilter(variable_id="CHILD", string_set=["Yes"])
    multi: MultiFilterFacts = EdaMultiFilter(
        entity_id="E",
        variable_id="CAT",
        operation="union",
        sub_filters=[EdaSubFilter(variable_id="CHILD", string_set=["Yes"])],
    )
    assert list(strings.string_set) == ["yes"]
    assert list(numbers.number_set) == [1.0]
    assert list(dates.date_set) == ["2017-05-05T00:00:00"]
    assert (number_bounds.min, number_bounds.max) == (0.0, 1.0)
    assert (date_bounds.min, date_bounds.max) == (
        "2017-05-05T00:00:00",
        "2017-05-08T00:00:00",
    )
    assert (longitude.left, longitude.right) == (0.0, 1.0)
    assert list(sub.string_set) == ["Yes"]
    assert multi.operation == "union"
    assert [entry.variable_id for entry in multi.sub_filters] == ["CHILD"]


def test_the_payload_of_every_wire_filter_reaches_the_predicate() -> None:
    """Each error names a payload value, so each narrow Protocol matched at runtime."""
    errors = validate_filters(
        _typed_study(),
        [
            EdaStringSetFilter(entity_id="E", variable_id="S", string_set=["maybe"]),
            EdaNumberSetFilter(entity_id="E", variable_id="I", number_set=[60.5]),
            EdaDateSetFilter(entity_id="E", variable_id="D", date_set=["2017-05-11"]),
            EdaNumberRangeFilter(entity_id="E", variable_id="I", min=100.0, max=0.0),
            EdaDateRangeFilter(
                entity_id="E",
                variable_id="D",
                min="2017-05-05",
                max="2017-05-08T00:00:00",
            ),
            EdaLongitudeRangeFilter(
                entity_id="E", variable_id="L", left=15.5, right=15.5
            ),
            EdaMultiFilter(
                entity_id="E",
                variable_id="CAT",
                operation="union",
                sub_filters=[EdaSubFilter(variable_id="CHILD", string_set=["No"])],
            ),
        ],
    )
    assert len(errors) == 7
    assert "maybe" in errors[0]
    assert "no, yes" in errors[0]
    assert "60.5" in errors[1]
    assert "2017-05-11T00:00:00" in errors[2]
    assert "min 100.0 above max 0.0" in errors[3]
    assert "2017-05-05T00:00:00" in errors[4]
    assert "left 15.5 equal to right 15.5" in errors[5]
    assert "No" in errors[6]
    assert "Yes" in errors[6]


def test_a_category_variable_carries_no_vocabulary_and_is_still_walked() -> None:
    """The category member of the union has no value fields, and the predicate copes."""
    errors = validate_filters(
        _typed_study(),
        [EdaStringSetFilter(entity_id="E", variable_id="CAT", string_set=["Yes"])],
    )
    assert len(errors) == 1
    assert "category" in errors[0]
    assert "stringSet applies to a variable of type string" in errors[0]


def test_find_gene_entity_runs_over_the_recorded_tree() -> None:
    result = find_gene_entity(_de_study())
    assert result.entity_id == _COUNTS
    assert result.error is None


def test_validate_filters_runs_over_the_recorded_tree_and_the_wire_filter() -> None:
    errors = validate_filters(
        _de_study(),
        [
            EdaStringSetFilter(
                entity_id=_SAMPLES, variable_id=_TEMPERATURE, string_set=["normal"]
            )
        ],
    )
    assert errors == []


def test_an_out_of_vocabulary_value_on_the_recorded_tree_is_caught() -> None:
    errors = validate_filters(
        _de_study(),
        [
            EdaStringSetFilter(
                entity_id=_SAMPLES, variable_id=_TEMPERATURE, string_set=["tepid"]
            )
        ],
    )
    assert len(errors) == 1
    assert "tepid" in errors[0]
    assert "febrile, normal" in errors[0]


def _de_config(group_a: list[str]) -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id=_COUNTS, variable_id="SEQUENCE_READ_COUNT_SENSE"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(entity_id=_SAMPLES, variable_id=_TEMPERATURE),
            group_a=[EdaLabeledRange(label=label) for label in group_a],
            group_b=[EdaLabeledRange(label="febrile")],
        ),
    )


def test_the_compute_config_is_a_compute_config_facts() -> None:
    config: ComputeConfigFacts = _de_config(["normal"])
    assert config.differential_expression_method == "DESeq"
    assert config.comparator.variable.entity_id == _SAMPLES
    assert [entry.label for entry in config.comparator.group_b] == ["febrile"]
    assert validate_compute_config(_de_study(), config) == []


def test_a_label_outside_the_recorded_vocabulary_is_caught_through_the_wire_config() -> (
    None
):
    errors = validate_compute_config(_de_study(), _de_config(["NOT_A_VALUE"]))
    assert len(errors) == 1
    assert "NOT_A_VALUE" in errors[0]
    assert "febrile, normal" in errors[0]
