"""The mock frames the orthology round trip the site builds: the seed tree
INTERSECT a transform back over a transform out over a copy of that tree."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.growths import round_trip_spec
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import frame_call, set_structure_args
from pathfinder.ai.models.mock.strategy_specs import combined_spec
from pathfinder.domain.strategy.operational_spec import StructureNode

_PLASMO = SiteValues.for_site("plasmodb")


def test_the_round_trip_goes_out_and_back_to_the_site_organism() -> None:
    plan = round_trip_spec(_PLASMO)

    signal, domains, there, back = plan.criteria
    assert signal.search_name == "GenesWithSignalPeptide"
    assert domains.search_name == "GenesByTransmembraneDomains"
    assert there.search_name == back.search_name == "GenesByOrthologs"
    assert there.values == {"isSyntenic": "yes"}
    assert there.alt_param == "organism"
    assert back.values == {
        "organism": ["Plasmodium falciparum 3D7"],
        "isSyntenic": "yes",
    }
    assert {there.role, back.role} == {"transform"}


def test_the_round_trip_is_kept_by_an_intersect_over_a_copy() -> None:
    plan = round_trip_spec(_PLASMO)
    signal, domains, there, back = plan.criteria
    seed = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            StructureNode(kind="leaf", criterion_id=signal.criterion_id),
            StructureNode(kind="leaf", criterion_id=domains.criterion_id),
        ],
    )

    assert plan.structure == StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            seed,
            StructureNode(
                kind="transform",
                criterion_id=back.criterion_id,
                inputs=[
                    StructureNode(
                        kind="transform",
                        criterion_id=there.criterion_id,
                        inputs=[StructureNode(kind="copy", inputs=[seed])],
                    )
                ],
            ),
        ],
    )
    sent = set_structure_args(plan)["root"]
    assert sent["inputs"][1]["inputs"][0]["inputs"][0]["kind"] == "copy"


def test_a_plan_with_a_transform_ranks_it_before_binding() -> None:
    plan = round_trip_spec(_PLASMO)

    ranked = frame_call(plan, frozenset(), [], "")

    assert ranked.tool_name == "search_for_searches"
    assert ranked.args_as_dict() == {
        "query": "syntenic orthologs of the Plasmodium falciparum 3D7 genes"
    }
    listed = frozenset({"list_searches", "search_for_searches"})
    assert frame_call(plan, listed, [], "").tool_name == "set_criterion"


def test_a_plan_without_a_transform_ranks_its_title() -> None:
    plan = combined_spec(_PLASMO)

    ranked = frame_call(plan, frozenset(), [], "")

    assert ranked.args_as_dict() == {"query": plan.title}
