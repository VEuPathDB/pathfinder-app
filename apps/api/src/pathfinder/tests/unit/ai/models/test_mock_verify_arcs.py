"""The VERIFY call sequence of the arcs that verify, on plasmodb and on vectorbase."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.separation import AttachedControls
from pathfinder.tests.unit.ai.models._mock_turns import (
    STRATEGY_ROOT_WDK_ID,
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
def test_the_controls_test_runs_last_on_the_root_the_order_samples(
    site_id: str,
) -> None:
    controls = SiteValues.for_site(site_id).controls

    calls = play(
        "verification", site_id, "[[arc:controls-test]]", work_order=verify_order(12)
    )

    assert names(calls) == [
        *_REVIEW[:-1],
        "run_control_tests_on_step",
        "final_result",
    ]
    assert args_of(calls, "run_control_tests_on_step") == [
        {
            "wdk_step_id": STRATEGY_ROOT_WDK_ID,
            "positive_controls": controls.positive_ids,
            "negative_controls": controls.negative_ids,
        }
    ]


def test_an_adopted_strategy_is_tested_with_the_controls_it_was_measured_on() -> None:
    attached = AttachedControls(
        task_id="task-1",
        control_set_id="cs-1",
        positives=["AGAP000046", "AGAP000128"],
        negatives=["AGAP000427"],
    )

    calls = play(
        "verification",
        "vectorbase",
        "[[arc:separation]]",
        work_order=verify_order(12, attached),
    )

    (test,) = args_of(calls, "run_control_tests_on_step")
    assert test["positive_controls"] == ["AGAP000046", "AGAP000128"]
    assert test["negative_controls"] == ["AGAP000427"]


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


def test_the_controls_test_runs_on_the_controls_the_message_pastes() -> None:
    text = (
        "Test this strategy against my controls. [[arc:controls-test]]\n"
        "Positive controls: AGAP000046 AGAP000128\n"
        "Negative controls: AGAP000427"
    )

    calls = play("verification", "vectorbase", text, work_order=verify_order(12))

    assert args_of(calls, "run_control_tests_on_step") == [
        {
            "wdk_step_id": STRATEGY_ROOT_WDK_ID,
            "positive_controls": ["AGAP000046", "AGAP000128"],
            "negative_controls": ["AGAP000427"],
        }
    ]
