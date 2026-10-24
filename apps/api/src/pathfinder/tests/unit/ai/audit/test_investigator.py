from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.models.scripted import retry_prompt_parts
from pydantic_ai import Agent, ModelRetry, RunContext, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage, RunUsage, UsageLimits

from pathfinder.ai.audit import investigator, verdict_tool
from pathfinder.ai.audit.check_tools import CHECK_TOOL_NAMES
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.investigator import (
    BUDGET_ANSWER,
    INVESTIGATION_LIMITS,
    GeneModelInvestigation,
    audit_deps_of,
    investigate,
)
from pathfinder.ai.audit.run_tools import READ_TOOL_NAMES
from pathfinder.ai.audit.verdict_tool import (
    record_gene_model_verdicts,
    unheld_cites_message,
    unheld_genomes_message,
)
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.domain.audit.verdicts import GeneModelVerdict, VerdictOrigin
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.audit.verdicts import AuditCaller
from pathfinder.tests._support.run_context import run_context_for

_UNMADE = "audit_gene_length:EXA_0003"
_VERDICT = {
    "genes": ["EXA_0003"],
    "modelGenome": "Examplea alpha A",
    "verdict": "error",
    "errorType": "truncated_model",
    "certainty": "medium",
    "cause": "The model ends early.",
    "cites": [_UNMADE],
}
type Stored = list[tuple[VerdictOrigin, GeneModelVerdict]]
type Charged = list[tuple[UUID, int, str]]


@pytest.fixture(autouse=True)
def charged(monkeypatch: pytest.MonkeyPatch) -> Charged:
    seen: Charged = []

    async def charge(
        user_id: UUID, usage: RunUsage, model: Model, *, model_id: str
    ) -> None:
        del model
        seen.append((user_id, usage.total_tokens, model_id))

    monkeypatch.setattr(investigator, "charge_run", charge)
    return seen


_HELD = {"EXA_0003": frozenset({"Examplea alpha A"})}


async def test_an_investigation_naming_a_genome_its_reads_do_not_hold_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _storing(monkeypatch, investigator)
    deps = _deps()
    deps.reads.add(_UNMADE)
    deps.hold_genomes(_HELD)
    invented = {**_VERDICT, "modelGenome": "PlasmoDB EXA_0003 model"}
    retried: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        retried.extend(_retries(messages[-1:]))
        verdict = _VERDICT if retried else invented
        return _output(info, {"answer": "It is truncated.", "verdicts": [verdict]})

    await investigate(
        "is the model of EXA_0003 truncated",
        deps=deps,
        model=FunctionModel(respond),
        usage=RunUsage(),
    )

    assert retried == [
        (
            "These verdicts name a genome the reads do not hold: PlasmoDB EXA_0003 "
            "model is not the genome of EXA_0003, which the reads place in "
            "Examplea alpha A. model_genome is the genome of a gene the verdict "
            "judges, as the read of that gene names it. Nothing was stored."
        )
    ]
    assert [verdict.model_genome for _, verdict in stored] == ["Examplea alpha A"]


async def test_the_verdict_tool_refuses_a_real_organism_the_gene_is_not_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _storing(monkeypatch, verdict_tool)
    deps = _deps().model_copy(update={"reads": {"audit_intron_support:Afu2g18040"}})
    deps.hold_genomes({"Afu2g18040": ["Aspergillus fumigatus Af293"]})
    elsewhere = GeneModelVerdict.model_validate(
        {
            **_VERDICT,
            "genes": ["Afu2g18040"],
            "modelGenome": "Neurospora crassa OR74A",
            "cites": ["audit_intron_support:Afu2g18040"],
        }
    )

    with pytest.raises(ModelRetry) as refused:
        await record_gene_model_verdicts(run_context_for(deps), [elsewhere])

    assert str(refused.value) == unheld_genomes_message(
        [
            (
                "Neurospora crassa OR74A is not the genome of Afu2g18040, which the "
                "reads place in Aspergillus fumigatus Af293"
            )
        ]
    )
    assert (stored, deps.recorded) == ([], [])


async def test_the_verdict_tool_refuses_a_gene_no_read_placed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _storing(monkeypatch, verdict_tool)
    deps = _deps().model_copy(update={"reads": {_UNMADE}})

    with pytest.raises(ModelRetry) as refused:
        await record_gene_model_verdicts(
            run_context_for(deps), [GeneModelVerdict.model_validate(_VERDICT)]
        )

    assert str(refused.value) == unheld_genomes_message(
        ["no read of this turn names the genome of EXA_0003"]
    )
    assert stored == []


async def test_an_investigation_carries_the_runs_its_reads_named() -> None:
    deps = _deps()
    run_id = uuid4()
    deps.runs.append(run_id)

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        return _output(info, {"answer": "Nothing to judge.", "verdicts": []})

    found = await investigate(
        "is it right", deps=deps, model=FunctionModel(answer), usage=RunUsage()
    )

    assert found.runs == (run_id,)


def _deps() -> AuditDeps:
    return AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())


def _storing(monkeypatch: pytest.MonkeyPatch, module: object) -> Stored:
    stored: Stored = []

    async def record(
        *,
        caller: AuditCaller,
        origin: VerdictOrigin,
        verdict: GeneModelVerdict,
        model_id: str,
    ) -> int:
        del caller, model_id
        stored.append((origin, verdict))
        return len(stored)

    monkeypatch.setattr(module, "record_verdict", record)
    return stored


def _retries(messages: list[ModelMessage]) -> list[str]:
    return [str(part.content) for part in retry_prompt_parts(messages)]


def _output(info: AgentInfo, args: dict[str, Any]) -> ModelResponse:
    (tool,) = info.output_tools
    return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])


async def test_an_investigation_citing_an_unmade_read_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _storing(monkeypatch, investigator)
    retried: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        retried.extend(_retries(messages[-1:]))
        if not retried:
            return _output(info, {"answer": "It is truncated.", "verdicts": [_VERDICT]})
        return _output(info, {"answer": "No read settles it.", "verdicts": []})

    found = await investigate(
        "is the model of EXA_0003 truncated",
        deps=_deps(),
        model=FunctionModel(respond),
        usage=RunUsage(),
    )

    assert retried == [unheld_cites_message([_UNMADE])]
    assert (found.answer, found.verdicts, stored) == ("No read settles it.", (), [])


async def test_an_investigation_charges_the_tokens_it_spent(charged: Charged) -> None:
    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        (tool,) = info.output_tools
        call = ToolCallPart(
            tool_name=tool.name, args={"answer": "Nothing to judge.", "verdicts": []}
        )
        return ModelResponse(
            parts=[call], usage=RequestUsage(input_tokens=100, output_tokens=20)
        )

    deps = _deps()
    model = FunctionModel(answer, model_name="judge")

    spent = RunUsage()
    await investigate("is it right", deps=deps, model=model, usage=spent)

    assert spent.total_tokens == 120
    assert charged == [(deps.user_id, 120, "function:judge")]


async def test_an_investigation_runs_on_its_own_budget(charged: Charged) -> None:
    def forever(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        args = {"confirmed": 1, "checked": 2, "unresolved": len(messages)}
        return ModelResponse(
            parts=[ToolCallPart(tool_name="rate_with_interval", args=args)]
        )

    deps = _deps()
    spent = RunUsage()
    found = await investigate(
        "what is the rate",
        deps=deps,
        model=FunctionModel(forever, model_name="forever"),
        usage=spent,
    )

    assert INVESTIGATION_LIMITS.request_limit == 24
    assert (found.answer, found.verdicts) == (BUDGET_ANSWER, ())
    assert spent.requests == 24
    assert charged == [(deps.user_id, spent.total_tokens, "function:forever")]


async def test_an_investigation_ignores_the_usage_of_its_caller() -> None:
    inner: list[RunUsage] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        return _output(info, {"answer": "Nothing to judge.", "verdicts": []})

    async def ask_the_investigator(ctx: RunContext[AuditDeps]) -> str:
        spent = RunUsage()
        found = await investigate(
            "is it right", deps=ctx.deps, model=FunctionModel(answer), usage=spent
        )
        inner.append(spent)
        return found.answer

    def outer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="ask_the_investigator", args={})]
            )
        return ModelResponse(parts=[TextPart("done")])

    caller = RunUsage(requests=30)
    agent = Agent(
        FunctionModel(outer), deps_type=AuditDeps, tools=[Tool(ask_the_investigator)]
    )
    await agent.run(
        "go",
        deps=_deps(),
        usage=caller,
        usage_limits=UsageLimits(request_limit=32),
    )

    assert ([u.requests for u in inner], caller.requests) == ([1], 32)


async def test_the_investigator_holds_the_checks_and_reads_and_no_start() -> None:
    offered: list[frozenset[str]] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        offered.append(frozenset(tool.name for tool in info.function_tools))
        return _output(info, {"answer": "Nothing to judge.", "verdicts": []})

    await investigate(
        "is it right", deps=_deps(), model=FunctionModel(answer), usage=RunUsage()
    )

    assert offered == [CHECK_TOOL_NAMES | READ_TOOL_NAMES]


async def test_the_verdict_tool_refuses_an_unmade_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _storing(monkeypatch, verdict_tool)
    deps = _deps()

    held = GeneModelVerdict.model_validate({**_VERDICT, "cites": ["finding:1"]})
    deps.reads.add("finding:1")

    with pytest.raises(ModelRetry, match=_UNMADE):
        await record_gene_model_verdicts(
            run_context_for(deps), [held, GeneModelVerdict.model_validate(_VERDICT)]
        )

    assert (stored, deps.recorded) == ([], [])


async def test_the_verdict_tool_stores_a_verdict_under_the_turns_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _storing(monkeypatch, verdict_tool)
    deps = _deps().model_copy(update={"origin": "verification", "reads": {_UNMADE}})
    deps.hold_genomes({**_HELD, "EXA_0004": frozenset({"Examplea alpha A"})})

    other = GeneModelVerdict.model_validate({**_VERDICT, "genes": ["EXA_0004"]})

    returned = await record_gene_model_verdicts(
        run_context_for(deps, "c1"), [GeneModelVerdict.model_validate(_VERDICT), other]
    )

    assert [origin for origin, _ in stored] == ["verification", "verification"]
    assert (returned.return_value, deps.recorded) == ([1, 2], [1, 2])
    (chunk,) = returned.metadata
    assert chunk.data["summary"] == "EXA_0003: error; EXA_0004: error"


def test_an_investigation_holds_no_facts_in_its_model_schema() -> None:
    schema = GeneModelInvestigation.model_json_schema()

    assert set(schema["properties"]) == {"answer", "verdicts"}


def test_a_turns_deps_become_an_investigations_on_its_site_and_thread() -> None:
    turn = AgentDeps(
        site_id="toxodb",
        user_id=uuid4(),
        conversation_id=uuid4(),
        strategy_session=StrategySession("toxodb"),
        turn_markers=TurnMarkers(),
    )

    deps = audit_deps_of(turn, origin="verification")

    assert (deps.site_id, deps.user_id, deps.conversation_id, deps.origin) == (
        "toxodb",
        turn.user_id,
        turn.conversation_id,
        "verification",
    )
    assert (deps.reads, deps.facts, deps.records) == (set(), [], [])
