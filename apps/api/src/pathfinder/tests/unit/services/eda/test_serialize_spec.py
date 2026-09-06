"""The one call site that turns an analysis into the eda_analysis_spec value."""

from __future__ import annotations

import json
from pathlib import Path

from veupathdb.eda.models import (
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaVariableSpec,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)

from pathfinder.services.eda.authoring import new_analysis, serialize_spec

REPO = Path(__file__).resolve().parents[8]


def test_no_filters_serializes_to_the_empty_string_not_a_json_object() -> None:
    """An empty eda_analysis_spec is legal and means no filters."""
    analysis = new_analysis(dataset_id="DS_x", display_name="x")
    assert serialize_spec(analysis) == ""


def test_a_filter_makes_the_spec_a_json_string_naming_the_dataset_id() -> None:
    analysis = new_analysis(
        dataset_id="DS_53f554ec6a",
        display_name="berghei subset",
        filters=[
            EdaStringSetFilter(
                entity_id="GENE_PHENOTYPE_DATA_ENTITY",
                variable_id="VAR_035294d0",
                string_set=["P. berghei"],
            )
        ],
    )
    spec = serialize_spec(analysis)
    parsed = json.loads(spec)
    assert parsed["studyId"] == "DS_53f554ec6a"
    assert parsed["descriptor"]["subset"]["descriptor"][0]["stringSet"] == [
        "P. berghei"
    ]


def test_the_serialized_spec_carries_no_null_valued_key() -> None:
    analysis = new_analysis(
        dataset_id="DS_x",
        display_name="x",
        filters=[EdaStringSetFilter(entity_id="E", variable_id="V", string_set=["a"])],
    )
    parsed = json.loads(serialize_spec(analysis))
    assert _no_nulls(parsed)


def _no_nulls(node: object) -> bool:
    match node:
        case dict():
            return all(v is not None and _no_nulls(v) for v in node.values())
        case list():
            return all(_no_nulls(v) for v in node)
        case _:
            return True


def test_a_computation_serializes_with_its_volcano_thresholds() -> None:
    analysis = new_analysis(
        dataset_id="DS_e973eadd57",
        display_name="de",
        computation=EdaComputation(
            computation_id="de1",
            descriptor=EdaComputationDescriptor(
                configuration=EdaDifferentialExpressionConfig(
                    identifier_variable=EdaVariableSpec(
                        entity_id="ENT_fd574cd6", variable_id="VEUPATHDB_GENE_ID"
                    ),
                    value_variable=EdaVariableSpec(
                        entity_id="ENT_fd574cd6",
                        variable_id="SEQUENCE_READ_COUNT_SENSE",
                    ),
                    comparator=EdaComparator(
                        variable=EdaVariableSpec(
                            entity_id="ENT_8151325d", variable_id="VAR_081ab087"
                        ),
                        group_a=[EdaLabeledRange(label="normal")],
                        group_b=[EdaLabeledRange(label="febrile")],
                    ),
                )
            ),
            visualizations=[
                EdaVisualization(
                    visualization_id="v1",
                    display_name="Volcano",
                    descriptor=EdaVolcanoDescriptor(
                        configuration=EdaVolcanoConfiguration(
                            effect_size_threshold=1.0,
                            significance_threshold=0.05,
                        )
                    ),
                )
            ],
        ),
    )
    parsed = json.loads(serialize_spec(analysis))
    viz = parsed["descriptor"]["computations"][0]["visualizations"][0]["descriptor"]
    assert viz["type"] == "volcanoplot"
    assert viz["configuration"]["effectSizeThreshold"] == 1.0
    assert viz["configuration"]["significanceThreshold"] == 0.05
    assert viz["configuration"]["effectDirection"] == "upAndDown"


_PACKAGE = "apps/api/src/pathfinder"

_SEARCHED = (
    f"{_PACKAGE}/services",
    f"{_PACKAGE}/ai",
    f"{_PACKAGE}/jobs",
    f"{_PACKAGE}/transport",
    f"{_PACKAGE}/persistence",
)

_AUTHORING = f"{_PACKAGE}/services/eda/authoring.py"

# Every ``model_dump_json`` the searched trees are allowed to carry, with the
# count each file holds and what it serializes. Only the first one is an
# analysis.
_ALLOWED: tuple[tuple[str, int, str], ...] = (
    (_AUTHORING, 1, "serialize_spec, the one eda_analysis_spec call site"),
    (f"{_PACKAGE}/ai/agents/state.py", 1, "an agent context value, not an analysis"),
    (
        f"{_PACKAGE}/transport/http/sse_utils.py",
        2,
        "one SSE event dump and the docstring that names it",
    ),
)


def _dump_counts() -> dict[str, int]:
    """Every ``model_dump_json`` in the searched trees, counted per file."""
    counts: dict[str, int] = {}
    for tree in _SEARCHED:
        for path in sorted((REPO / tree).rglob("*.py")):
            found = sum(
                1 for line in path.read_text().splitlines() if "model_dump_json" in line
            )
            if found:
                counts[path.relative_to(REPO).as_posix()] = found
    return counts


def test_the_grep_gate_addresses_the_real_source_tree() -> None:
    """The gate below is vacuous unless the scan reaches authoring.py."""
    assert _dump_counts().get(_AUTHORING) == 1


def test_serialize_spec_is_the_only_place_an_analysis_is_dumped_to_json() -> None:
    """One call site, so there is one answer to what went into the parameter.

    A dump the allowlist does not name is a second answer, and a named one that
    disappeared means the allowlist is stale.
    """
    allowed = {path: count for path, count, _reason in _ALLOWED}
    found = _dump_counts()
    unlisted = {p: c for p, c in found.items() if allowed.get(p) != c}
    missing = {p: c for p, c in allowed.items() if found.get(p) != c}
    assert unlisted == {}, f"unallowed model_dump_json: {unlisted}"
    assert missing == {}, f"the allowlist is stale: {missing}"
