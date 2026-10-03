"""A case holds the reply to counting the strategy's steps in genes, never in transcripts."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.devtools.eval_runner import counts_in_genes
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from pathfinder.evals.scoring import ObservedOutcome, score_case

# The title of a search the reply turned down, quoted as the site names it.
_QUOTED_TITLE = (
    "I left out **Genes with changes in sense and antisense transcripts**, "
    "because it measures antisense expression. The strategy holds 720 genes."
)


def _transcript_strategy() -> StrategyAst:
    leaf = StrategyStepNode(id="s_sp", search_name="GenesBySignalPeptide")
    return StrategyAst(record_type="transcript", root=leaf, step_counts={"s_sp": 720})


def _case(counts: bool | None) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["find the secreted genes"],
        site_id="toxodb",
        assistant_id="pathfinder",
        rationale="pins the count unit",
        expected=ExpectedOutcome(builds_strategy=True, counts_in_genes=counts),
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="toxodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-09-27",
        ),
    )


def _observed(reply: str) -> ObservedOutcome:
    return ObservedOutcome(
        built_strategy=True,
        reply_text=reply,
        counts_in_genes=counts_in_genes(reply, _transcript_strategy()),
    )


def test_a_gene_count_beside_a_quoted_title_that_says_transcripts_passes() -> None:
    observed = _observed(_QUOTED_TITLE)

    assert observed.counts_in_genes is True
    assert score_case(_case(True), observed).passed is True


def test_a_step_count_written_in_transcripts_fails() -> None:
    observed = _observed("The strategy holds 720 transcripts.")

    score = score_case(_case(True), observed)

    assert observed.counts_in_genes is False
    assert [(d.field, d.expected, d.actual) for d in score.differences] == [
        ("countsInGenes", "True", "False"),
    ]


def test_a_transcript_count_no_step_holds_is_not_a_step_count() -> None:
    reply = "The 720 genes come from 751 transcripts."

    assert counts_in_genes(reply, _transcript_strategy()) is True


def test_a_column_fit_row_in_transcripts_is_not_a_step_count() -> None:
    shown = (
        "720 of 720 transcripts fit Min %ile (Within Chosen Samples) (80 to 100)\n"
        "The strategy holds 720 genes."
    )

    assert counts_in_genes(shown, _transcript_strategy()) is True


def test_an_unset_expectation_is_not_compared() -> None:
    observed = _observed("The strategy holds 720 transcripts.")

    assert score_case(_case(None), observed).passed is True
