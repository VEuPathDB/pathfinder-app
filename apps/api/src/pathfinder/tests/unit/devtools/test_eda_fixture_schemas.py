"""Every recorded EDA body, measured against the pinned service-eda RAML."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError
from veupathdb.devtools.eda_schemas import (
    BINDINGS,
    LIBRARY_FILE,
    SPEC_DEFECTS,
    SpecDefect,
    binding_checks,
    load_pin,
    main,
    pinned,
    raml_pin_drift,
    reached_types,
    verify_body,
    verify_wire_body,
)
from veupathdb.testing.eda_fixtures import UPSTREAM_DIR

from pathfinder.tests._support.eda_fixtures import FIXTURES

_BODY: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


def _fixture(name: str) -> dict[str, Any]:
    """One recorded body, as a mutable copy the mutation tests can bend."""
    path = next(binding.file for binding in BINDINGS if binding.fixture == name)
    return _BODY.validate_python(json.loads(path.read_text()))


def test_the_vendored_raml_is_byte_identical_to_the_pin() -> None:
    assert raml_pin_drift(load_pin()) == ()


def test_the_pin_holds_exactly_the_raml_on_disk() -> None:
    pin = load_pin()
    assert {path.name for path in UPSTREAM_DIR.glob("*.raml")} == set(pin.files)
    assert set(pin.files) == {LIBRARY_FILE, "hash-id.raml"}
    assert pin.repo == "VEuPathDB/service-eda"
    assert pin.root == "schema"


def test_the_pinned_library_declares_the_whole_service_type_set() -> None:
    assert len(pinned().library.types) == 414


def test_the_included_hash_id_resolves_into_the_library() -> None:
    definitions = pinned().declared["definitions"]
    assert isinstance(definitions, dict)
    assert definitions["JobID"] == {
        "type": "string",
        "minLength": 32,
        "maxLength": 32,
        "pattern": "^[\\dA-Fa-f]{32}$",
    }


def test_every_recorded_fixture_binds_a_type_the_library_declares() -> None:
    declared = pinned().library.types
    assert {binding.raml_type for binding in BINDINGS} <= set(declared)
    assert all(binding.file.exists() for binding in BINDINGS)


def test_the_binding_table_is_total_over_the_fixture_manifest() -> None:
    assert {binding.fixture for binding in BINDINGS} == {
        fixture.name for fixture in FIXTURES
    }


def test_the_bound_types_reach_forty_of_the_pinned_library() -> None:
    bound = tuple(binding.raml_type for binding in BINDINGS)
    assert len(reached_types(bound)) == 40


def test_every_recorded_fixture_passes_the_type_its_endpoint_returns() -> None:
    failures = {
        check.fixture: check.errors for check in binding_checks() if check.errors
    }
    assert failures == {}


def test_a_retyped_member_fails() -> None:
    body = _fixture("count_filtered")
    body["count"] = str(body["count"])
    assert verify_wire_body("EntityCountPostResponse", body) == (
        f"count: '{body['count']}' is not of type 'integer'",
    )


def test_a_missing_required_member_fails() -> None:
    body = _fixture("compute_job_lookup")
    del body["status"]
    assert verify_wire_body("JobResponse", body) == (
        "<root>: 'status' is a required property",
    )


def test_a_member_outside_a_closed_type_fails() -> None:
    body = _fixture("compute_job_lookup")
    body["notAnEdaField"] = "x"
    assert verify_wire_body("JobResponse", body) == (
        "<root>: Additional properties are not allowed "
        "('notAnEdaField' was unexpected)",
    )


def test_a_value_outside_an_enum_fails() -> None:
    body = _fixture("compute_job_lookup")
    body["status"] = "almost-done"
    errors = verify_wire_body("JobResponse", body)
    assert len(errors) == 1
    assert errors[0].startswith("status: 'almost-done' is not one of")


def test_a_hash_id_of_the_wrong_length_fails() -> None:
    body = _fixture("compute_job_lookup")
    body["jobID"] = "abc"
    assert verify_wire_body("JobResponse", body) == (
        "jobID: 'abc' does not match '^[\\\\dA-Fa-f]{32}$'",
        "jobID: 'abc' is too short",
    )


def test_a_variable_typed_as_no_branch_of_the_union_fails() -> None:
    body = _fixture("study_detail_phenotype")
    body["study"]["rootEntity"]["variables"][0]["type"] = "not-a-variable-type"
    errors = verify_wire_body("StudyIdGetResponse", body)
    assert len(errors) == 1
    assert errors[0].startswith("study/rootEntity/variables/0: ")
    assert errors[0].endswith("is not valid under any of the given schemas")


def test_a_retyped_member_inside_the_permissions_map_fails() -> None:
    body = _fixture("permissions")
    entry = next(iter(body["perDataset"].values()))
    entry["isUserStudy"] = "yes"
    errors = verify_wire_body("PermissionsGetResponse", body)
    assert len(errors) == 1
    assert errors[0].endswith("isUserStudy: 'yes' is not of type 'boolean'")


def test_a_retyped_row_inside_the_volcano_statistics_fails() -> None:
    body = _fixture("volcano_statistics")
    body["statistics"][0]["effectSize"] = 1.5
    assert verify_wire_body("DifferentialExpressionStatsResponse", body) == (
        "statistics/0/effectSize: 1.5 is not of type 'string'",
    )


def test_a_type_the_library_does_not_declare_is_refused() -> None:
    with pytest.raises(KeyError, match="not a type the pinned library declares"):
        verify_wire_body("NotAnEdaType", {})


@pytest.mark.parametrize(
    "defect", SPEC_DEFECTS, ids=lambda d: f"{d.raml_type}.{d.member}"
)
def test_each_recorded_defect_still_contradicts_the_pinned_library(
    defect: SpecDefect,
) -> None:
    """A defect the spec has fixed must leave this table and the knowledge doc."""
    library = pinned().library
    definitions = pinned().declared["definitions"]
    assert isinstance(definitions, dict)
    names = (defect.raml_type, *library.subtypes(defect.raml_type))
    shapes = {name: _shape(definitions[name]) for name in names}
    objects = tuple(name for name in names if "properties" in shapes[name])
    holding = tuple(name for name in names if defect.holds(shapes[name]))
    assert objects != ()
    assert holding == objects


def _shape(node: Any) -> dict[str, Any]:
    assert isinstance(node, dict)
    return node


def test_the_declared_library_reports_the_defects_the_wire_document_absorbs() -> None:
    """Without the recorded defects the same bodies fail, which is why they exist."""
    raw = {
        binding.fixture: verify_body(binding.raml_type, _json(binding.file.read_text()))
        for binding in BINDINGS
    }
    assert {name: len(errors) for name, errors in raw.items() if errors} == {
        "studies_list": 3,
        "study_detail_de": 9,
        "study_detail_phenotype": 13,
        "volcano_statistics": 203,
        "permissions": 24,
    }


def test_is_category_is_the_only_reason_a_recorded_variable_fails_its_branch() -> None:
    variable = _fixture("study_detail_phenotype")["study"]["rootEntity"]["variables"][0]
    assert variable["type"] == "string"
    assert verify_body("API_StringVariable", variable) == (
        "<root>: 'isCategory' is a required property",
    )
    assert verify_wire_body("API_StringVariable", variable) == ()


def test_a_defect_that_names_no_wire_member_is_refused() -> None:
    with pytest.raises(ValidationError, match="only a rename names a wire member"):
        SpecDefect(
            raml_type="JobResponse",
            member="status",
            kind="required-but-absent",
            renamed="state",
            measured="never",
            records="nowhere",
        )


def test_the_verify_command_passes_over_the_whole_store() -> None:
    assert main(["verify"]) == 0


def _json(text: str) -> JsonValue:
    parsed: JsonValue = json.loads(text)
    return parsed
