from __future__ import annotations

import ast
import inspect
import textwrap
import types
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import veupathdb_mcp.tools
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import Tool
from veupathdb.jbrowse import JBrowseError
from veupathdb_mcp.audit import (
    GeneId,
    PseudogeneCallAudit,
    locus_tag_answers,
    rate_with_bounds,
)

from pathfinder.ai.audit.check_tools import CHECK_TOOL_NAMES, build_check_toolset
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.facts import audit_finding_fact, json_rows
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import GenePairTarget
from pathfinder.domain.statistic_facts import statistic_value
from pathfinder.services.audit import investigation
from pathfinder.services.audit.finding_views import (
    EvidenceView,
    FindingDetail,
    FindingView,
)
from pathfinder.services.gene_records.read import gene_record_url

_STRAIN = "EXA_0001"
_RESOLVED = "EXA_0001:pseudogene"
_REFERENCE = "EXR_0001"
_GENOME = "Examplea alpha A"
_PAIR_ARGS = {
    "strain_gene": _STRAIN,
    "reference_gene": _REFERENCE,
}
_WHOLE_GENOME_TOOLS = {
    "audit_genome_pseudogene_calls",
    "audit_genome_priority",
    "audit_missing_gene",
    "audit_organelle_gene",
    "audit_gene_fusion",
}
_DATASET_WRITES = {"create_dataset"}


def _intact() -> PseudogeneCallAudit:
    return PseudogeneCallAudit(
        verdict="INTACT",
        reference_cds_length=900,
        strain_cds_length=900,
        covered=900,
        premature_stops=[],
        residue_differences=0,
        gene_ids=[
            GeneId(given=_STRAIN, resolved=_RESOLVED),
            GeneId(given=_REFERENCE, resolved=_REFERENCE),
        ],
        strain_gene=_RESOLVED,
        reference_gene=_REFERENCE,
    )


def _deps() -> AuditDeps:
    return AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())


def _calling(tool_name: str, args: dict[str, Any]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id="c1")]
            )
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(respond)


async def _run(tool_name: str, args: dict[str, Any], deps: AuditDeps) -> ToolReturnPart:
    agent = Agent(
        _calling(tool_name, args),
        deps_type=AuditDeps,
        toolsets=[build_check_toolset()],
        capabilities=[SiteReadFailures[AuditDeps](reads=CHECK_TOOL_NAMES)],
    )
    result = await agent.run("check it", deps=deps)
    (returned,) = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    return returned


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer: object
    fact_id: str


def _read(part: ToolReturnPart) -> _Read:
    return _Read.model_validate(part.content)


def _summary(part: ToolReturnPart) -> str:
    (chunk,) = part.metadata
    return str(chunk.data["summary"])


def _answering(monkeypatch: pytest.MonkeyPatch, error: Exception | None) -> None:
    async def answer(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del site_id, strain_gene, reference_gene
        if error is not None:
            raise error
        return _intact()

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)


async def test_a_check_read_records_the_given_and_resolved_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answering(monkeypatch, None)
    deps = _deps()

    returned = await _run("audit_pseudogene_call", _PAIR_ARGS, deps)

    (fact,) = deps.facts
    assert deps.reads == {
        "audit_pseudogene_call:EXA_0001:EXR_0001",
        "audit_pseudogene_call:EXA_0001:pseudogene:EXR_0001",
    }
    assert (fact.kind, fact.value("strainCdsLength")) == ("gene_check", "900")
    assert [(r.record_id, r.url) for r in deps.records] == [
        (_STRAIN, gene_record_url("plasmodb", _STRAIN)),
        (_RESOLVED, gene_record_url("plasmodb", _RESOLVED)),
        (_REFERENCE, gene_record_url("plasmodb", _REFERENCE)),
    ]
    assert _summary(returned) == "EXA_0001 against EXR_0001: INTACT"
    assert _read(returned).fact_id == fact.id


async def test_a_refused_check_reaches_the_model_as_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answering(monkeypatch, ToolError("EXA_9999 names no gene"))
    deps = _deps()

    returned = await _run("audit_pseudogene_call", _PAIR_ARGS, deps)

    assert returned.outcome == "failed"
    assert "EXA_9999 names no gene" in str(returned.content)
    assert (deps.reads, deps.facts, deps.records) == (set(), [], [])


async def test_a_site_outage_inside_a_tool_error_is_an_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outage = ToolError("plasmodb did not answer the audit reads: ConnectError")
    outage.__cause__ = httpx.ConnectError("refused")
    _answering(monkeypatch, outage)

    returned = await _run("audit_pseudogene_call", _PAIR_ARGS, _deps())

    assert (returned.outcome, str(returned.content)) == (
        "failed",
        (
            "audit_pseudogene_call got no answer from the site (plasmodb did not "
            "answer the audit reads: ConnectError). Nothing was read and the "
            "strategy is unchanged. Say that the site did not answer this read, "
            "and answer from what the turn already holds."
        ),
    )


def _tools() -> dict[str, Tool[AuditDeps]]:
    return build_check_toolset().tools


def test_every_check_tool_keeps_the_library_name_and_description() -> None:
    tools = _tools()
    library = {
        name: tool for name, tool in tools.items() if name != "rate_with_interval"
    }

    assert set(tools) == CHECK_TOOL_NAMES
    assert {name: tool.description for name, tool in library.items()} == {
        name: _without_site(inspect.getdoc(getattr(veupathdb_mcp.tools, name)))
        for name in library
    }


def _without_site(doc: str | None) -> str:
    assert doc is not None
    kept = [line for line in doc.splitlines() if "site_id: VEuPathDB site" not in line]
    assert len(kept) == len(doc.splitlines()) - 1
    return "\n".join(kept)


def test_no_check_tool_asks_the_model_for_a_site() -> None:
    schemas = {
        name: tool.tool_def.parameters_json_schema for name, tool in _tools().items()
    }

    assert {
        name: "site_id" in s["properties"] for name, s in schemas.items()
    } == dict.fromkeys(CHECK_TOOL_NAMES, False)


async def test_a_check_runs_on_the_turns_site(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    async def answer(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del strain_gene, reference_gene
        asked.append(site_id)
        return _intact()

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)
    deps = AuditDeps(site_id="toxodb", user_id=uuid4(), conversation_id=uuid4())

    await _run("audit_pseudogene_call", _PAIR_ARGS, deps)

    assert asked == ["toxodb"]
    assert [r.url for r in deps.records] == [
        gene_record_url("toxodb", gene) for gene in (_STRAIN, _RESOLVED, _REFERENCE)
    ]


async def test_a_genome_store_outage_fails_the_check_and_the_turn_goes_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outage = ToolError("plasmodb answered 503 to the audit reads: window")
    outage.__cause__ = JBrowseError("GET", "https://example.org/seq", 503)
    _answering(monkeypatch, outage)
    deps = _deps()
    agent = Agent(
        _calling("audit_pseudogene_call", _PAIR_ARGS),
        deps_type=AuditDeps,
        toolsets=[build_check_toolset()],
        capabilities=[SiteReadFailures[AuditDeps](reads=CHECK_TOOL_NAMES)],
    )

    result = await agent.run("check it", deps=deps)

    (returned,) = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    assert (result.output, returned.outcome) == ("done", "failed")
    assert str(returned.content).startswith(
        "audit_pseudogene_call got no answer from the site (plasmodb answered 503 "
        "to the audit reads: window)."
    )


def test_no_genome_scale_probe_is_a_chat_tool() -> None:
    assert not CHECK_TOOL_NAMES & _WHOLE_GENOME_TOOLS
    assert len(CHECK_TOOL_NAMES) == 10


def _named(function: Callable[..., object]) -> tuple[set[str], set[str]]:
    try:
        source = inspect.getsource(function)
    except OSError:
        return set(), set()
    tree = ast.parse(textwrap.dedent(source))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    return names, attributes


def _methods(cls: type) -> Iterator[types.FunctionType]:
    for member in vars(cls).values():
        function: object
        match member:
            case classmethod() | staticmethod():
                function = member.__func__
            case property():
                function = member.fget
            case _:
                function = member
        match function:
            case types.FunctionType():
                yield function
            case _:
                pass


def _library_functions(function: types.FunctionType) -> Iterator[types.FunctionType]:
    names, _ = _named(function)
    for name in names:
        match function.__globals__.get(name):
            case types.FunctionType() as found if found.__module__.startswith(
                ("veupathdb_mcp", "veupathdb")
            ):
                yield found
            case type() as found if found.__module__.startswith("veupathdb_mcp"):
                yield from _methods(found)
            case _:
                pass


def _reached(root: Callable[..., object]) -> set[types.FunctionType]:
    assert isinstance(root, types.FunctionType)
    seen: set[types.FunctionType] = set()
    stack = [root]
    while stack:
        function = stack.pop()
        if function not in seen:
            seen.add(function)
            stack.extend(_library_functions(function))
    return seen


def _dataset_writers(root: Callable[..., object]) -> list[str]:
    return sorted(
        f"{function.__module__}.{function.__qualname__}"
        for function in _reached(root)
        if _named(function)[1] & _DATASET_WRITES
    )


def test_the_dataset_trace_enters_library_class_methods() -> None:
    reached = _reached(veupathdb_mcp.tools.audit_strain_model)

    assert "ModelReads.read" in {function.__qualname__ for function in reached}


def test_the_dataset_trace_finds_the_locus_tag_upload() -> None:
    assert _dataset_writers(locus_tag_answers) == [
        "veupathdb_mcp.audit.genes._locus_tag_answer"
    ]


def test_no_chat_check_creates_a_dataset() -> None:
    library = sorted(CHECK_TOOL_NAMES - {"rate_with_interval"})

    assert {
        name: _dataset_writers(getattr(veupathdb_mcp.tools, name)) for name in library
    } == {name: [] for name in library}


async def test_the_rate_tool_is_the_library_rate() -> None:
    deps = _deps()

    returned = await _run(
        "rate_with_interval", {"confirmed": 3, "checked": 12, "unresolved": 4}, deps
    )

    expected = rate_with_bounds(3, 12, 4)
    (fact,) = deps.facts
    assert investigation.rate_with_interval(3, 12, 4) == expected
    assert _read(returned).answer == expected
    assert (fact.kind, _read(returned).fact_id) == ("audit_rate", fact.id)
    assert [fact.value(name) for name in ("confirmed", "checked", "low", "high")] == [
        "3",
        "12",
        repr(expected.low),
        repr(expected.high),
    ]


def test_finding_rows_are_dotted_paths() -> None:
    run_id = uuid4()
    target = GenePairTarget(check="pseudogene_call", genes=(_STRAIN, _REFERENCE))
    detail = FindingDetail(
        site_id="plasmodb",
        finding=FindingView(
            id=7,
            genome=_GENOME,
            screened_genome=_GENOME,
            paired_genome=None,
            target=target,
            sampled=True,
            status="confirmed",
            error_type=None,
            certainty=None,
            judged=True,
            impact=None,
            weighing=None,
            requests=4,
            attempts=1,
            stopped=0,
            message=None,
            reviewed=False,
            verdict="INTACT",
            from_target=True,
            review_line=None,
        ),
        evidence=[
            EvidenceView(
                kind="confirmation",
                status="stored",
                payload=ConfirmationEvidence(
                    confirmation=PseudogeneConfirmation(result=_intact())
                ),
                requests=4,
                attempts=1,
                stopped=0,
                message=None,
            )
        ],
        facts=[],
        review=None,
        review_text=None,
    )

    fact = audit_finding_fact(run_id, detail)

    assert fact.kind == "audit_finding"
    assert fact.value("confirmation.confirmation.result.strainCdsLength") == "900"
    assert fact.value("finding.genome") == _GENOME
    assert fact.value("finding.target.check") == "pseudogene_call"
    assert (fact.value("finding.verdict"), fact.value("finding.fromTarget")) == (
        "INTACT",
        "true",
    )
    assert (
        statistic_value(
            [fact], f"{fact.id}.confirmation.confirmation.result.strainCdsLength"
        )
        == "900"
    )


def test_a_fact_holds_every_scalar_of_a_long_answer() -> None:
    rows = json_rows("lost", [[k, k + 9] for k in range(0, 3000, 10)])

    assert (len(rows), rows[-1].name, rows[-1].value) == (600, "lost.299.1", "2999")
