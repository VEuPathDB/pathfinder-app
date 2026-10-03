"""The facts of a turn hold each count before and after an edit, every record a
tool of the turn returned, every gene the gate resolved and every count a
comparison returned, and a reply names each of them by a reference."""

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
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.comparison_facts import (
    ComparedVariant,
    ComparisonFact,
    SharedGenes,
)
from pathfinder.domain.evidence import SampledGene, VerificationReview
from pathfinder.domain.reply_references import ProseFault, prose_faults, render_reply
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.turn_facts import SourceFact
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
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


def _deps(session: StrategySession, *, site_id: str = "plasmodb") -> LeadDeps:
    state = pipeline_state(
        site_id, user_message_id=uuid4(), domain=StrategyDomainState()
    )
    return lead_deps(state, strategy_session=session)


def _rendered(deps: LeadDeps, prose: str) -> str:
    return render_reply(prose, turn_record(run_context_for(deps)).facts)


def _faults(deps: LeadDeps, prose: str) -> list[ProseFault]:
    return prose_faults(prose, turn_record(run_context_for(deps)).facts)


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
    deps = _deps(session)
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


def test_a_reply_says_how_the_count_moved_by_reference() -> None:
    deps = _tightened()
    prose = (
        "It fell from [root_before] to [root], a decrease of [diff:root_before,root]."
    )

    assert _rendered(deps, prose) == (
        "It fell from 209 genes to 38 genes, a decrease of 171 genes."
    )
    assert _faults(deps, "It fell by 172.") == [ProseFault(token="172", kind="number")]


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


_VECTORBASE_RECORD = "https://vectorbase.org/vectorbase/app/record/gene/AFUN020124"


def test_a_record_a_read_returned_is_rendered_linked_with_its_product() -> None:
    deps = _leaf_read()
    deps.state.turn_markers.record_read(
        ReadRecord(
            record_id="AFUN020124",
            url=_VECTORBASE_RECORD,
            product="insulin receptor",
            organism="Anopheles funestus FUMOZ",
            asked_orthologs=["AGAP009262", "Anopheles gambiae PEST"],
        )
    )

    assert _rendered(deps, "The record is [record:AFUN020124].") == (
        f"The record is [AFUN020124]({_VECTORBASE_RECORD}) (insulin receptor)."
    )
    assert _faults(deps, "It is AFUN020124.") == [
        ProseFault(
            token="AFUN020124",
            kind="identifier",
            references=("[record:AFUN020124]",),
        )
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
    "- [record:PF3D7_0709000]\n"
    "- [record:PF3D7_1133400]\n"
    "- [record:PF3D7_0102600]"
)
_PLASMO_RECORD = "https://plasmodb.org/plasmo/app/record/gene/"


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
        (g.gene_id, f"{_PLASMO_RECORD}{g.gene_id}") for g in _IMAGE_GENES
    ]
    assert _rendered(deps, _IMAGE_REPLY) == (
        "The image contains these genes:\n\n"
        f"- [PF3D7_0709000]({_PLASMO_RECORD}PF3D7_0709000) "
        "(chloroquine resistance transporter)\n"
        f"- [PF3D7_1133400]({_PLASMO_RECORD}PF3D7_1133400) "
        "(apical membrane antigen 1)\n"
        f"- [PF3D7_0102600]({_PLASMO_RECORD}PF3D7_0102600) "
        "(serine/threonine protein kinase, FIKK family)"
    )


# cryptodb, build 71: mucin* over C. parvum IOWA-ATCC in the product field and
# in every text field.
def test_the_counts_a_comparison_returned_are_facts_a_reply_references() -> None:
    step = StrategyStepNode(id="c_text", search_name="GenesByText")
    deps = _deps(_session(step, {"c_text": 2}), site_id="cryptodb")
    deps.state.turn_markers.record_comparison(
        ComparisonFact(
            variants=[
                ComparedVariant(label="Product field", gene_count=2, unique_count=0),
                ComparedVariant(
                    label="All text fields", gene_count=84, unique_count=82
                ),
            ],
            overlaps=[SharedGenes(a="Product field", b="All text fields", shared=2)],
        )
    )
    prose = (
        "Every text field finds [compare:All text fields], "
        "[compare:All text fields:unique] beyond the [count:c_text] here."
    )

    assert _rendered(deps, prose) == (
        "Every text field finds 84 genes, 82 genes beyond the 2 genes here."
    )
    assert _faults(deps, "Every text field finds 83.") == [
        ProseFault(token="83", kind="number")
    ]


def test_a_number_the_researcher_writes_is_prose_in_the_reply() -> None:
    step = StrategyStepNode(id="step_cfe9f20f", search_name="GenesByText")
    session = _session(step, {"step_cfe9f20f": 146}, site_id="piroplasmadb")
    state = pipeline_state(
        "piroplasmadb",
        user_prompt="What fraction of the VESA1 genes are on chromosome 1?",
        domain=StrategyDomainState(original_request="Find the VESA1 genes."),
    )
    deps = lead_deps(state, strategy_session=session)

    assert _faults(deps, "On chromosome 1: [count:step_cfe9f20f].") == []
    assert _faults(deps, "On chromosome 2: [count:step_cfe9f20f].") == [
        ProseFault(token="2", kind="number")
    ]
