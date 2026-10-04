"""VERIFY is handed every message of the request and the root it samples, and
its review reaches the verdict and the card as the record lets it stand."""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKSearch, WDKStepTree

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import evidence_card, verify_dispatch
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verification_scope import verification_scope
from pathfinder.ai.lead.verify_dispatch import (
    RootSample,
    SearchStep,
    run_verification,
    work_order,
)
from pathfinder.domain.caveats import RequirementGap, SampleCaveat
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT
from pathfinder.domain.question_rows import ResearcherAsk
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import text_queries
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.column_fits import tm_fit
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
    requirement,
)

_ASKED = "P. falciparum 3D7 genes with a signal peptide"
_ADDED = "Also require at least 2 transmembrane domains."
_ROOT = 440299573
_STRATEGY = 300125410
_RECORD = "https://plasmodb.org/plasmo/app/record/gene/{}"

pytestmark = pytest.mark.usefixtures("collector")


def _deps(*, unexpressed: list[str] | None = None) -> LeadDeps:
    state = pipeline_state("plasmodb", user_prompt=_ADDED)
    state.domain.original_request = _ASKED
    state.domain.request_messages = [_ASKED]
    state.domain.requirements = [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum 3D7")
    ]
    state.domain.operational_spec = OperationalSpec(
        goal=_ASKED,
        criteria=[
            Criterion(
                id="s1",
                text="genes with a signal peptide",
                search_name="GenesWithSignalPeptide",
                unexpressed_qualifiers=list(unexpressed or []),
            )
        ],
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=_STRATEGY,
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesWithSignalPeptide",
                wdk_step_id=_ROOT,
                status="ok",
            )
        ],
    )
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Signal peptides", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id="s1", search_name="GenesWithSignalPeptide")
    )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"s1": _ROOT},
        step_counts={"s1": 5},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_ROOT),
    )
    return lead_deps(state, strategy_session=session)


def test_the_scope_numbers_every_message_of_the_request() -> None:
    scope = verification_scope(_deps(), check_id="call_verify")

    assert scope.messages == [_ASKED, _ADDED]
    assert scope.stated == [
        (
            "organism (organism): 'Plasmodium falciparum 3D7' -> grounded "
            "(from an earlier message); key organism:Plasmodium falciparum 3D7"
        )
    ]


def test_the_scope_lists_each_word_no_search_states() -> None:
    scope = verification_scope(_deps(unexpressed=["exported"]), check_id="call_v")

    assert scope.unexpressed == ["'exported' in [s1] genes with a signal peptide"]


def test_the_work_order_names_each_search_step_then_the_root_to_sample() -> None:
    root = RootSample(
        step_id="s3",
        wdk_step_id=_ROOT,
        count=5,
        search_steps=(
            SearchStep(step_id="s1", wdk_step_id=11),
            SearchStep(step_id="s2", wdk_step_id=12),
        ),
    )

    assert work_order("check it", None, root) == (
        "Verification work order: check it\n"
        "Inspect the built strategy. Return a VerificationDelta.\n"
        "Read the columns of each search step first: "
        "read_step_columns(wdk_step_id=11) for s1; "
        "read_step_columns(wdk_step_id=12) for s2.\n"
        f"The root is s3, step {_ROOT} on the site, 5 records. For a criterion "
        "whose step shows no column, sample it with "
        f"get_sample_records(wdk_step_id={_ROOT}, limit=5)."
    )


def test_the_dispatch_names_the_strategys_search_steps() -> None:
    root = verify_dispatch.root_sample(_deps())

    assert root is not None
    assert root.search_steps == (SearchStep(step_id="s1", wdk_step_id=_ROOT),)


def test_an_empty_root_is_not_sampled() -> None:
    order = work_order(
        "check it", None, RootSample(step_id="s1", wdk_step_id=_ROOT, count=0)
    )

    assert order.endswith(
        f"The root is s1, step {_ROOT} on the site, 0 records. "
        "It holds no gene to sample."
    )


def test_a_root_larger_than_the_sample_is_read_eight_records_deep() -> None:
    order = work_order(
        "check it", None, RootSample(step_id="s1", wdk_step_id=_ROOT, count=212)
    )

    assert order.endswith(f"get_sample_records(wdk_step_id={_ROOT}, limit=8).")


def _digest(review: dict[str, Any]) -> VerificationDelta:
    return VerificationDelta.model_validate(
        {
            "digest": {
                "disposition": "done",
                "prose": "The strategy returns 5 genes.",
                "reason": "Counts and records read.",
                "success": True,
                "review": review,
            }
        }
    )


class _Dispatch:
    """Stands in for the VERIFY run and the site's count read."""

    def __init__(self, outcome: VerificationDelta) -> None:
        self.outcome = outcome
        self.agent_deps: AgentDeps | None = None
        self.work_order = ""

    async def streamed(self, **kwargs: Any) -> VerificationDelta:
        self.agent_deps = kwargs["agent_deps"]
        self.work_order = kwargs["run"].work_order
        return self.outcome


async def _run(
    monkeypatch: pytest.MonkeyPatch, deps: LeadDeps, review: dict[str, Any]
) -> tuple[VerificationDelta, _Dispatch]:
    dispatch = _Dispatch(_digest(review))

    async def counts(site_id: str, wdk_strategy_id: int) -> SiteCounts:
        del site_id, wdk_strategy_id
        return SiteCounts(root_step_id=_ROOT, counts={_ROOT: 5})

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", dispatch.streamed)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    delta = await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the genes"
    )
    assert isinstance(delta, VerificationDelta)
    return delta, dispatch


_UNMET = {
    "text": "at least 2 transmembrane domains",
    "turn": 2,
    "answeredBy": [],
    "how": "search",
    "status": "unmet",
    "note": "no step reads transmembrane domains",
}


async def test_an_unmet_requirement_refuses_the_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps()
    deps.state.domain.requirements.append(
        requirement(
            ConstraintKind.OTHER,
            "transmembrane domains",
            "at least 2 transmembrane domains",
        )
    )
    delta, _dispatch = await _run(monkeypatch, deps, {"requirements": [_UNMET]})

    assert (delta.digest.success, delta.digest.gaps) == (
        False,
        [RequirementGap(text="at least 2 transmembrane domains", status="unmet")],
    )


def _gene(gene_id: str, fits: str) -> dict[str, str]:
    return {
        "geneId": gene_id,
        "product": "erythrocyte membrane protein",
        "organism": "Plasmodium falciparum 3D7",
        "fits": fits,
        "why": "the product names a membrane protein",
    }


async def test_the_columns_this_turn_read_are_the_cards_and_the_caveats(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    deps = _deps()
    short = tm_fit(3, 5, wdk_step_id=_ROOT)
    deps.state.turn_markers.record_column_fits(
        [short, tm_fit(9, 9, wdk_step_id=_ROOT + 1)]
    )
    for gene_id in ("PF3D7_0100100", "PF3D7_0100200"):
        deps.state.turn_markers.record_retrieved_source(_RECORD.format(gene_id))

    delta, _dispatch = await _run(
        monkeypatch,
        deps,
        {
            "sampledGenes": [
                _gene("PF3D7_0100100", "yes"),
                _gene("PF3D7_0100200", "no"),
                _gene("PF3D7_0100300", "yes"),
            ]
        },
    )

    assert delta.digest.caveats == [SampleCaveat(fit=short)]
    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert (
        card.review.column_fits,
        [gene.gene_id for gene in card.review.sampled_genes],
    ) == ([short], ["PF3D7_0100100", "PF3D7_0100200"])
    streamed = collector.data_of("data-evidence-card")[0]["review"]
    assert (streamed["columnFits"][0]["fits"], streamed["sampledGenes"][1]["fits"]) == (
        "some",
        "no",
    )


async def test_the_checks_guard_leaves_record_reads_to_the_reading_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _delta, dispatch = await _run(monkeypatch, _deps(), {})

    assert dispatch.agent_deps is not None
    guard: ToolRepetitionGuard = dispatch.agent_deps.tool_repetition_guard
    reads = [
        guard.check("read_gene_record", {"gene_id": f"PF3D7_{i:07d}"}, run_step=i + 1)
        for i in range(SAMPLED_GENE_LIMIT + 1)
    ]

    assert reads == [None] * (SAMPLED_GENE_LIMIT + 1)
    assert dispatch.work_order.endswith(
        f"get_sample_records(wdk_step_id={_ROOT}, limit=5)."
    )


def _string_search(search_name: str, param: str, initial: str) -> WDKSearch:
    return WDKSearch.model_validate(
        {
            "urlSegment": search_name,
            "displayName": search_name,
            "shortDisplayName": search_name,
            "parameters": [
                {
                    "name": param,
                    "displayName": param,
                    "type": "string",
                    "isVisible": True,
                    "initialDisplayValue": initial,
                }
            ],
        }
    )


_SHEETS = {
    "GenesByGoTerm": _string_search("GenesByGoTerm", "go_term", "N/A"),
    "GenesByText": _string_search("GenesByText", "text_expression", ""),
}
_COMPARE = "Also search trans-sialidase and tell me how the two counts compare."


def _met(text: str, criterion: str, turn: int = 1) -> dict[str, Any]:
    return {
        "text": text,
        "turn": turn,
        "answeredBy": [criterion],
        "how": "parameter",
        "status": "met",
        "note": "the step binds it",
    }


async def test_only_a_text_query_is_held_to_the_records_and_an_ask_files_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def record_type(_site: str, _search: str, given: str | None) -> str:
        return given or "transcript"

    async def definition(_site: str, _record_type: str, search: str) -> WDKSearch:
        return _SHEETS[search]

    monkeypatch.setattr(text_queries, "resolve_search_record_type", record_type)
    monkeypatch.setattr(text_queries, "read_search_definition", definition)
    deps = _deps()
    deps.state.user_prompt = _COMPARE
    deps.state.domain.researcher_asks = [
        ResearcherAsk(message=_COMPARE, text="tell me how the two counts compare")
    ]
    deps.state.domain.operational_spec = OperationalSpec(
        goal=_ASKED,
        criteria=[
            Criterion(
                id="c_go",
                text="protein kinase activity",
                search_name="GenesByGoTerm",
                resolved_params=bound(
                    {
                        "go_typeahead": MultiPickValue(values=["GO:0004672"]),
                        "go_term": StringValue(value="N/A"),
                    },
                    defaulted=("go_term",),
                ),
            ),
            Criterion(
                id="c_text",
                text="trans-sialidase",
                search_name="GenesByText",
                resolved_params=bound(
                    {"text_expression": StringValue(value="trans-sialidase")}
                ),
            ),
        ],
    )

    deps.state.turn_markers.record_retrieved_source(_RECORD.format("PF3D7_0100200"))

    delta, _dispatch = await _run(
        monkeypatch,
        deps,
        {
            "requirements": [
                _met("protein kinase activity", "c_go"),
                _met("trans-sialidase", "c_text", turn=2),
                _met("tell me how the two counts compare", "c_text", turn=2),
            ],
            "sampledGenes": [
                {
                    **_gene("PF3D7_0100200", "no"),
                    "why": "the product names no trans-sialidase",
                }
            ],
        },
    )

    assert [
        (row.text, row.shown_status) for row in delta.digest.review.requirements
    ] == [
        ("protein kinase activity", "met"),
        ("trans-sialidase", "unshown"),
    ]


def test_the_scope_lists_each_count_the_edit_moved() -> None:
    deps = _deps()
    deps.state.turn_markers.record_arrival("s1", {"s1": 823})
    deps.state.turn_markers.edited = True
    session = deps.runtime.strategy_session
    assert session.sync_state is not None
    session.sync_state.step_counts["s1"] = 410

    scope = verification_scope(deps, check_id="call_verify")

    assert scope.before == [
        "[s1] GenesWithSignalPeptide: 823 before this turn's edit, 410 now"
    ]


def test_a_turn_that_wrote_nothing_lists_no_count_before() -> None:
    deps = _deps()
    deps.state.turn_markers.record_arrival("s1", {"s1": 823})

    assert verification_scope(deps, check_id="call_verify").before == []
