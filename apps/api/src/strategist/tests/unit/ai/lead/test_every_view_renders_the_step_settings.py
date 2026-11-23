from __future__ import annotations

from pydantic import TypeAdapter
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import (
    ColocationParams,
    CombineOp,
    StepFilter,
    StepSettings,
    StrategyAst,
    StrategyStepNode,
    settings_of,
    walk,
)

from strategist.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from strategist.ai.lead.case_memory import collect_case_candidates
from strategist.ai.lead.lead_pins import pinned_operational_spec
from strategist.ai.lead.ledger_render import render_frame_full
from strategist.ai.lead.ledger_sections import FrameSection
from strategist.ai.lead.turn_briefing import compose_turn_briefing
from strategist.domain.strategy.build_outcome import BuildOutcome, BuiltCounts
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.revision import strategy_revision
from strategist.domain.strategy.step_settings_text import (
    settings_change_text,
    settings_text,
)
from strategist.services.conversations.thread_activity import ThreadActivity
from strategist.services.eval_data.extraction import extracted_strategy
from strategist.tests._support.bound_values import bound
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.lead.conftest import pipeline_state

_FILTER = "matched_transcript_filter_array"
_ROWS = TypeAdapter(list[dict[str, object]])
_COLOCATED = ColocationParams(operation="contains", strand="same strand")


def _leaf(step_id: str, label: str, **settings: object) -> StrategyStepNode:
    return StrategyStepNode.model_validate(
        {
            "id": step_id,
            "searchName": "GenesByText",
            "displayName": label,
            "parameters": {"text_expression": {"type": "string", "value": label}},
            **settings,
        }
    )


def _tree(*, leaf_a: StrategyStepNode, operator: CombineOp, offset: int) -> StrategyAst:
    colocated = StrategyStepNode(
        id="step_c",
        search_name="__combine__",
        display_name="near kinases",
        operator=CombineOp.COLOCATE,
        colocation_params=_COLOCATED.model_copy(update={"begin_offset_a": offset}),
        primary_input=_leaf("step_b", "kinase"),
        secondary_input=_leaf("step_d", "phosphatase"),
    )
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_u",
            search_name="__combine__",
            display_name="either",
            operator=operator,
            primary_input=leaf_a,
            secondary_input=colocated,
        ),
    )


class TestTheText:
    def test_the_settings_other_than_search_and_values_in_order(self) -> None:
        settings = StepSettings(
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value="kinase")},
            operator=CombineOp.COLOCATE,
            colocation_params=_COLOCATED.model_copy(update={"begin_offset_a": 500}),
            filters=[StepFilter(name=_FILTER, value={"values": ["Y"]})],
            wdk_weight=10,
            expanded_strategy_id=9001,
            expanded_name="Saved kinases",
        )

        assert settings_text(settings) == (
            "operator COLOCATE, colocation contains, same strand, beginOffsetA 500, "
            f'filters {_FILTER}, weight 10, expands "Saved kinases"'
        )

    def test_a_step_on_every_default_has_no_text(self) -> None:
        assert settings_text(StepSettings(search_name="GenesByText")) == ""

    def test_a_weight_change_names_both_weights(self) -> None:
        assert (
            settings_change_text(
                "wdk_weight", StepSettings(wdk_weight=3), StepSettings(wdk_weight=5)
            )
            == "weight 3 -> 5"
        )


def test_an_outside_edit_names_the_filter_the_operator_and_the_colocation() -> None:
    answered = _tree(
        leaf_a=_leaf("step_a", "kinase"), operator=CombineOp.UNION, offset=0
    )
    live = _tree(
        leaf_a=_leaf(
            "step_a", "kinase", filters=[{"name": _FILTER, "value": {"values": ["N"]}}]
        ),
        operator=CombineOp.INTERSECT,
        offset=200,
    )

    briefing = compose_turn_briefing(
        ThreadActivity(), requirements=[], answered=answered, live=live
    )

    assert briefing.render().splitlines()[1:-1] == [
        f"- kinase (step_a): filter {_FILTER} added",
        "- near kinases (step_c): colocation beginOffsetA 0 -> 200",
        "- either (step_u): operator UNION -> INTERSECT",
    ]


def test_a_rewire_alone_names_that_the_combinations_changed() -> None:
    answered = _tree(
        leaf_a=_leaf("step_a", "kinase"), operator=CombineOp.UNION, offset=0
    )
    swapped = answered.model_copy(
        update={
            "root": answered.root.model_copy(
                update={
                    "primary_input": answered.root.secondary_input,
                    "secondary_input": answered.root.primary_input,
                }
            )
        }
    )

    briefing = compose_turn_briefing(
        ThreadActivity(), requirements=[], answered=answered, live=swapped
    )

    assert briefing.render().splitlines()[1:-1] == ["- the combinations changed"]


def _weighted_colocated_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="kinases near phosphatases",
        criteria=[
            Criterion(
                id="c_kinase",
                text="kinase",
                search_name="GenesByText",
                role="seed",
                weight=10,
                resolved_params=bound({"text_expression": StringValue(value="kinase")}),
            ),
            Criterion(
                id="c_phosphatase",
                text="phosphatase",
                search_name="GenesByText",
                role="seed",
                resolved_params=bound(
                    {"text_expression": StringValue(value="phosphatase")}
                ),
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.COLOCATE,
                colocation_params=_COLOCATED,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_kinase"),
                    StructureNode(kind="leaf", criterion_id="c_phosphatase"),
                ],
            )
        ),
    )


def test_the_pinned_plan_names_the_weight_and_the_colocation() -> None:
    ctx = lead_run_context()
    ctx.deps.state.domain.operational_spec = _weighted_colocated_spec()

    lines = (pinned_operational_spec(ctx) or "").splitlines()

    assert (
        next(line for line in lines if "[c_kinase]" in line).endswith("| weight 10"),
        [line for line in lines if line.startswith("- structure:")],
    ) == (
        True,
        [
            (
                "- structure: (GenesByText COLOCATE GenesByText; colocation "
                "contains, same strand)"
            )
        ],
    )


def test_the_ledger_names_the_weight_and_the_colocation() -> None:
    rendered = render_frame_full(FrameSection(spec=_weighted_colocated_spec()))

    assert (
        "    SETTINGS weight 10" in rendered.splitlines(),
        "(GenesByText COLOCATE GenesByText; colocation contains, same strand)"
        in rendered.splitlines(),
    ) == (True, True)


def test_the_case_of_a_weighted_plan_records_the_weight() -> None:
    spec = _weighted_colocated_spec()
    state = pipeline_state(
        domain=StrategyDomainState(
            operational_spec=spec,
            answered_spec=spec,
            original_request="kinases near phosphatases",
            last_build_outcome=BuildOutcome(pushed_step_ids=["c_kinase"]),
            site_verdict=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="done",
                reason="ok",
                success=True,
            ),
        ),
    )

    [(value, _key)] = collect_case_candidates(
        state, counts=BuiltCounts(by_step={"root": 12}, root_id="root")
    )

    assert (
        [
            row.get("settings")
            for row in _ROWS.validate_python(value.content["criteria"])
        ],
        value.content["structure"],
    ) == (
        ["weight 10", None],
        "(GenesByText COLOCATE GenesByText; colocation contains, same strand)",
    )


def _organism_leaf(step_id: str, **extra: object) -> dict[str, object]:
    return {
        "id": step_id,
        "searchName": "GenesByRNASeqEvidence",
        "parameters": {
            "fold_change": {"type": "string", "value": "2"},
            "organism": {
                "type": "multi-pick-vocabulary",
                "values": ["Plasmodium falciparum 3D7"],
            },
        },
        **extra,
    }


_STORED = {
    "77fd2cb9bc469208": {"recordType": "transcript", "root": _organism_leaf("a")},
    "d8a7dad6a53e4bda": {
        "recordType": "transcript",
        "root": {
            "id": "u",
            "operator": "INTERSECT",
            "wdkWeight": 4,
            "primaryInput": _organism_leaf(
                "a",
                wdkWeight=10,
                filters=[{"name": _FILTER, "value": {"values": ["Y"]}}],
            ),
            "secondaryInput": _organism_leaf("b"),
        },
        "detachedRoots": [_organism_leaf("d", wdkWeight=0)],
    },
    "8da40e201baab242": {
        "recordType": "transcript",
        "root": {
            "id": "c",
            "operator": "COLOCATE",
            "colocationParams": {
                "operation": "contains",
                "strand": "same strand",
                "beginOffsetA": 500,
            },
            "primaryInput": _organism_leaf("a"),
            "secondaryInput": {
                "id": "b",
                "searchName": "GenesByLocation",
                "parameters": {},
            },
        },
    },
}


class TestTheRevision:
    def test_a_stored_revision_keeps_its_fingerprint(self) -> None:
        assert {
            stored: strategy_revision(StrategyAst.model_validate(raw))
            for stored, raw in _STORED.items()
        } == {stored: stored for stored in _STORED}

    def test_a_tree_that_differs_only_in_its_expanded_name_is_another(self) -> None:
        def expanded(name: str) -> StrategyAst:
            return StrategyAst(
                record_type="transcript",
                root=StrategyStepNode(
                    id="u",
                    search_name="__combine__",
                    operator=CombineOp.UNION,
                    expanded_strategy_id=9001,
                    expanded_name=name,
                    primary_input=_leaf("a", "kinase"),
                    secondary_input=_leaf("b", "phosphatase"),
                ),
            )

        assert strategy_revision(expanded("Saved kinases")) != strategy_revision(
            expanded("Kinases kept")
        )

    def test_a_reordered_pick_is_the_same_revision(self) -> None:
        def picked(values: list[str]) -> StrategyAst:
            return StrategyAst(
                record_type="transcript",
                root=StrategyStepNode(
                    id="a",
                    search_name="GenesByTaxon",
                    parameters={"organism": MultiPickValue(values=values)},
                ),
            )

        assert strategy_revision(
            picked(["Plasmodium vivax P01", "Plasmodium falciparum 3D7"])
        ) == strategy_revision(
            picked(["Plasmodium falciparum 3D7", "Plasmodium vivax P01"])
        )


def test_the_extracted_strategy_keeps_every_step_setting() -> None:
    stored = _tree(
        leaf_a=_leaf(
            "step_a",
            "kinase",
            wdkWeight=10,
            filters=[{"name": _FILTER, "value": {"values": ["N"]}}],
        ),
        operator=CombineOp.UNION,
        offset=500,
    )
    stored.root.expanded_strategy_id = 9001
    stored.root.expanded_name = "Saved kinases"

    extracted = extracted_strategy(
        record_type="transcript",
        step_count=5,
        strategy_ast=stored.model_dump(by_alias=True, mode="json"),
    )

    assert extracted is not None
    kept = StrategyAst.model_validate(extracted.strategy_ast)
    assert [settings_of(node) for node in walk(kept.root)] == [
        settings_of(node) for node in walk(stored.root)
    ]


def _weighted_before_a_search() -> OperationalSpec:
    return OperationalSpec(
        goal="kinases",
        criteria=[Criterion(id="c_k", text="kinases", role="seed", weight=10)],
    )


def test_the_pinned_plan_names_a_weight_stated_before_a_search() -> None:
    ctx = lead_run_context()
    ctx.deps.state.domain.operational_spec = _weighted_before_a_search()

    lines = (pinned_operational_spec(ctx) or "").splitlines()

    assert next(line for line in lines if "[c_k]" in line).endswith("| weight 10")


def test_the_ledger_names_a_weight_stated_before_a_search() -> None:
    rendered = render_frame_full(FrameSection(spec=_weighted_before_a_search()))

    assert "    SETTINGS weight 10" in rendered.splitlines()


def test_a_rewire_beside_an_edit_names_both() -> None:
    answered = _tree(
        leaf_a=_leaf("step_a", "kinase"), operator=CombineOp.MINUS, offset=0
    )
    edited = _leaf("step_a", "kinase").model_copy(
        update={"parameters": {"text_expression": StringValue(value="kinases")}}
    )
    swapped = answered.model_copy(
        update={
            "root": answered.root.model_copy(
                update={
                    "primary_input": answered.root.secondary_input,
                    "secondary_input": edited,
                }
            )
        }
    )

    briefing = compose_turn_briefing(
        ThreadActivity(), requirements=[], answered=answered, live=swapped
    )

    assert briefing.render().splitlines()[1:-1] == [
        '- kinase (step_a): text_expression "kinase" -> "kinases"',
        "- the combinations changed",
    ]
