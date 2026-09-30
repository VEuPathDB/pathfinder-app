"""A fact is anything the thread showed or this turn read: every facts part the
thread wrote, each count before and after an edit, every record a tool of the
turn returned and every gene the gate resolved. The reply may hold any of them."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb_mcp.gene_lookup import GeneResolveResult, GeneResult

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.ai.lead import classification_gate
from pathfinder.ai.lead.contract_messages import fact_outside_the_block_message
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.evidence import SampledGene, VerificationReview
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.turn_facts import SourceFact
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _session(
    root: StrategyStepNode,
    counts: dict[str, int],
    wdk_ids: dict[str, int] | None = None,
    site_id: str = "plasmodb",
) -> StrategySession:
    graph = StrategyGraph(graph_id="g1", name="strategy", site_id=site_id)
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session = StrategySession(site_id=site_id)
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts=dict(counts), wdk_step_ids=dict(wdk_ids or {})
    )
    return session


def _deps(
    session: StrategySession,
    *,
    shown: list[str] | None = None,
    site_id: str = "plasmodb",
) -> LeadDeps:
    state = pipeline_state(
        site_id,
        user_message_id=uuid4(),
        domain=StrategyDomainState(facts_shown=list(shown or [])),
    )
    return lead_deps(state, strategy_session=session)


def _printed(deps: LeadDeps, prose: str) -> list[str]:
    record = turn_record(run_context_for(deps))
    return [
        m.sentence
        for m in reconcile(reply(prose), record)
        if m.kind == "fact_outside_the_block"
    ]


# The portal narrowing: the text search held 2,160 genes, then 19 at 3D7.
def _portal_after_the_narrowing() -> LeadDeps:
    step = StrategyStepNode(id="c_text", search_name="GenesByText")
    deps = _deps(_session(step, {"c_text": 19}), site_id="veupathdb")
    markers = deps.state.turn_markers
    markers.record_arrival("c_text", {"c_text": 2160})
    markers.edited = True
    return deps


def test_the_narrowed_step_and_the_result_show_their_counts_before_the_edit() -> None:
    facts = turn_facts(_portal_after_the_narrowing())

    assert [(s.count, s.count_before) for s in facts.steps] == [(19, 2160)]
    assert (facts.root_count, facts.root_count_before) == (19, 2160)


def test_the_count_before_an_earlier_turn_s_edit_may_be_restated() -> None:
    """Turn 4 asks the count before turn 2's narrowing, which turn 1 showed."""
    session = _session(StrategyStepNode(id="c_text", search_name="GenesByText"), {})
    session.sync_state = WDKSyncState(step_counts={"c_text": 19})
    deps = _deps(
        session,
        shown=["GenesByText: 2,160 genes", "Result: 2,160 genes"],
        site_id="veupathdb",
    )

    assert _printed(deps, "Before the organism narrowing it was 2,160 genes.") == []
    assert _printed(deps, "Before the organism narrowing it was 2,161 genes.") == [
        fact_outside_the_block_message(["2,161"])
    ]


# The percentile tighten: the percentile step 1,014 -> 260, the root 209 -> 38.
def _tightened() -> LeadDeps:
    root = StrategyStepNode(
        id="step_root",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(id="c_tm", search_name="GenesByTMDomains"),
        secondary_input=StrategyStepNode(
            id="c_pct", search_name="GenesByRNASeqPercentile"
        ),
    )
    session = _session(root, {"c_tm": 1305, "c_pct": 260, "step_root": 38})
    deps = _deps(session, shown=["Result: 209 genes"])
    markers = deps.state.turn_markers
    markers.record_arrival("step_root", {"c_tm": 1305, "c_pct": 1014, "step_root": 209})
    markers.edited = True
    return deps


def test_the_tightened_step_and_the_root_show_both_counts() -> None:
    facts = turn_facts(_tightened())

    assert [(s.step_id, s.count, s.count_before) for s in facts.steps] == [
        ("c_tm", 1305, None),
        ("c_pct", 260, 1014),
        ("step_root", 38, 209),
    ]
    assert "Result: 38 genes, 209 genes before this turn's edit" in facts.lines()


# The Hammondia microneme search held 23 genes when the message arrived. The turn
# added the ME49 search, bound it twice, and joined the two by orthology.
def _joined_by_orthology() -> LeadDeps:
    root = StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(id="step_hha", search_name="GenesByText"),
        secondary_input=StrategyStepNode(
            id="step_orth",
            search_name="GenesByOrthologs",
            primary_input=StrategyStepNode(id="c_me49", search_name="GenesByText"),
        ),
    )
    session = _session(
        root, {"step_hha": 23, "c_me49": 25, "step_orth": 47, "step_join": 19}
    )
    deps = _deps(session, site_id="toxodb")
    markers = deps.state.turn_markers
    markers.record_arrival("step_hha", {"step_hha": 23})
    markers.built = True
    return deps


def test_a_step_the_turn_created_or_left_unchanged_shows_no_count_before() -> None:
    facts = turn_facts(_joined_by_orthology())

    assert [(s.step_id, s.count, s.count_before) for s in facts.steps] == [
        ("step_hha", 23, None),
        ("c_me49", 25, None),
        ("step_orth", 47, None),
        ("step_join", 19, None),
    ]
    assert "Result: 19 genes, 23 genes before this turn's edit" in facts.lines()


def test_the_strategy_at_arrival_is_kept_once_per_message() -> None:
    deps = _joined_by_orthology()
    markers = deps.state.turn_markers
    markers.record_arrival("c_me49", {"c_me49": 6123})

    assert turn_facts(deps).root_count_before == 23


def test_a_turn_that_wrote_nothing_shows_no_count_before() -> None:
    deps = _tightened()
    deps.state.turn_markers.edited = False

    facts = turn_facts(deps)
    assert (facts.root_count_before, [s.count_before for s in facts.steps]) == (
        None,
        [None, None, None],
    )


def test_a_reply_may_say_how_the_count_moved_but_not_a_number_no_count_gives() -> None:
    deps = _tightened()

    assert _printed(deps, "It fell from 209 to 38, a decrease of 171.") == []
    assert _printed(deps, "It fell from 209 to 38, a decrease of 172.") == [
        fact_outside_the_block_message(["172"])
    ]


# A leaf of 627 genes under a result of 9, and one record read from the leaf.
_LEAF_WDK = 441125223
_TOXO_RECORD = "https://toxodb.org/toxo/app/record/gene/TGME49_200010"


def _leaf_read() -> LeadDeps:
    root = StrategyStepNode(
        id="step_root",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.MINUS,
        primary_input=StrategyStepNode(
            id="step_d2536be6", search_name="GenesWithSignalPeptide"
        ),
        secondary_input=StrategyStepNode(
            id="step_ortho", search_name="GenesByOrthologPattern"
        ),
    )
    session = _session(
        root,
        {"step_d2536be6": 627, "step_ortho": 4102, "step_root": 9},
        {"step_d2536be6": _LEAF_WDK, "step_ortho": 441125224, "step_root": 441125225},
        site_id="toxodb",
    )
    deps = _deps(session, site_id="toxodb")
    markers = deps.state.turn_markers
    markers.record_listed_genes(_LEAF_WDK, ["TGME49_200010"])
    markers.record_read(
        ReadRecord(
            record_id="TGME49_200010",
            url=_TOXO_RECORD,
            product="hypothetical protein",
            organism="Toxoplasma gondii ME49",
        )
    )
    deps.state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="sampled",
            success=True,
            review=VerificationReview(
                sampled_genes=[
                    SampledGene(
                        gene_id="TGME49_200010",
                        product="hypothetical protein",
                        fits="unclear",
                        why="The record states no signal peptide evidence.",
                    )
                ]
            ),
        ),
        revision=strategy_revision(None),
    )
    return deps


def test_a_leaf_s_record_is_a_source_of_the_leaf_with_its_fit() -> None:
    facts = turn_facts(_leaf_read())

    assert facts.sources == [
        SourceFact(
            url=_TOXO_RECORD,
            record_id="TGME49_200010",
            product="hypothetical protein",
            organism="Toxoplasma gondii ME49",
            step_id="step_d2536be6",
            step_name=facts.steps[0].display_name,
            fit="unclear",
            why="The record states no signal peptide evidence.",
        )
    ]
    lines = facts.lines()
    source = next(k for k, line in enumerate(lines) if _TOXO_RECORD in line)
    assert source == 1
    assert lines.index("Result: 9 genes") > source


def test_a_record_read_under_a_step_the_strategy_replaced_is_no_source() -> None:
    first = _leaf_read()
    replacement = StrategyStepNode(id="step_b", search_name="GenesByTaxon")
    second = lead_deps(
        first.state,
        strategy_session=_session(
            replacement, {"step_b": 8210}, {"step_b": 441125300}, site_id="toxodb"
        ),
    )

    assert [s.step_id for s in turn_facts(first).sources] == ["step_d2536be6"]
    facts = turn_facts(second)
    assert (facts.sources, [line for line in facts.lines() if "TGME49" in line]) == (
        [],
        [],
    )


def test_a_value_a_record_read_returned_is_a_fact_of_the_turn() -> None:
    deps = _leaf_read()
    deps.state.turn_markers.record_read(
        ReadRecord(
            record_id="AFUN020124",
            url="https://vectorbase.org/vectorbase/app/record/gene/AFUN020124",
            product="insulin receptor",
            organism="Anopheles funestus FUMOZ",
            asked_orthologs=["AGAP009262", "Anopheles gambiae PEST"],
        )
    )

    assert _printed(deps, "AFUN020124 lists AGAP009262 as its PEST ortholog.") == []
    assert _printed(deps, "AFUN020124 lists AGAP000001 as its PEST ortholog.") == [
        fact_outside_the_block_message(["AGAP000001"])
    ]


# The genes the attached table of the plasmodb flow shows, as the site names them.
_IMAGE_GENES = [
    GeneResult(
        gene_id="PF3D7_0709000",
        product="chloroquine resistance transporter",
        organism="P. falciparum 3D7",
    ),
    GeneResult(
        gene_id="PF3D7_1133400",
        product="apical membrane antigen 1",
        organism="P. falciparum 3D7",
    ),
    GeneResult(
        gene_id="PF3D7_0102600",
        product="serine/threonine protein kinase, FIKK family",
        organism="P. falciparum 3D7",
    ),
]
_IMAGE_REPLY = (
    "The image contains these genes:\n\n"
    "- **PF3D7_0709000** - chloroquine resistance transporter\n"
    "- **PF3D7_1133400** - apical membrane antigen 1\n"
    "- **PF3D7_0102600** - a FIKK family kinase"
)


async def test_the_genes_the_gate_resolved_are_facts_the_reply_may_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _resolve(site_id: str, gene_ids: list[str]) -> GeneResolveResult:
        del site_id
        found = [g for g in _IMAGE_GENES if g.gene_id in gene_ids]
        return GeneResolveResult(records=found, total_count=len(found))

    monkeypatch.setattr(classification_gate, "resolve_gene_ids", _resolve)
    state = pipeline_state(
        "plasmodb",
        user_prompt="Which genes are in this image?",
        user_message_id=uuid4(),
    )
    state.user_parts = [
        FileUIPart(media_type="image/png", url="data:image/png;base64,AA=="),
        TextUIPart(text=state.user_prompt),
    ]
    deps = lead_deps(state)
    intent = UserIntent.model_validate(
        {
            "classification": "follow_up_question",
            "inferredGoal": "Identify the gene IDs shown in the attached image.",
            "namedGeneIds": [g.gene_id for g in _IMAGE_GENES],
        }
    )
    await classify_user_intent(run_context_for(deps, tool_call_id="c1"), intent)

    facts = turn_facts(deps)
    assert [(g.record_id, g.url) for g in facts.named_genes] == [
        (g.gene_id, f"https://plasmodb.org/plasmo/app/record/gene/{g.gene_id}")
        for g in _IMAGE_GENES
    ]
    assert _printed(deps, _IMAGE_REPLY) == []


# The transmembrane choice: the facts hold the minimum of 2, and a reply offers 3.
_TM_OPTIONS = [
    "Keep the current inclusive rule: at least 2 predicted TM domains",
    "Use a conservative corrected rule: at least 3 predicted TM domains",
]
_TM_PROSE = "You can keep at least 2 domains, or move to at-least-3 domains."


def _tm_deps() -> LeadDeps:
    step = StrategyStepNode(id="c_tm", search_name="GenesByTransmembraneDomains")
    return _deps(
        _session(step, {"c_tm": 1490}),
        shown=["Transmembrane Domain Count: 1,490 genes", "Minimum TM domains: 2"],
        site_id="amoebadb",
    )


def _printed_with(deps: LeadDeps, prose: str, options: list[str]) -> list[str]:
    asked = AskedQuestion(
        question="Which minimum?",
        dimension=ConstraintKind.OTHER,
        options=options,
    )
    record = turn_record(run_context_for(deps))
    return [
        m.sentence
        for m in reconcile(reply(prose, questions=[asked]), record)
        if m.kind == "fact_outside_the_block"
    ]


def test_a_value_a_question_of_the_reply_offers_may_be_named() -> None:
    deps = _tm_deps()

    assert _printed_with(deps, _TM_PROSE, _TM_OPTIONS) == []
    assert _printed(deps, _TM_PROSE) == [fact_outside_the_block_message(["at-least-3"])]


def test_a_label_and_a_count_a_comparison_returned_may_be_printed() -> None:
    deps = _tm_deps()
    deps.state.turn_markers.compared_labels.extend(["Minimum 2", "Minimum 3"])
    deps.state.turn_markers.compared_counts.extend([1490, 227, 1029, 82])

    assert _printed(deps, "At a minimum of 3, 82 of the 227 remain.") == []
    assert _printed(deps, "At a minimum of 3, 83 of the 227 remain.") == [
        fact_outside_the_block_message(["83"])
    ]
