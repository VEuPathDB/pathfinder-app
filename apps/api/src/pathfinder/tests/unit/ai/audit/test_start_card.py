from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.tool_summary import truncate_summary
from pydantic_ai import Agent, DeferredToolRequests, ModelRetry
from pydantic_ai.capabilities import HandleDeferredToolCalls
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import DeferredToolResults, RunContext, ToolDenied
from veupathdb.errors import WDKError, WDKLoginRequiredError

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.run_tools import (
    START_TOOL,
    audit_can_start,
    build_run_toolset,
    plan_gene_model_audit_tool,
)
from pathfinder.ai.audit.start_card import ask_about_the_audits
from pathfinder.domain.audit.planning import (
    START_LABEL,
    AuditStartCard,
    PlanAsk,
    PlanRequest,
    start_card,
)
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.services.audit import planning
from pathfinder.services.audit.planning import propose_scope
from pathfinder.tests._support.audit_planning import (
    RNA_KEPT,
    STRAINS,
    FakeSite,
    faked_site,
    plan_request,
)
from pathfinder.tests._support.run_context import run_context_for

_CALL = "start-1"
GENOME_RULE = (
    "A genome is one of the site's organism names, written in full. For gene "
    "targets alone, send genomes: [] with the same targets."
)
_REQUEST = plan_request(STRAINS[0], STRAINS[1])


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    return faked_site(monkeypatch)


def _context() -> RunContext[AuditDeps]:
    deps = AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())
    return run_context_for(deps, tool_call_id=_CALL)


def _args(request: PlanRequest, scope: AuditScope) -> dict[str, Any]:
    ask = request.model_dump(mode="json", by_alias=True, exclude={"site_id"})
    return {
        "request": ask,
        "scope": scope.model_dump(mode="json", by_alias=True),
    }


def _ask() -> PlanAsk:
    return PlanAsk(genomes=_REQUEST.genomes)


async def _planned() -> AuditScope:
    scope = (await propose_scope(_REQUEST)).scope
    assert scope is not None
    return scope


def _reversed(scope: AuditScope) -> AuditScope:
    return scope.model_copy(
        update={
            "genomes": scope.genomes[::-1],
            "comparison": scope.comparison[::-1],
        }
    )


async def _drawn(scope: AuditScope) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    parked = ToolCallPart(
        tool_name=START_TOOL, args=_args(_REQUEST, scope), tool_call_id=_CALL
    )
    await ask_about_the_audits(
        DeferredToolRequests(approvals=[parked]), written.append, site_id="plasmodb"
    )
    return [entry["chunk"] for entry in written]


@pytest.mark.usefixtures("site")
async def test_the_card_states_the_replanned_fields() -> None:
    label, card = await _drawn(await _planned())

    assert (label["type"], label["data"]["summary"]) == (
        "data-tool-summary",
        START_LABEL,
    )
    assert (card["type"], card["id"]) == ("data-audit-start", _CALL)
    assert AuditStartCard.model_validate(card["data"]) == start_card(
        await propose_scope(_REQUEST), tool_call_id=_CALL
    )


@pytest.mark.usefixtures("site")
async def test_a_start_with_another_genome_order_starts() -> None:
    planned = await _planned()
    turned = _reversed(planned)

    await audit_can_start(_context(), request=_ask(), scope=turned)

    assert turned.genomes != planned.genomes
    (_, card) = await _drawn(turned)
    assert AuditStartCard.model_validate(card["data"]) == start_card(
        await propose_scope(_REQUEST), tool_call_id=_CALL
    )


def test_the_start_arguments_carry_no_estimate() -> None:
    schema = build_run_toolset().tools[START_TOOL].tool_def.parameters_json_schema

    assert set(schema["properties"]) == {"request", "scope"}


def test_no_plan_or_start_request_names_a_site() -> None:
    tools = build_run_toolset().tools
    plan = tools["plan_gene_model_audit"].tool_def.parameters_json_schema
    start = tools[START_TOOL].tool_def.parameters_json_schema

    assert set(plan["properties"]) == {"genomes", "checks", "targets", "confirmLimit"}
    assert start["properties"]["request"] == {"$ref": "#/$defs/PlanAsk"}
    assert set(start["$defs"]["PlanAsk"]["properties"]) == set(plan["properties"])


@pytest.mark.usefixtures("site")
async def test_a_scope_of_another_site_draws_no_card() -> None:
    elsewhere = (await _planned()).model_copy(update={"site_id": "toxodb"})

    with pytest.raises(ModelRetry) as refused:
        await audit_can_start(_context(), request=_ask(), scope=elsewhere)

    assert str(refused.value).endswith("Nothing was started and no card was shown.")


def _starting(args: dict[str, Any]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name=START_TOOL, args=args, tool_call_id=_CALL)
                ]
            )
        return ModelResponse(parts=[TextPart("no audit")])

    return FunctionModel(respond)


@pytest.mark.usefixtures("site")
async def test_a_changed_scope_draws_no_card() -> None:
    planned = await _planned()
    dropped = planned.model_copy(update={"comparison": planned.comparison[:-1]})
    written: list[dict[str, Any]] = []

    async def handler(
        ctx: RunContext[AuditDeps], requests: DeferredToolRequests
    ) -> None:
        del ctx
        await ask_about_the_audits(requests, written.append, site_id="plasmodb")

    agent = Agent(
        _starting(_args(_REQUEST, dropped)),
        deps_type=AuditDeps,
        output_type=[str, DeferredToolRequests],
        toolsets=[build_run_toolset()],
        capabilities=[HandleDeferredToolCalls[AuditDeps](handler=handler)],
    )

    result = await agent.run("start it", deps=_context().deps)

    (retry,) = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    assert result.output == "no audit"
    assert written == []
    assert str(retry.content).endswith(
        "This scope is not the one the planner computes for this request; start "
        "with the scope plan_gene_model_audit returned. Nothing was started and no "
        "card was shown."
    )


async def test_an_approved_start_is_not_planned_again(site: FakeSite) -> None:
    planned = await _planned()
    dropped = planned.model_copy(update={"comparison": planned.comparison[:-1]})
    site.calls.clear()
    approved = replace(_context(), tool_call_approved=True)

    await audit_can_start(approved, request=_ask(), scope=dropped)

    assert site.calls == []


def _parked(scope: AuditScope) -> DeferredToolRequests:
    return DeferredToolRequests(
        approvals=[
            ToolCallPart(
                tool_name=START_TOOL, args=_args(_REQUEST, scope), tool_call_id=_CALL
            )
        ]
    )


async def test_a_replan_with_no_scope_draws_no_card(site: FakeSite) -> None:
    parked = _parked(await _planned())
    site.organisms.remove(STRAINS[1])
    written: list[dict[str, Any]] = []

    results = await ask_about_the_audits(parked, written.append, site_id="plasmodb")

    reason = (
        f"The planner starts no audit: the site holds no genome named {STRAINS[1]}. "
        f"{GENOME_RULE} Nothing was started and no card was shown."
    )
    assert [(c["chunk"]["type"], c["chunk"]["data"]["summary"]) for c in written] == [
        ("data-tool-summary", truncate_summary(reason)),
    ]
    assert results == DeferredToolResults(approvals={_CALL: ToolDenied(reason)})


@pytest.mark.usefixtures("site")
async def test_a_site_error_in_the_replan_draws_no_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parked = _parked(await _planned())

    async def unanswered(site_id: str) -> list[str]:
        del site_id
        detail = "upstream failed"
        raise WDKError(detail, status=502)

    monkeypatch.setattr(planning, "list_organisms", unanswered)
    written: list[dict[str, Any]] = []

    results = await ask_about_the_audits(parked, written.append, site_id="plasmodb")

    reason = (
        "PlasmoDB did not answer the planner's reads (HTTP 502: VEuPathDB service "
        "error: upstream failed). Nothing was started and no card was shown."
    )
    assert [c["chunk"]["data"]["summary"] for c in written] == [
        truncate_summary(reason)
    ]
    assert results == DeferredToolResults(approvals={_CALL: ToolDenied(reason)})


def test_every_plan_field_tells_the_model_what_it_takes() -> None:
    plan = build_run_toolset().tools["plan_gene_model_audit"]
    properties = plan.tool_def.parameters_json_schema["properties"]

    assert {
        name: bool(field.get("description")) for name, field in properties.items()
    } == {
        "genomes": True,
        "checks": True,
        "targets": True,
        "confirmLimit": True,
    }


@pytest.mark.usefixtures("site")
@pytest.mark.parametrize(
    "refusal", [WDKLoginRequiredError(), WDKError("forbidden", status=403)]
)
async def test_a_sign_in_refusal_in_the_replan_reaches_the_turn(
    monkeypatch: pytest.MonkeyPatch, refusal: Exception
) -> None:
    parked = _parked(await _planned())

    async def refused(site_id: str) -> list[str]:
        del site_id
        raise refusal

    monkeypatch.setattr(planning, "list_organisms", refused)
    written: list[dict[str, Any]] = []

    with pytest.raises(type(refusal)):
        await ask_about_the_audits(parked, written.append, site_id="plasmodb")

    assert written == []


@pytest.mark.usefixtures("site")
async def test_a_plan_that_names_a_site_as_a_genome_is_refused_with_the_rule() -> None:
    ctx = _context()

    with pytest.raises(CallRefused) as refused:
        await plan_gene_model_audit_tool(
            ctx, PlanAsk(genomes=("PlasmoDB",), targets=(RNA_KEPT,))
        )

    assert refused.value.message == (
        "The planner starts no audit: the site holds no genome named PlasmoDB. "
        f"{GENOME_RULE} Nothing was started and no card was shown."
    )
    assert (ctx.deps.facts, ctx.deps.records) == ([], [])


@pytest.mark.usefixtures("site")
async def test_a_refused_plan_names_the_organisms_its_words_hold() -> None:
    with pytest.raises(CallRefused) as refused:
        await plan_gene_model_audit_tool(_context(), PlanAsk(genomes=("beta",)))

    assert refused.value.message == (
        "The planner starts no audit: the site holds no genome named beta; the "
        "organisms its words name are Examplea beta R, Examplea beta S. "
        f"{GENOME_RULE} Nothing was started and no card was shown."
    )
