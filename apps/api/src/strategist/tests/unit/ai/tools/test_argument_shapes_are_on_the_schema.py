"""Each tool's argument schema states the shape it takes, and pydantic-ai's
validation refuses any other shape before the body runs."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai import Tool

from strategist.ai.lead.lead_agent import build_lead_toolset
from strategist.ai.tools.toolsets import eda, verification
from strategist.tests.unit.ai.tools.conftest import unwrap_function_toolset

_SET = "6b1d5a52-4f0e-4c3f-9a3c-8e1f6d2b7a10"
_VARIANT = {
    "label": "2-fold",
    "search_name": "GenesByRNASeqEvidence",
    "parameters": {},
}
_VARIABLE = {"entityId": "EUPATH_0000609", "variableId": "VEUPATHDB_GENE_ID"}


def _lead(name: str) -> Tool[Any]:
    return unwrap_function_toolset(build_lead_toolset()).tools[name]


def _check(name: str) -> Tool[Any]:
    return unwrap_function_toolset(verification.build_toolset()).tools[name]


def _eda(name: str) -> Tool[Any]:
    return unwrap_function_toolset(eda.build_toolset()).tools[name]


def _refused(tool: Tool[Any], args: dict[str, Any]) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as refused:
        tool.function_schema.validator.validate_python(args)
    return [
        (".".join(str(part) for part in error["loc"]), error["msg"])
        for error in refused.value.errors(include_url=False)
    ]


def _property(tool: Tool[Any], name: str) -> dict[str, Any]:
    properties: dict[str, dict[str, Any]] = tool.tool_def.parameters_json_schema[
        "properties"
    ]
    return properties[name]


def test_a_download_names_a_format_the_site_writes_and_a_built_step() -> None:
    download = _check("get_download_url")

    assert _property(download, "output_format")["enum"] == ["csv", "tab", "json"]
    assert _property(download, "wdk_step_id")["exclusiveMinimum"] == 0
    assert _refused(download, {"wdk_step_id": 0, "output_format": "xlsx"}) == [
        ("wdk_step_id", "Input should be greater than 0"),
        ("output_format", "Input should be 'csv', 'tab' or 'json'"),
    ]


def test_a_sample_names_a_built_step_or_none() -> None:
    sample = _check("get_sample_records")

    assert _refused(sample, {"wdk_step_id": -3}) == [
        ("wdk_step_id", "Input should be greater than 0")
    ]
    assert sample.function_schema.validator.validate_python({}) == {
        "wdk_step_id": None,
        "limit": 5,
    }


@pytest.mark.parametrize("tool", [_check("export_gene_set"), _lead("export_gene_set")])
def test_a_gene_set_export_is_a_csv_or_a_txt_file(tool: Tool[Any]) -> None:
    assert _property(tool, "output_format")["enum"] == ["csv", "txt"]
    assert _refused(tool, {"gene_set_id": "gs1", "output_format": "pdf"}) == [
        ("output_format", "Input should be 'csv' or 'txt'")
    ]


@pytest.mark.parametrize("tool", [_check("save_gene_set"), _lead("save_gene_set")])
def test_a_saved_gene_set_has_a_name_and_a_list_holds_a_gene(
    tool: Tool[Any],
) -> None:
    assert _refused(tool, {"name": "   "}) == [
        ("name", "String should have at least 1 character")
    ]
    assert _refused(tool, {"name": "kinases", "gene_ids": []}) == [
        ("gene_ids", "List should have at least 1 item after validation, not 0")
    ]


@pytest.mark.parametrize("tool", [_check("save_gene_set"), _lead("save_gene_set")])
def test_a_pasted_list_is_saved_without_a_step(tool: Tool[Any]) -> None:
    [(where, said)] = _refused(
        tool, {"name": "kinases", "step_id": "step_3", "gene_ids": ["PF3D7_1222600"]}
    )

    assert where == "gene_ids"
    assert "carries no strategy step" in said
    assert "Leave step_id out" in said


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (_lead("compare_search_variants"), {}),
        (_lead("compare_variants_scored"), {"control_set_id": _SET}),
    ],
)
def test_a_comparison_takes_two_variants_at_least(
    tool: Tool[Any], args: dict[str, Any]
) -> None:
    assert _property(tool, "variants")["minItems"] == 2
    assert _refused(tool, {**args, "variants": [_VARIANT]}) == [
        ("variants", "List should have at least 2 items after validation, not 1")
    ]


def test_a_count_filter_names_its_column_and_its_values_together() -> None:
    tally = _lead("count_by_column")
    asked = {"search": _VARIANT, "record_type": "dataset", "column": "organism"}

    assert "only_column" not in tally.tool_def.parameters_json_schema["properties"]
    assert _refused(tally, {**asked, "only": {"column": "newcategory"}}) == [
        ("only.values", "Field required")
    ]
    assert _refused(tally, {**asked, "only": {"column": "c", "values": []}}) == [
        ("only.values", "List should have at least 1 item after validation, not 0")
    ]


def test_groups_that_share_a_label_are_refused_by_the_schema() -> None:
    compute = _eda("run_eda_compute")
    args = {
        "identifier_variable": _VARIABLE,
        "value_variable": _VARIABLE,
        "comparator_variable": _VARIABLE,
        "group_a_labels": ["24h pbm", "18h pbm"],
        "group_b_labels": ["18h pbm", "0h"],
    }

    [(where, said)] = _refused(compute, args)

    assert compute.args_validator is None
    assert where == "group_b_labels"
    assert "18h pbm" in said
    assert "A sample cannot be its own control" in said


@pytest.mark.parametrize(
    ("tool", "argument", "args"),
    [
        (_lead("read_control_set"), "control_set_id", {}),
        (_lead("compare_variants_scored"), "control_set_id", {"variants": []}),
        (_lead("read_gene_ids_from_strategy"), "strategy_id", {}),
    ],
)
def test_a_strategist_id_is_a_uuid_and_says_a_wdk_id_is_not_one(
    tool: Tool[Any], argument: str, args: dict[str, Any]
) -> None:
    declared = _property(tool, argument)
    refused = _refused(tool, {**args, argument: "441030803"})

    assert declared["format"] == "uuid"
    assert "A WDK strategy or step id is a different id" in declared["description"]
    assert (argument, "Input should be a valid UUID") in [
        (where, said.split(",")[0]) for where, said in refused
    ]
