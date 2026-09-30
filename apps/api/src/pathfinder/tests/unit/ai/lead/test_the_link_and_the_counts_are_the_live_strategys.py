"""The facts link, the counts a check compares and the counts an edit moved
are the live strategy's.

The first cases replay a delete or a value-only edit whose recorded build names
a step the strategy no longer roots on, or carries no link at all.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import delete_step
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.lead.verify_dispatch import root_sample, work_order
from pathfinder.domain.caveats import EditDirection
from pathfinder.domain.strategy.build_outcome import BuildOutcome, built_counts
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import commit, live_counts, step_wdk_push, sync
from pathfinder.services.strategies.commit import live_strategy_url
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    session_with,
)

_ROOT = "step_4f8f1008"
_STRATEGY = 330847483
_LIVE_ROOT = 441096713
_DELETED_INTERSECT = 441096733


def _session(site_id: str, root: str, wdk_root: int, count: int) -> StrategySession:
    graph = StrategyGraph(graph_id="g1", name="TM genes", site_id=site_id)
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id=root, search_name="GenesByTransmembraneDomains")
    )
    graph.recompute_roots()
    session = StrategySession(site_id=site_id)
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={root: wdk_root},
        step_counts={root: count},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=wdk_root),
    )
    return session


def _spec(root: str) -> OperationalSpec:
    return OperationalSpec(
        goal="genes with at least two transmembrane domains",
        criteria=[
            Criterion(
                id=root,
                text="at least two predicted transmembrane domains",
                search_name="GenesByTransmembraneDomains",
                search_display_name="Transmembrane Domain Count",
                resolved_params=bound({"min_tm": StringValue(value="2")}),
            )
        ],
    )


def _after_the_delete() -> StrategySession:
    return _session("cryptodb", _ROOT, _LIVE_ROOT, 483)


def _deps_after_the_delete() -> LeadDeps:
    state = pipeline_state(
        "cryptodb", domain=StrategyDomainState(operational_spec=_spec(_ROOT))
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=[_ROOT],
        wdk_strategy_id=_STRATEGY,
    )
    return lead_deps(state, strategy_session=_after_the_delete())


def test_after_a_delete_the_link_names_the_root_the_strategy_holds() -> None:
    facts = turn_facts(_deps_after_the_delete())

    assert facts.strategy_url == (
        f"https://cryptodb.org/cryptodb/app/workspace/strategies/{_STRATEGY}/{_LIVE_ROOT}"
    )
    assert facts.root_count == 483


def test_after_a_value_only_edit_the_link_is_still_shown() -> None:
    step = "step_a556a9eb"
    state = pipeline_state(
        "piroplasmadb", domain=StrategyDomainState(operational_spec=_spec(step))
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=[step], wdk_strategy_id=_STRATEGY
    )
    deps = lead_deps(state, strategy_session=_session("piroplasmadb", step, 902, 5))

    assert turn_facts(deps).strategy_url == (
        f"https://piroplasmadb.org/piro/app/workspace/strategies/{_STRATEGY}/902"
    )


def test_the_work_order_after_a_delete_names_the_live_root_count() -> None:
    root = root_sample(_deps_after_the_delete())

    assert root is not None
    assert (root.wdk_step_id, root.count) == (_LIVE_ROOT, 483)
    assert "step 441096713 on the site, 483 records" in work_order("check", None, root)


def _loosened(direction: EditDirection) -> LeadDeps:
    step = "step_ae885aac"
    state = pipeline_state(
        "toxodb", domain=StrategyDomainState(operational_spec=_spec(step))
    )
    state.turn_markers.record_arrival(step, {step: 1535})
    state.turn_markers.edited = True
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="loosen the cut to 1.5-fold",
        edit_direction=direction,
    )
    session = _session("toxodb", step, 441096800, 1249)
    return lead_deps(state, intent=intent, strategy_session=session)


def test_a_loosen_whose_count_fell_shows_both_counts() -> None:
    facts = turn_facts(_loosened("loosen"))

    assert [c.sentence for c in facts.caveats if c.kind == "edit_direction"] == [
        (
            "'Transmembrane Domain Count' was edited to loosen it, and its count "
            "fell from 1,535 genes to 1,249 genes"
        )
    ]


def test_an_edit_with_no_direction_shows_no_such_caveat() -> None:
    facts = turn_facts(_loosened("other"))

    assert [c for c in facts.caveats if c.kind == "edit_direction"] == []


def test_a_log2_parameter_shows_its_fold_beside_the_value() -> None:
    step = "step_eda"
    spec = OperationalSpec(
        goal="bradyzoite over tachyzoite",
        criteria=[
            Criterion(
                id=step,
                text="1.5-fold up in bradyzoites",
                search_name="GenesByTransmembraneDomains",
                resolved_params=bound({"effect_size": StringValue(value="1.5")}),
                param_display_names={"effect_size": "log2(Fold Change)"},
            )
        ],
    )
    state = pipeline_state("toxodb", domain=StrategyDomainState(operational_spec=spec))
    deps = lead_deps(state, strategy_session=_session("toxodb", step, 5, 1249))

    [row] = turn_facts(deps).steps[0].parameters

    assert (row.lines(), row.notes) == (["log2(Fold Change): 1.5 (2.83-fold)"], [])


_INTERSECT = "step_c07f210b"
_OTHER = "step_sp"


class _SiteAfterTheDelete(StubAPI):
    """The site holds the transmembrane step alone, at 483 genes."""

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": strategy_id,
                "name": "TM genes",
                "rootStepId": _LIVE_ROOT,
                "stepTree": {"stepId": _LIVE_ROOT},
                "steps": {
                    str(_LIVE_ROOT): {
                        "id": _LIVE_ROOT,
                        "searchName": "GenesByTransmembraneDomains",
                        "searchConfig": {"parameters": {}},
                        "estimatedSize": 483,
                    }
                },
            }
        )


async def _sync_on_the_live_root(
    *, sync_state: WDKSyncState, **_kwargs: object
) -> SyncResult:
    sync_state.wdk_step_tree = WDKStepTree(step_id=_LIVE_ROOT)
    return SyncResult(
        wdk_strategy_id=_STRATEGY,
        wdk_url=None,
        root_step_id=_LIVE_ROOT,
        counts={},
        root_count=None,
        zero_step_ids=[],
        step_count=1,
    )


async def test_after_a_delete_the_ledger_counts_are_the_live_strategys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    api = _SiteAfterTheDelete()
    for module in (commit, step_wdk_push, sync, live_counts):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(commit, "sync_strategy_for_site", _sync_on_the_live_root)
    session = session_with(
        combine(
            _INTERSECT,
            StrategyStepNode(id=_ROOT, search_name="GenesByTransmembraneDomains"),
            StrategyStepNode(id=_OTHER, search_name="GenesWithSignalPeptide"),
        ),
        {_INTERSECT: _DELETED_INTERSECT, _ROOT: _LIVE_ROOT, _OTHER: 441096720},
    )
    ensure_sync_state(session).wdk_strategy_id = _STRATEGY
    ctx = lead_run_context(strategy_session=session, tool_call_id="call_delete")
    ctx.deps.state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=[_INTERSECT, _ROOT, _OTHER],
        wdk_strategy_id=_STRATEGY,
    )

    await delete_step(ctx, step_id=_INTERSECT, reply="The intersection goes.")

    build = derive_ledger(ctx.deps.state, None).build
    counts = built_counts(session.graph, session.sync_state)
    link = live_strategy_url("plasmodb", session.sync_state)
    assert (counts.root_count, link) == (
        483,
        (
            "https://plasmodb.org/plasmo/app/workspace/strategies/"
            f"{_STRATEGY}/{_LIVE_ROOT}"
        ),
    )
    assert [(n.node_id, counts.of(n.node_id)) for n in build.node_results] == [
        (_ROOT, 483)
    ]
