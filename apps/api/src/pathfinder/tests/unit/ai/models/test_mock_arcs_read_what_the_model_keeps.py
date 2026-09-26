"""The arcs read only what the history processors leave the model: an answer
more than three tool calls old reaches it cut to a stub."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.models._mock_pins import framed_pins
from pathfinder.tests.unit.ai.models._mock_turns import (
    LIVE_ROOT_COUNT,
    SHEET_ORGANISMS,
    Scene,
    args_of,
    names,
    play,
    verify_order,
)

SITES = ("plasmodb", "vectorbase", "toxodb")
_TEXT = "Upregulated after a blood meal [[arc:other-site-experiment]]"
_ORDER = "Frame work order: mock frame"
_NEAREST = "GenesByBloodMealSeries"
# A ranked read as the catalog returns it: every hit carries its description.
_RANKED = [
    {"note": "No search on this site states the request closely."},
    *(
        {
            "name": name,
            "displayName": name,
            "description": f"Genes the {name} experiment ranks by fold change. " * 3,
            "recordType": "transcript",
            "semanticSimilarity": similarity,
        }
        for name, similarity in (
            ("GenesByFoldChange", 0.41),
            ("GenesByPercentile", 0.38),
            (_NEAREST, 0.47),
            ("GenesByTimeSeries", 0.33),
        )
    ),
    {"otherSites": {"experiments": [{"datasetId": "DS_elsewhere"}]}},
]
_TESTED = {
    "status": "success",
    "result": {
        "positiveRecoveredIds": [f"GENE_{n:04d}" for n in range(80)],
        "positiveMissedIds": [],
        "negativeAdmittedIds": [],
        "negativeExcludedIds": ["NEG_1", "NEG_2", "NEG_3"],
    },
}
_COUNTS = "80 of 80 positive controls recovered; 0 of 3 negative controls returned."


@pytest.mark.parametrize("site_id", SITES)
def test_the_check_states_the_counts_of_a_large_control_test(site_id: str) -> None:
    calls = play(
        "verification",
        site_id,
        "Test it [[arc:controls-test]]",
        work_order=verify_order(12),
        scene=Scene(answers={"run_control_tests_on_step": _TESTED}),
    )

    assert calls[-1].args_as_dict()["digest"]["prose"] == _COUNTS


@pytest.mark.parametrize("site_id", SITES)
def test_the_controls_reply_on_a_built_thread_changes_nothing(site_id: str) -> None:
    digest = {"digest": {"success": True, "prose": _COUNTS}}
    scene = Scene(instructions=framed_pins(), answers={"verify_strategy": digest})

    calls = play("lead", site_id, "Test it [[arc:controls-test]]", scene=scene)

    assert calls[-1].args_as_dict()["strategyChanged"] is False
    assert calls[-1].args_as_dict()["prose"] == (
        f"{_COUNTS} The strategy returns {LIVE_ROOT_COUNT:,} genes."
    )


@pytest.mark.parametrize("site_id", SITES)
def test_the_own_nearest_hit_is_bound_on_its_rank(site_id: str) -> None:
    frame = play(
        "frame",
        site_id,
        _TEXT,
        work_order=_ORDER,
        scene=Scene(answers={"search_for_searches": _RANKED}),
    )

    bound = [a for a in args_of(frame, "set_criterion") if "params" in a]
    assert names(frame)[:2] == ["list_searches", "search_for_searches"]
    assert bound[0]["search_name"] == _NEAREST
    assert bound[0]["why"] == {
        "basis": "nearest",
        "term": "Upregulated after a blood meal",
        "reason": (
            "Of the searches ranked for Upregulated after a blood meal, this one "
            "scored nearest."
        ),
    }


@pytest.mark.parametrize("site_id", SITES)
def test_the_own_hit_frame_ends_ready_once_the_ranking_is_cut(site_id: str) -> None:
    frame = play(
        "frame",
        site_id,
        _TEXT,
        work_order=_ORDER,
        scene=Scene(answers={"search_for_searches": _RANKED}),
    )

    assert names(frame)[-2:] == ["set_structure", "final_result"]
    assert frame[-1].args_as_dict()["disposition"] == "spec_ready"
    assert "read_experiment" not in names(frame)


@pytest.mark.parametrize("site_id", SITES)
def test_a_sweep_that_builds_states_the_count_the_build_answered(site_id: str) -> None:
    unbuilt = Scene(answers={"get_live_strategy_state": {}})

    calls = play("lead", site_id, "[[arc:sweep]]", scene=unbuilt)

    assert str(calls[-1].args_as_dict()["prose"]).endswith(
        "- Predicted Signal Peptide, chosen for SignalP version\n\n"
        "The strategy returns 12 genes."
    )


# An organism name longer than the graph pin prints a parameter value.
_LONG_ORGANISM = "Trypanosoma cruzi CL Brener Esmeraldo-like"


def _orthology_graph(site_id: str, target: str) -> StrategyGraph:
    """A seed on the site's organism carried to its orthologs in ``target``."""
    graph = StrategyGraph("g1", "orthologs", site_id)
    graph.record_type = "transcript"
    seed = MultiPickValue(values=[SiteValues.for_site(site_id).organism])
    add_step_to_graph(
        graph,
        StrategyStep(
            id="step_seed",
            kind=StepKind.SEARCH,
            search_name="GenesWithSignalPeptide",
            parameters={"organism": seed},
        ),
    )
    add_step_to_graph(
        graph,
        StrategyStep(
            id="step_root",
            kind=StepKind.TRANSFORM,
            search_name="GenesByOrthologs",
            primary_input_id="step_seed",
            parameters={"organism": MultiPickValue(values=[target])},
        ),
    )
    return graph


@pytest.mark.parametrize("site_id", SITES)
@pytest.mark.parametrize("long_name", [False, True])
def test_the_review_names_the_organism_of_the_pinned_root(
    site_id: str, long_name: bool
) -> None:
    """The strategy read is cut to a stub; the graph pin still names the root."""
    target = _LONG_ORGANISM if long_name else SHEET_ORGANISMS[site_id][1]
    scene = Scene(
        graph=_orthology_graph(site_id, target),
        answers={
            "get_strategy": "get_strategy returned 2 steps.",
            "get_sample_records": {"records": [{"id": "ORTH_0001.1"}]},
            "read_gene_record": {
                "geneId": "ORTH_0001",
                "organism": target,
                "product": "a conserved protein",
                "recordUrl": f"https://{site_id}.example/record",
            },
        },
    )

    calls = play(
        "verification",
        site_id,
        "[[arc:orthologs]]",
        work_order=verify_order(12),
        scene=scene,
    )

    review = calls[-1].args_as_dict()["digest"]["review"]
    assert [row["text"] for row in review["requirements"]] == [target]
    assert [gene["fits"] for gene in review["sampledGenes"]] == ["yes"]
