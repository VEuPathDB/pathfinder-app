from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry, ToolFailed
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb.wdk import get_site
from veupathdb_mcp import MAX_CALL_SECONDS_META_KEY
from veupathdb_mcp.catalog import (
    CladeOnlyExpression,
    EverySpeciesExpression,
    ProteinCountComparison,
)
from veupathdb_mcp.server import TOOLS

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.tools.standalone import orthomcl_expressions
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    build_clade_only_expression,
    build_every_species_expression,
    build_protein_count_comparison,
)
from pathfinder.tests._support.orthomcl_counts import (
    CLADE_ONLY,
    CRYPTOSPORIDIUM,
    EVERY_SPECIES,
    LADDER,
    SITE,
    count_recording,
    replayed_counts,
    same_reading,
)
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context, summary_of

_MORE = "tgon"
_FEWER = "pfal"
_RECORDED_K = 111
_RECORDED_PROBES = 8
_COUNT_REPORT = "/record-types/group/searches/GroupsByPhyleticPattern/reports/standard"


def _recorded_ladders() -> tuple[str, str]:
    forward, backward = count_recording(LADDER).reports[_RECORDED_PROBES:]
    return forward.expression, backward.expression


async def test_the_comparison_reads_k_and_both_ladders_from_the_recorded_counts() -> (
    None
):
    forward, backward = _recorded_ladders()

    with replayed_counts(LADDER) as replay:
        result = await build_protein_count_comparison(
            agent_run_context(site_id=SITE), _MORE, _FEWER, reverse=True
        )

    comparison = returned(result, ProteinCountComparison)
    first, second = comparison.ladders
    assert (comparison.k, comparison.count_reports, len(replay.sent)) == (
        _RECORDED_K,
        10,
        10,
    )
    assert (first.more, first.fewer, first.groups) == (_MORE, _FEWER, 3896)
    assert (second.more, second.fewer, second.groups) == (_FEWER, _MORE, 1472)
    assert same_reading(first.expression, forward)
    assert same_reading(second.expression, backward)
    assert first.expression.endswith("OR pfal=111 AND tgon>=112")
    assert summary_of(result).data["summary"] == (
        "3896 groups with more proteins in tgon than pfal; "
        "1472 groups with more proteins in pfal than tgon"
    )


async def test_one_genome_named_twice_is_sent_back_before_any_count() -> None:
    with replayed_counts(LADDER) as replay, pytest.raises(ModelRetry) as refused:
        await build_protein_count_comparison(
            agent_run_context(site_id=SITE), _MORE, _MORE
        )

    assert str(refused.value) == "genome_a and genome_b name the same genome, 'tgon'."
    assert replay.sent == []


def test_the_comparison_keeps_the_budget_the_served_tool_declares() -> None:
    [served] = [
        row.meta for row in TOOLS if row.fn.__name__ == "build_protein_count_comparison"
    ]

    assert served == {
        MAX_CALL_SECONDS_META_KEY: orthomcl_expressions.PROTEIN_COMPARISON_MAX_CALL_SECONDS
    }
    assert orthomcl_expressions.PROTEIN_COMPARISON_MAX_CALL_SECONDS == 120


async def test_a_count_report_the_site_fails_is_a_failed_call_the_model_reads() -> None:
    report = f"{get_site(SITE).service_url}{_COUNT_REPORT}"

    with (
        replayed_counts(LADDER, status=503) as replay,
        pytest.raises(ToolFailed) as failed,
    ):
        await build_protein_count_comparison(
            agent_run_context(site_id=SITE), _MORE, _FEWER
        )

    assert str(failed.value) == (
        "build_protein_count_comparison got no answer from the site (HTTP 503: "
        "VEuPathDB service error: Request failed after retries: Server error "
        f"'503 Service Unavailable' for url '{report}'\nFor more "
        "information check: "
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/503). Nothing "
        "was read and the strategy is unchanged. Say that the site did not answer "
        "this read, and answer from what the turn already holds."
    )
    assert replay.sent == ["pfal>=128"]


async def test_a_comparison_past_its_budget_is_a_failed_call_the_model_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        orthomcl_expressions, "PROTEIN_COMPARISON_MAX_CALL_SECONDS", 0.01
    )

    with (
        replayed_counts(LADDER, delay=1.0) as replay,
        pytest.raises(ToolFailed) as failed,
    ):
        await build_protein_count_comparison(
            agent_run_context(site_id=SITE), _MORE, _FEWER
        )

    assert str(failed.value) == (
        "build_protein_count_comparison got no answer from the site (no answer "
        "within 0.01 s for the protein counts of tgon and pfal). Nothing was read "
        "and the strategy is unchanged. Say that the site did not answer this "
        "read, and answer from what the turn already holds."
    )
    assert replay.sent == []


async def test_the_clade_only_expression_counts_the_recorded_groups() -> None:
    recorded = count_recording(CLADE_ONLY).reports[1]

    with replayed_counts(CLADE_ONLY, start=1) as replay:
        result = await build_clade_only_expression(
            agent_run_context(site_id=SITE), ["APIC"]
        )

    built = returned(result, CladeOnlyExpression)
    assert built.expression == recorded.expression
    assert (built.groups, built.outside, len(built.genomes)) == (54039, 718, 139)
    assert replay.sent == [built.expression]
    assert summary_of(result).data["summary"] == (
        "54039 groups with a protein in 139 genomes and none in 718 others"
    )


async def test_within_a_larger_clade_counts_the_recorded_groups() -> None:
    recorded = count_recording(CLADE_ONLY).reports[0]

    with replayed_counts(CLADE_ONLY) as replay:
        result = await build_clade_only_expression(
            agent_run_context(site_id=SITE), ["ecun"], ["MICR"]
        )

    built = returned(result, CladeOnlyExpression)
    assert built.expression == (
        "ecun>=1T AND ARCH+BACT+ALVE+AMOE+EUGL+ASCO+BASI+CHYT+MUCO+amac+cang+ccor"
        "+rall+META+OEUK+VIRI=0T"
    )
    assert same_reading(built.expression, recorded.expression)
    assert (built.groups, built.outside, built.genomes) == (558, 806, ("ecun",))
    assert replay.sent == [built.expression]
    assert summary_of(result).data["summary"] == (
        "558 groups with a protein in 1 genomes and none in 806 others"
    )


async def test_every_species_holds_each_species_at_half_its_genomes_rounded_up() -> (
    None
):
    (recorded,) = count_recording(EVERY_SPECIES).reports

    with replayed_counts(EVERY_SPECIES) as replay:
        result = await build_every_species_expression(
            agent_run_context(site_id=SITE), CRYPTOSPORIDIUM
        )

    built = returned(result, EverySpeciesExpression)
    hominis = next(s for s in built.species if s.species == "Cryptosporidium hominis")
    assert built.expression == recorded.expression
    assert (built.groups, len(built.species), built.genomes) == (
        2505,
        12,
        tuple(sorted(CRYPTOSPORIDIUM)),
    )
    assert (len(hominis.genomes), hominis.present) == (4, 2)
    assert replay.sent == [built.expression]
    assert summary_of(result).data["summary"] == (
        "2505 groups present in each of 12 species"
    )


async def test_a_clade_of_one_species_is_sent_back() -> None:
    with replayed_counts(EVERY_SPECIES) as replay, pytest.raises(ModelRetry):
        await build_every_species_expression(agent_run_context(site_id=SITE), ["cand"])

    assert replay.sent == []


async def test_a_code_the_taxonomy_lacks_is_sent_back() -> None:
    with replayed_counts(CLADE_ONLY) as replay, pytest.raises(ModelRetry) as refused:
        await build_clade_only_expression(agent_run_context(site_id=SITE), ["NOPE"])

    assert str(refused.value) == (
        "clade names codes the site's taxonomy does not hold: ['NOPE']."
    )
    assert replay.sent == []


async def test_frame_reads_the_recorded_ladder_as_its_tool_result() -> None:
    forward, _ = _recorded_ladders()
    returns: list[ToolReturnPart] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        returns.extend(p for p in last.parts if isinstance(p, ToolReturnPart))
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "build_protein_count_comparison",
                        {"genome_a": _MORE, "genome_b": _FEWER},
                        "call_ladder",
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "final_result",
                    {"summary": "Built the ladder.", "disposition": "needs_research"},
                )
            ]
        )

    agent = build_frame_agent()
    with (
        replayed_counts(LADDER),
        agent.override(model=FunctionModel(_frame, model_name="scripted")),
    ):
        run = await agent.run(
            "FRAME work order: frame it", deps=agent_run_context(site_id=SITE).deps
        )

    assert isinstance(run.output, FrameResult)
    [answer] = returns
    (ladder,) = ProteinCountComparison.model_validate(answer.content).ladders
    assert answer.tool_name == "build_protein_count_comparison"
    assert same_reading(ladder.expression, forward)
    assert (ladder.groups, ladder.length) == (3896, 2690)
