from __future__ import annotations

import pytest
from assistant_core.platform.types import JSONObject
from veupathdb.errors import ValidationError

from pathfinder.services.strategies.plan_validation import validate_plan_or_raise


def _codes(exc: ValidationError) -> list[str]:
    assert exc.errors is not None
    out: list[str] = []
    for err in exc.errors:
        assert isinstance(err, dict)
        code = err.get("code")
        assert isinstance(code, str)
        out.append(code)
    return out


def test_valid_leaf_plan_parses() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {"id": "a", "searchName": "GenesByText"},
    }
    ast = validate_plan_or_raise(plan)
    assert ast.record_type == "transcript"
    assert ast.root.search_name == "GenesByText"


def test_empty_dict_is_invalid_strategy() -> None:
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise({})
    assert exc.value.title == "Invalid strategy"
    assert _codes(exc.value) == ["INVALID_STRATEGY"]


def test_root_not_an_object_is_invalid_strategy() -> None:
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise({"recordType": "transcript", "root": "nope"})
    assert _codes(exc.value) == ["INVALID_STRATEGY"]


def test_empty_search_name_leaf_reports_missing_search_name() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {"id": "a", "searchName": ""},
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert "MISSING_SEARCH_NAME" in _codes(exc.value)


def test_empty_record_type_reports_missing_record_type() -> None:
    plan: JSONObject = {
        "recordType": "",
        "root": {"id": "a", "searchName": "GenesByText"},
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert "MISSING_RECORD_TYPE" in _codes(exc.value)


def test_combine_without_operator_is_rejected_by_model() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {
            "id": "c",
            "primaryInput": {"id": "a", "searchName": "GenesByText"},
            "secondaryInput": {"id": "b", "searchName": "GenesByGoTerm"},
        },
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert _codes(exc.value) == ["INVALID_STRATEGY"]


def test_invalid_operator_value_is_rejected_by_model() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {
            "id": "c",
            "operator": "FROBNICATE",
            "primaryInput": {"id": "a", "searchName": "GenesByText"},
            "secondaryInput": {"id": "b", "searchName": "GenesByGoTerm"},
        },
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert _codes(exc.value) == ["INVALID_STRATEGY"]


def test_combine_with_same_step_on_both_inputs_is_rejected() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {
            "id": "c",
            "operator": "UNION",
            "primaryInput": {"id": "dup", "searchName": "GenesByText"},
            "secondaryInput": {"id": "dup", "searchName": "GenesByText"},
        },
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert _codes(exc.value) == ["INVALID_STRATEGY"]


def test_duplicate_step_ids_across_tree_are_rejected() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {
            "id": "shared",
            "operator": "UNION",
            "primaryInput": {"id": "shared", "searchName": "GenesByText"},
            "secondaryInput": {"id": "b", "searchName": "GenesByGoTerm"},
        },
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert _codes(exc.value) == ["INVALID_STRATEGY"]


def test_colocate_without_colocation_params_is_rejected() -> None:
    plan: JSONObject = {
        "recordType": "transcript",
        "root": {
            "id": "c",
            "operator": "COLOCATE",
            "primaryInput": {"id": "a", "searchName": "GenesByText"},
            "secondaryInput": {"id": "b", "searchName": "GenesByGoTerm"},
        },
    }
    with pytest.raises(ValidationError) as exc:
        validate_plan_or_raise(plan)
    assert _codes(exc.value) == ["INVALID_STRATEGY"]
