"""The served research tools' answers land on the turn's markers."""

from __future__ import annotations

from decimal import Decimal

from assistant_core.mcp.untrusted import UntrustedOutputToolset
from pydantic_ai import RunContext, ToolReturn
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset

from pathfinder.ai.lead.retrieval_toolset import (
    ResearchAnswer,
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
    toolset: AbstractToolset[LeadDeps], name: str, ctx: RunContext[LeadDeps]
) -> object:
    tools = await toolset.get_tools(ctx)
    return await toolset.call_tool(name, {"query": "mitosome"}, ctx, tools[name])


def _tools(name: str, answer: object) -> FunctionToolset[object]:
    inner: FunctionToolset[object] = FunctionToolset()

    def tool(query: str) -> object:
        del query
        return answer

    inner.add_function(tool, name=name)
    return inner


def _served(
    name: str, answer: object, ctx: RunContext[LeadDeps]
) -> AbstractToolset[LeadDeps]:
    wrapped = recording_retrievals(_tools(name, answer), ctx.deps)
    assert wrapped is not None
    return wrapped


def _as_a_source_serves_it(
    name: str, answer: object, ctx: RunContext[LeadDeps]
) -> AbstractToolset[LeadDeps]:
    """The served source as the runtime wraps it, with the recorder outside."""
    served: AbstractToolset[object] = UntrustedOutputToolset(
        _tools(name, answer), part_namespace="research"
    )
    wrapped = recording_retrievals(served, ctx.deps)
    assert wrapped is not None
    return wrapped


async def test_the_text_a_served_literature_search_answers_is_recorded() -> None:
    ctx = _ctx()

    result = await _call(
        _served("research_literature_search", SERVED_TEXT, ctx),
        "research_literature_search",
        ctx,
    )

    assert result == SERVED_TEXT
    assert ctx.deps.state.turn_markers.retrieved_sources == _REFERENCES


async def test_a_wrapped_return_is_read_through_its_value() -> None:
    ctx = _ctx()
    answer = ToolReturn(return_value=SERVED_TEXT, metadata=["a part"])

    await _call(_served("research_web_search", answer, ctx), "research_web_search", ctx)

    assert ctx.deps.state.turn_markers.retrieved_sources == _REFERENCES


async def test_a_refusal_in_place_of_an_answer_records_nothing() -> None:
    ctx = _ctx()

    await _call(
        _served("research_literature_search", BUDGET_REFUSAL, ctx),
        "research_literature_search",
        ctx,
    )

    assert ctx.deps.state.turn_markers.retrieved_sources == []


async def test_a_tool_that_is_not_a_research_read_records_nothing() -> None:
    ctx = _ctx()

    await _call(
        _served("lookup_gene_records", SERVED_TEXT, ctx), "lookup_gene_records", ctx
    )

    assert ctx.deps.state.turn_markers.retrieved_sources == []


DUPLICATE_TEXT = '{"results": [{"doi": "10.1/a"}], "sources": [{"url": "10.1/a"}]}'


async def test_the_same_reference_is_recorded_once() -> None:
    """One answer that lists a reference twice leaves one marker."""
    ctx = _ctx()
    answer = ResearchAnswer.model_validate(DUPLICATE_TEXT)

    await _call(
        _served("research_literature_search", DUPLICATE_TEXT, ctx),
        "research_literature_search",
        ctx,
    )

    assert answer.references() == ["10.1/a", "10.1/a"]
    assert ctx.deps.state.turn_markers.retrieved_sources == ["10.1/a"]


async def test_the_shape_a_served_source_answers_in_is_recorded() -> None:
    """The runtime returns a served answer inside a ToolReturn with its summary."""
    ctx = _ctx()

    result = await _call(
        _as_a_source_serves_it("research_literature_search", SERVED_TEXT, ctx),
        "research_literature_search",
        ctx,
    )

    assert isinstance(result, ToolReturn)
    assert result.return_value == SERVED_TEXT
    assert ctx.deps.state.turn_markers.retrieved_sources == _REFERENCES


def test_no_sources_wrap_nothing() -> None:
    assert [recording_retrievals(None, _ctx().deps)] == [None]


PRICED_TEXT = SERVED_TEXT[:-1] + ', "costUsd": "0.005"}'


async def test_a_priced_web_search_is_charged_to_the_turn() -> None:
    ctx = _ctx()
    charges: list[ToolCharge] = []
    ctx.deps.record_tool_charge = charges.append

    await _call(
        _served("research_web_search", PRICED_TEXT, ctx), "research_web_search", ctx
    )

    assert charges == [
        ToolCharge(tool_name="research_web_search", cost_usd=Decimal("0.005")),
    ]


async def test_an_answer_without_a_price_charges_nothing() -> None:
    ctx = _ctx()
    charges: list[ToolCharge] = []
    ctx.deps.record_tool_charge = charges.append

    await _call(
        _served("research_web_search", SERVED_TEXT, ctx), "research_web_search", ctx
    )

    assert charges == []
