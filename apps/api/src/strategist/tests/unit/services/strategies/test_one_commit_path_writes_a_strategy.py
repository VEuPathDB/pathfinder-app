from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    ColocationParams,
    CombineOp,
    StepFilter,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    walk,
)
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.operations import (
    GraphOperation,
    ReplaceStrategyOp,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.validate import ValidationResult, validate_strategy
from strategist.services.eval import build_gold_strategy
from strategist.services.strategies import (
    commit_tree,
    organism_params,
    spec_build,
    stated_sides,
)
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.materialize import materialize_strategy_snapshot
from strategist.services.strategies.save_substrategy import save_subtree_as_strategy
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests._support.held_steps import (
    BOOLEAN_SEARCH,
    LEAF_DEFAULT,
    SPAN_SEARCH,
    default_filters,
)
from strategist.tests._support.holding_wdk import (
    HoldingWDK,
    serve_the_holding_wdk,
)
from strategist.tests._support.record_classes import list_every_search_under

_SITE = "plasmodb"
_SORTED = [{"name": "wdk_weight", "direction": "DESC"}]
_FILTER = "matched_transcript_filter_array"
_COLOC = ColocationParams(
    operation="contains", strand="same strand", begin_offset_a=500
)
_NEW_COLOC = ColocationParams(
    operation="overlaps", strand="opposite strand", begin_offset_a=2000
)
FIELDS = [
    "weight_leaf",
    "weight_combine",
    "sort_root",
    "filter_added",
    "filter_removed",
    "operator",
    "colocation",
    "expansion",
    "custom_name",
    "validate_strategy",
    "default_filter_kept",
    "filter_only_patch",
]


def _text(step_id: str, text: str, name: str, **fields: Any) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByTextSearch",
        display_name=name,
        parameters={"text_expression": StringValue(value=text)},
        **fields,
    )


def _filter(*values: str) -> list[StepFilter]:
    return [StepFilter(name=_FILTER, value={"values": list(values)})]


def plan_root(
    *,
    a_weight: int = 10,
    a_filter: tuple[str, ...] = ("N",),
    coloc: ColocationParams = _COLOC,
) -> StrategyStepNode:
    union = StrategyStepNode(
        id="step_union",
        search_name="__combine__",
        display_name="Kinase or rhoptry",
        operator=CombineOp.UNION,
        wdk_weight=7,
        primary_input=_text(
            "step_a",
            "kinase",
            "Kinase text",
            wdk_weight=a_weight,
            filters=_filter(*a_filter),
        ),
        secondary_input=_text("step_b", "rhoptry", "Rhoptry text", wdk_weight=5),
    )
    coloc_node = StrategyStepNode(
        id="step_coloc",
        search_name="__combine__",
        display_name="Contains membrane genes",
        operator=CombineOp.COLOCATE,
        colocation_params=coloc,
        wdk_weight=4,
        primary_input=union,
        secondary_input=_text("step_c", "membrane", "Membrane text"),
    )
    return StrategyStepNode(
        id="step_root",
        search_name="__combine__",
        display_name="In saved kinases",
        operator=CombineOp.INTERSECT,
        expanded_strategy_id=9001,
        expanded_name="Saved kinases",
        primary_input=coloc_node,
        secondary_input=_text("step_d", "protein kinase", "Saved kinases root"),
    )


def _unfiltered(root: StrategyStepNode) -> StrategyStepNode:
    root = root.model_copy(deep=True)
    node_of(root, "step_a").filters = []
    return root


def node_of(root: StrategyStepNode, step_id: str) -> StrategyStepNode:
    return next(n for n in walk(root) if n.id == step_id)


class Env:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.wdk = HoldingWDK()
        self.validate_calls = 0
        self.lost: list[str] = []
        serve_the_holding_wdk(monkeypatch, self.wdk)

        async def _echo(*_a: object, **kw: Any) -> ValidatedParams:
            params: dict[str, ParamValue] = {**kw["context"], **kw["stated"]}
            return ValidatedParams(params=params, record_class="transcript")

        for module in (stated_sides, commit_tree):
            monkeypatch.setattr(module, "validate_parameters", _echo)
            monkeypatch.setattr(module, "make_validation_callbacks", lambda _s: None)
        list_every_search_under(monkeypatch, "transcript")

        async def _no_marks(*_a: object, **_k: object) -> dict[str, str]:
            return {}

        async def _no_organisms(*_a: object, **_k: object) -> None:
            return None

        async def _no_kinds(**_k: object) -> None:
            return None

        monkeypatch.setattr(spec_build, "read_the_unread_kinds", _no_kinds)
        monkeypatch.setattr(organism_params, "organism_parameters", _no_marks)
        monkeypatch.setattr(organism_params, "step_dataset_organisms", _no_organisms)
        real = validate_strategy

        def _spy(*a: Any, **kw: Any) -> ValidationResult:
            self.validate_calls += 1
            return real(*a, **kw)

        monkeypatch.setattr(
            "strategist.services.strategies._tree_write.validate_strategy", _spy
        )

    def held_pairs(
        self, strategy_id: int | None, plan: StrategyStepNode
    ) -> list[tuple[StrategyStepNode, dict[str, Any]]]:
        assert strategy_id is not None
        return _pairs(self.wdk, self.wdk.strategies[strategy_id]["stepTree"], plan)

    def keeps_the_defaults(
        self, strategy_id: int | None, plan: StrategyStepNode
    ) -> None:
        declared = {n.id: {f.name for f in n.filters} for n in walk(plan_root())}
        for node, held in self.held_pairs(strategy_id, plan):
            got = _by_name(held["searchConfig"]["filters"])
            for d in default_filters(
                held["searchName"], held["searchConfig"]["parameters"]
            ):
                if d["name"] not in declared[node.id] and got.get(d["name"]) != [
                    d["value"],
                    False,
                ]:
                    self.lost.append(f"{node.id}: {d['name']}")


def _pairs(
    wdk: HoldingWDK, tree: dict[str, Any], node: StrategyStepNode
) -> list[tuple[StrategyStepNode, dict[str, Any]]]:
    out = [(node, wdk.steps[tree["stepId"]])]
    for slot, sub in (
        ("primaryInput", node.primary_input),
        ("secondaryInput", node.secondary_input),
    ):
        assert (sub is None) == (tree.get(slot) is None)
        if sub is not None:
            out.extend(_pairs(wdk, tree[slot], sub))
    return out


def _by_name(filters: list[dict[str, Any]]) -> dict[str, Any]:
    return {f["name"]: [f.get("value"), bool(f.get("disabled"))] for f in filters}


def filters_as_planned(
    env: Env, strategy_id: int | None, plan: StrategyStepNode
) -> bool:
    a_node, a_held = next(
        (n, h) for n, h in env.held_pairs(strategy_id, plan) if n.id == "step_a"
    )
    defaults = default_filters(
        a_held["searchName"], a_held["searchConfig"]["parameters"]
    )
    declared = [f.model_dump(by_alias=True, mode="json") for f in a_node.filters]
    want = {**_by_name(defaults), **_by_name(declared)}
    return _by_name(a_held["searchConfig"]["filters"]) == want


def cells(env: Env, strategy_id: int | None, plan: StrategyStepNode) -> dict[str, bool]:
    pairs = env.held_pairs(strategy_id, plan)
    leaves = [(n, h) for n, h in pairs if n.infer_kind() != "combine"]
    booleans = [
        (n, h)
        for n, h in pairs
        if n.infer_kind() == "combine" and n.operator is not CombineOp.COLOCATE
    ]
    root_node, root_held = pairs[0]
    coloc_node, coloc_held = next((n, h) for n, h in pairs if n.id == "step_coloc")
    assert coloc_node.colocation_params is not None
    span = coloc_held["searchConfig"]["parameters"]
    return {
        "weight_leaf": all(
            h["searchConfig"]["wdkWeight"] == (n.wdk_weight or 0) for n, h in leaves
        ),
        "weight_combine": all(
            h["searchConfig"]["wdkWeight"] == (n.wdk_weight or 0)
            for n, h in pairs
            if n.infer_kind() == "combine"
        ),
        "sort_root": root_held["displayPreferences"].get("sortColumns") == _SORTED,
        "filter_added": filters_as_planned(env, strategy_id, plan),
        "operator": coloc_held["searchName"] == SPAN_SEARCH
        and all(
            h["searchName"] == BOOLEAN_SEARCH
            and n.operator is not None
            and h["searchConfig"]["parameters"]["bq_operator"] == n.operator.value
            for n, h in booleans
        ),
        "colocation": all(
            span.get(k) == v
            for k, v in coloc_node.colocation_params.to_wdk_params().items()
        ),
        "expansion": (root_held["expanded"], root_held["expandedName"])
        == (True, root_node.expanded_name),
        "custom_name": all(h["customName"] == n.display_name for n, h in pairs),
    }


def new_thread() -> StrategyMutationContext:
    session = StrategySession(site_id=_SITE)
    graph = StrategyGraph(
        graph_id="g1", name="Kinases near membrane genes", site_id=_SITE
    )
    graph.record_type = "transcript"
    session.graph = graph
    return StrategyMutationContext(
        site_id=_SITE, strategy_session=session, conversation_id=None
    )


def _strategy_id(deps: StrategyMutationContext) -> int | None:
    return ensure_sync_state(deps.strategy_session).wdk_strategy_id


async def commit_ops(deps: StrategyMutationContext, *ops: GraphOperation) -> int | None:
    await apply_operations_and_commit(deps=deps, ops=list(ops))
    return _strategy_id(deps)


def replace_with(root: StrategyStepNode) -> ReplaceStrategyOp:
    return ReplaceStrategyOp(root=root, name="Kinases near membrane genes")


def _replace_a(root: StrategyStepNode) -> ReplaceSubtreeOp:
    return ReplaceSubtreeOp(step_id="step_a", subtree=node_of(root, "step_a"))


def _patch_ops() -> list[GraphOperation]:
    return [
        _replace_a(plan_root(a_weight=3, a_filter=("Y", "N"))),
        UpdateCombineOperatorOp(
            step_id="step_coloc",
            operator=CombineOp.COLOCATE,
            colocation_params=_NEW_COLOC,
        ),
    ]


type Write = Callable[[StrategyStepNode], Awaitable[int | None]]


async def _row(env: Env, first: StrategyStepNode, write: Write) -> list[str]:
    calls = env.validate_calls
    strategy_id = await write(first)
    held = cells(env, strategy_id, first)
    held["validate_strategy"] = env.validate_calls > calls
    env.keeps_the_defaults(strategy_id, first)
    removed = _unfiltered(first)
    held["filter_removed"] = filters_as_planned(env, await write(removed), removed)
    refiltered = first.model_copy(deep=True)
    a = node_of(refiltered, "step_a")
    a.filters = _filter("Y", "N") if a.filters == _filter("N") else _filter("N")
    refiltered_id = await write(refiltered)
    held["filter_only_patch"] = filters_as_planned(env, refiltered_id, refiltered)
    env.keeps_the_defaults(refiltered_id, refiltered)
    held["default_filter_kept"] = env.lost == []
    return [field for field in FIELDS if held[field]]


async def test_p1_create_holds_every_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    first = True

    async def write(root: StrategyStepNode) -> int | None:
        nonlocal first
        op = replace_with(root) if first else _replace_a(root)
        first = False
        return await commit_ops(deps, op)

    assert await _row(env, plan_root(), write) == FIELDS


async def test_p1_patch_holds_every_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    patched = plan_root(a_weight=3, a_filter=("Y", "N"), coloc=_NEW_COLOC)
    first = True

    async def write(root: StrategyStepNode) -> int | None:
        nonlocal first
        ops = _patch_ops() if first else [_replace_a(root)]
        first = False
        return await commit_ops(deps, *ops)

    assert await _row(env, patched, write) == FIELDS


async def test_p2_build_holds_every_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)
    deps = new_thread()

    async def write(root: StrategyStepNode) -> int | None:
        await build_strategy_from_spec(deps=deps, root=root.model_copy(deep=True))
        return ensure_sync_state(deps.strategy_session).wdk_strategy_id

    assert await _row(env, plan_root(), write) == FIELDS


async def test_p3_save_subtree_holds_every_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)

    async def write(root: StrategyStepNode) -> int | None:
        session = StrategySession(site_id=_SITE)
        graph = StrategyGraph(graph_id="g1", name="Kinases", site_id=_SITE)
        graph.steps = flatten_tree(root)
        graph.recompute_roots()
        session.graph = graph
        saved = await save_subtree_as_strategy(
            session=session, site_id=_SITE, source_step_id=root.id, name="Saved"
        )
        return saved.wdk_strategy_id

    assert await _row(env, plan_root(), write) == FIELDS


async def test_p6_gold_holds_every_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)

    async def _no_genes(*_args: object) -> list[str]:
        return []

    monkeypatch.setattr("strategist.services.eval.fetch_all_gene_ids", _no_genes)

    async def write(root: StrategyStepNode) -> int | None:
        gold = await build_gold_strategy(
            gold_id="matrix",
            site_id=_SITE,
            step_tree=root.model_dump(by_alias=True, mode="json"),
        )
        return gold.wdk_strategy_id

    assert await _row(env, plan_root(), write) == FIELDS


async def test_p4_snapshot_holds_every_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    env = Env(monkeypatch)

    async def write(root: StrategyStepNode) -> int | None:
        ast = StrategyAst(record_type="transcript", root=root, name="Kinases")
        made = await materialize_strategy_snapshot(
            site_id=_SITE,
            conversation_id=uuid4(),
            name="Kinases",
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        return made.wdk_strategy_id

    assert await _row(env, plan_root(), write) == FIELDS


async def test_dropping_the_only_filter_puts_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    a_id = ensure_sync_state(deps.strategy_session).wdk_step_ids["step_a"]
    env.wdk.writes.clear()

    result = await apply_operations_and_commit(
        deps=deps, ops=[_replace_a(_unfiltered(plan_root()))]
    )

    puts = env.wdk.written("PUT", f"/steps/{a_id}/search-config")
    assert [w.body["filters"] for w in puts] == [[]]
    assert env.wdk.steps[a_id]["searchConfig"]["filters"] == [LEAF_DEFAULT]
    assert result.failures == []


async def test_a_filter_value_alone_is_one_put_and_no_tree_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    deps = new_thread()
    await commit_ops(deps, replace_with(plan_root()))
    env.wdk.writes.clear()

    await commit_ops(deps, _replace_a(plan_root(a_filter=("Y", "N"))))

    assert [(w.method, w.path.rsplit("/", 1)[-1]) for w in env.wdk.writes] == [
        ("PUT", "search-config")
    ]


async def test_a_weight_the_site_drops_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = Env(monkeypatch)
    env.wdk.drops_the_weight_on_create = True
    deps = new_thread()

    result = await apply_operations_and_commit(
        deps=deps, ops=[replace_with(plan_root())]
    )

    held = {f.step_id: f.error for f in result.failures}
    assert held["step_a"].endswith("holds wdk_weight None for this step, not 10")
    assert held["step_b"].endswith("holds wdk_weight None for this step, not 5")
