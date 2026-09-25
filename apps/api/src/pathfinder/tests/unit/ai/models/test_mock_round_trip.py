"""The mock frames a syntenic-ortholog request as the round trip the site builds:
the seed INTERSECT a transform back over a transform out over a copy of the seed."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.arcs import spec_for
from pathfinder.ai.models.mock.specs import frame_call, set_structure_args
from pathfinder.domain.strategy.operational_spec import StructureNode

_REQUEST = "keep only those with syntenic orthologs in Plasmodium vivax P01"


def test_the_request_frames_the_round_trip_on_plasmodb() -> None:
    plan = spec_for(_REQUEST, "plasmodb")

    seed, there, back = plan.criteria
    assert seed.search_name == "GenesByTaxon"
    assert there.search_name == back.search_name == "GenesByOrthologs"
    assert there.values == {
        "organism": ["Plasmodium vivax P01"],
        "isSyntenic": "yes",
    }
    assert back.values == {
        "organism": ["Plasmodium falciparum 3D7"],
        "isSyntenic": "yes",
    }
    assert {there.role, back.role} == {"transform"}


def test_the_round_trip_is_kept_by_an_intersect_over_a_copy() -> None:
    plan = spec_for(_REQUEST, "plasmodb")
    seed, there, back = plan.criteria
    leaf = StructureNode(kind="leaf", criterion_id=seed.criterion_id)

    assert plan.structure == StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            leaf,
            StructureNode(
                kind="transform",
                criterion_id=back.criterion_id,
                inputs=[
                    StructureNode(
                        kind="transform",
                        criterion_id=there.criterion_id,
                        inputs=[StructureNode(kind="copy", inputs=[leaf])],
                    )
                ],
            ),
        ],
    )
    sent = set_structure_args(plan)["root"]
    assert sent["inputs"][1]["inputs"][0]["inputs"][0]["kind"] == "copy"


def test_a_plan_with_a_transform_ranks_it_before_binding() -> None:
    plan = spec_for(_REQUEST, "plasmodb")
    searches = frame_call(plan, frozenset(), [])

    ranked = frame_call(plan, frozenset({searches.tool_name}), [])

    assert ranked.tool_name == "search_for_searches"
    assert ranked.args_as_dict() == {
        "query": "syntenic orthologs in Plasmodium vivax P01"
    }
    assert (
        frame_call(
            plan, frozenset({"list_searches", "search_for_searches"}), []
        ).tool_name
        == "set_criterion"
    )


def test_a_plan_without_a_transform_lists_no_transforms() -> None:
    plan = spec_for("comprehensive kinase strategy", "plasmodb")

    assert frame_call(plan, frozenset({"list_searches"}), []).tool_name == (
        "set_criterion"
    )
