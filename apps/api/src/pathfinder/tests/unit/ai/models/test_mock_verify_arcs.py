"""The VERIFY call sequence of the arcs that verify, on plasmodb and on vectorbase."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.separation import AttachedControls
from pathfinder.tests.unit.ai.models._mock_turns import (
    CONTROL_SET_ID,
    STRATEGY_ROOT_WDK_ID,
    Scene,
    args_of,
    names,
    play,
    verify_order,
)

SITES = ("plasmodb", "vectorbase")
_REVIEW = [
    "get_strategy",
    "get_sample_records",
    "read_gene_record",
    "read_gene_record",
    "final_result",
]


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("arc", ["single", "intersect", "orthologs", "edit-param"])
def test_the_check_reads_the_strategy_then_reviews_two_records(
    arc: str, site_id: str
) -> None:
    calls = play("verification", site_id, f"[[arc:{arc}]]", work_order=verify_order(12))

    assert names(calls) == _REVIEW
    assert calls[-1].args_as_dict()["digest"]["success"] is True


@pytest.mark.parametrize("site_id", SITES)
def test_the_controls_test_runs_last_on_the_saved_set_the_listing_names(
    site_id: str,
) -> None:
    calls = play(
        "verification", site_id, "[[arc:controls-test]]", work_order=verify_order(12)
    )

    assert names(calls) == [
        *_REVIEW[:-1],
        "list_control_sets",
        "run_control_tests_on_step",
        "final_result",
    ]
    assert args_of(calls, "run_control_tests_on_step") == [
        {"wdk_step_id": STRATEGY_ROOT_WDK_ID, "control_set_id": CONTROL_SET_ID}
    ]


def test_an_adopted_strategy_is_tested_with_the_set_it_was_measured_on() -> None:
    attached = AttachedControls(
        task_id="task-1",
        control_set_id="cs-adopted",
        positives=["AGAP000046", "AGAP000128"],
        negatives=["AGAP000427"],
    )

    calls = play(
        "verification",
        "vectorbase",
        "[[arc:separation]]",
        work_order=verify_order(12, attached),
    )

    assert "list_control_sets" not in names(calls)
    assert args_of(calls, "run_control_tests_on_step") == [
        {"wdk_step_id": STRATEGY_ROOT_WDK_ID, "control_set_id": "cs-adopted"}
    ]


@pytest.mark.parametrize("site_id", SITES)
def test_an_empty_root_fails_the_check(site_id: str) -> None:
    calls = play(
        "verification", site_id, "[[arc:zero-then-relax]]", work_order=verify_order(0)
    )

    assert names(calls) == ["get_strategy", "final_result"]
    assert calls[-1].args_as_dict()["digest"]["success"] is False


def test_the_review_names_the_organism_the_root_returns() -> None:
    organism = SiteValues.for_site("vectorbase").organism

    calls = play(
        "verification", "vectorbase", "[[arc:single]]", work_order=verify_order(12)
    )

    review = calls[-1].args_as_dict()["digest"]["review"]
    assert review["requirements"][0]["text"] == organism
    assert [g["fits"] for g in review["sampledGenes"]] == ["yes", "yes"]


def test_a_check_with_no_saved_set_runs_no_control_test() -> None:
    text = (
        "Test this strategy against my controls. [[arc:controls-test]]\n"
        "Positive controls: AGAP000046 AGAP000128\n"
        "Negative controls: AGAP000427"
    )

    calls = play(
        "verification",
        "vectorbase",
        text,
        work_order=verify_order(12),
        scene=Scene(answers={"list_control_sets": []}),
    )

    assert names(calls) == [*_REVIEW[:-1], "list_control_sets", "final_result"]
