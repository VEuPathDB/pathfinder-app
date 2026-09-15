"""The served research tools' answers land on the turn's markers."""

from __future__ import annotations

from decimal import Decimal

from pydantic_ai import RunContext, ToolReturn
from pydantic_ai.toolsets import FunctionToolset

from pathfinder.ai.lead.retrieval_toolset import (
    ResearchAnswer,
    RetrievalRecordingToolset,
    recording_retrievals,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, ToolCharge
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# One literature answer as the research server serves it: JSON text, camelCase.
SERVED_TEXT = '{"query": "Giardia lamblia mitosome function evidence disagreement Fe-S cluster assembly mitosome role review", "results": [{"title": "Mitosome", "year": 2008, "journal": "Encyclopedia of Genetics, Genomics, Proteomics and Informatics", "authors": [], "doi": "10.1007/978-1-4020-6754-9_10556", "pmid": null, "url": "https://doi.org/10.1007/978-1-4020-6754-9_10556", "abstract": "Encyclopedia of Genetics, Genomics, Proteomics and Informatics"}, {"title": "Mitosome", "year": 2015, "journal": "The Dictionary of Genomics, Transcriptomics and Proteomics", "authors": [], "doi": "10.1002/9783527678679.dg07775", "pmid": null, "url": "https://doi.org/10.1002/9783527678679.dg07775", "abstract": "The Dictionary of Genomics, Transcriptomics and Proteomics"}], "sources": [{"id": "crossref_5b88f4c6b55a", "url": "https://doi.org/10.1007/978-1-4020-6754-9_10556", "title": "Mitosome"}, {"id": "crossref_2ee15282f046", "url": "https://doi.org/10.1002/9783527678679.dg07775", "title": "Mitosome"}], "sourcesStatus": [{"source": "europepmc", "results": 0, "error": null}, {"source": "crossref", "results": 8, "error": null}], "guidance": "Ranked most relevant first."}'
BUDGET_REFUSAL = (
    "You have called research_literature_search 7 times in this run, which is "
    "past the call budget for it. Report what it has returned so far."
)
_REFERENCES = [
    "https://doi.org/10.1007/978-1-4020-6754-9_10556",
    "10.1007/978-1-4020-6754-9_10556",
    "https://doi.org/10.1002/9783527678679.dg07775",
    "10.1002/9783527678679.dg07775",
]


def _ctx() -> RunContext[LeadDeps]:
    return run_context_for(
        lead_deps(pipeline_state(user_prompt="What does the Giardia mitosome do?")),
        tool_call_id="call_lit",
    )


async def _call(
    toolset: RetrievalRecordingToolset, name: str, ctx: RunContext[LeadDeps]
) -> object:
    tools = await toolset.get_tools(ctx)
    return await toolset.call_tool(name, {"query": "mitosome"}, ctx, tools[name])


def _served(name: str, answer: object) -> RetrievalRecordingToolset:
    inner: FunctionToolset[object] = FunctionToolset()

    def tool(query: str) -> object:
        del query
        return answer

    inner.add_function(tool, name=name)
    return RetrievalRecordingToolset(inner)


async def test_the_text_a_served_literature_search_answers_is_recorded() -> None:
    ctx = _ctx()

    result = await _call(
        _served("research_literature_search", SERVED_TEXT),
        "research_literature_search",
        ctx,
    )

    assert result == SERVED_TEXT
    assert ctx.deps.state.turn_markers.retrieved_sources == _REFERENCES


async def test_a_wrapped_return_is_read_through_its_value() -> None:
    ctx = _ctx()
    answer = ToolReturn(return_value=SERVED_TEXT, metadata=["a part"])

    await _call(_served("research_web_search", answer), "research_web_search", ctx)

    assert ctx.deps.state.turn_markers.retrieved_sources == _REFERENCES


async def test_a_refusal_in_place_of_an_answer_records_nothing() -> None:
    ctx = _ctx()

    await _call(
        _served("research_literature_search", BUDGET_REFUSAL),
        "research_literature_search",
        ctx,
    )

    assert ctx.deps.state.turn_markers.retrieved_sources == []


async def test_a_tool_that_is_not_a_research_read_records_nothing() -> None:
    ctx = _ctx()

    await _call(_served("lookup_gene_records", SERVED_TEXT), "lookup_gene_records", ctx)

    assert ctx.deps.state.turn_markers.retrieved_sources == []


def test_the_same_reference_is_recorded_once() -> None:
    answer = ResearchAnswer.model_validate(
        {"results": [{"doi": "10.1/a"}], "sources": [{"url": "10.1/a"}]},
    )

    assert answer.references() == ["10.1/a", "10.1/a"]


def test_no_sources_wrap_nothing() -> None:
    assert [recording_retrievals(None)] == [None]


PRICED_TEXT = SERVED_TEXT[:-1] + ', "costUsd": "0.005"}'


async def test_a_priced_web_search_is_charged_to_the_turn() -> None:
    ctx = _ctx()
    charges: list[ToolCharge] = []
    ctx.deps.record_tool_charge = charges.append

    await _call(_served("research_web_search", PRICED_TEXT), "research_web_search", ctx)

    assert charges == [
        ToolCharge(tool_name="research_web_search", cost_usd=Decimal("0.005")),
    ]


async def test_an_answer_without_a_price_charges_nothing() -> None:
    ctx = _ctx()
    charges: list[ToolCharge] = []
    ctx.deps.record_tool_charge = charges.append

    await _call(_served("research_web_search", SERVED_TEXT), "research_web_search", ctx)

    assert charges == []
