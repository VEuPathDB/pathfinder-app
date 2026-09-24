"""The seam that answers a service refusal to the model instead of the user."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import control_sets
from pathfinder.persistence.models import ControlSet
from pathfinder.platform.errors import (
    AppError,
    ErrorCode,
    InternalError,
    NotFoundError,
    ProviderKeyError,
    ProviderKeyRefusedError,
    ProviderKeyUnreadableError,
    ProviderNotConfiguredError,
    SiteUnavailableError,
    UnauthorizedError,
    site_failure_reason,
)
from pathfinder.platform.refusals import (
    LISTS_THE_IDS,
    CallerSuppliedIds,
    ServiceRefusalRetry,
)
from pathfinder.services.control_sets import ControlSetService
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.tests._support.sub_agents import agent_tool_names
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_TOOL = "read_gene_ids_from_gene_set"
_MISSING_GENE_SET = "d6edd975-f6d9-482e-bc50-3d666b55227f"
_LIVE_CONTROL_SET = "3f2b1c04-0d55-4a19-9c6a-7c1f5f2a8b31"


def _not_found() -> NotFoundError:
    return NotFoundError(detail=f"Gene set not found: {_MISSING_GENE_SET}")


def _call(tool_name: str) -> ToolCallPart:
    return ToolCallPart(tool_name=tool_name, args={}, tool_call_id="tc_1")


def _tool_def(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description="test", parameters_json_schema={})


async def _route(error: Exception, args: dict[str, Any]) -> Any:
    capability: ServiceRefusalRetry[Any] = ServiceRefusalRetry()
    return await capability.on_tool_execute_error(
        MagicMock(),
        call=_call(_TOOL),
        tool_def=_tool_def(_TOOL),
        args=args,
        error=error,
    )


@pytest.mark.asyncio
async def test_a_missing_id_names_the_tool_that_lists_the_ids() -> None:
    with pytest.raises(ModelRetry) as caught:
        await _route(_not_found(), {"gene_set_id": _MISSING_GENE_SET})

    message = str(caught.value)
    assert ErrorCode.NOT_FOUND in message
    assert _MISSING_GENE_SET in message
    assert "list_gene_sets" in message


@pytest.mark.asyncio
async def test_a_refusal_without_an_id_argument_states_its_code() -> None:
    with pytest.raises(ModelRetry) as caught:
        await _route(_not_found(), {})

    message = str(caught.value)
    assert ErrorCode.NOT_FOUND in message
    assert "list_gene_sets" not in message


@pytest.mark.asyncio
async def test_only_the_missing_id_is_blamed() -> None:
    """A call that carries two ids blames the one the refusal names."""
    with pytest.raises(ModelRetry) as caught:
        await _route(
            _not_found(),
            {"gene_set_id": _MISSING_GENE_SET, "control_set_id": _LIVE_CONTROL_SET},
        )

    message = str(caught.value)
    assert "list_gene_sets" in message
    assert "list_control_sets" not in message
    assert _LIVE_CONTROL_SET not in message


@pytest.mark.asyncio
async def test_a_site_that_is_down_is_not_retried() -> None:
    """Retrying an outage spends the turn's budget on a service that cannot answer."""
    with pytest.raises(SiteUnavailableError):
        await _route(SiteUnavailableError("plasmodb", "ConnectError"), {})


@pytest.mark.asyncio
async def test_a_sign_in_refusal_is_not_retried() -> None:
    """No argument the model can choose passes an identity refusal."""
    with pytest.raises(UnauthorizedError):
        await _route(UnauthorizedError(code=ErrorCode.WDK_LOGIN_REQUIRED), {})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refusal",
    [
        ProviderKeyRefusedError("OpenAI"),
        ProviderKeyUnreadableError("OpenAI"),
        ProviderNotConfiguredError("Google"),
    ],
    ids=["refused", "unreadable", "no payer"],
)
async def test_a_key_refusal_is_not_retried(refusal: ProviderKeyError) -> None:
    """No argument the model can choose pays for a model nobody may pay for."""
    with pytest.raises(type(refusal)):
        await _route(refusal, {})


def _one_call_then_text(text: str) -> Callable[..., ModelResponse]:
    """A model that calls the registered tool with the measured id, then answers."""
    calls: list[int] = []

    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        calls.append(len(calls))
        if len(calls) > 1:
            return ModelResponse(parts=[TextPart(content=text)])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=_TOOL,
                    args={"gene_set_id": _MISSING_GENE_SET},
                    tool_call_id=f"tc_{len(calls)}",
                )
            ]
        )

    return _respond


def _lead_toolset_agent(respond: Callable[..., ModelResponse]) -> Agent[LeadDeps, str]:
    """One registered Lead tool under the seam, on the Lead's own deps."""
    return Agent(
        FunctionModel(respond),
        deps_type=LeadDeps,
        toolsets=[
            FunctionToolset[LeadDeps](tools=[control_sets.read_gene_ids_from_gene_set])
        ],
        capabilities=[ServiceRefusalRetry[LeadDeps]()],
        retries=3,
    )


def _deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt="import my controls"))


def _refusing_service(monkeypatch: pytest.MonkeyPatch, error: AppError) -> None:
    async def _refuse(user_id: object, gene_set_id: str) -> list[str]:
        del user_id, gene_set_id
        raise error

    monkeypatch.setattr(control_sets, "control_ids_from_saved_gene_set", _refuse)


@pytest.mark.asyncio
async def test_a_turn_whose_tool_refuses_an_id_still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal ends the tool call, not the turn."""
    _refusing_service(monkeypatch, _not_found())
    agent = _lead_toolset_agent(_one_call_then_text("listed the gene sets"))

    result = await agent.run("import my controls", deps=_deps())

    assert result.output == "listed the gene sets"


@pytest.mark.asyncio
async def test_an_invariant_failure_stays_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 500 is not a call another call can pass, so it ends the run."""
    _refusing_service(monkeypatch, InternalError(detail="the store is unreadable"))
    agent = _lead_toolset_agent(_one_call_then_text("recovered"))

    with pytest.raises(InternalError):
        await agent.run("import my controls", deps=_deps())


@pytest.mark.asyncio
async def test_a_turn_whose_tool_carries_a_defect_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bug is not a correctable call, so it ends the run."""

    async def _bug(user_id: object, gene_set_id: str) -> list[str]:
        del user_id, gene_set_id
        msg = "unsupported operand"
        raise TypeError(msg)

    monkeypatch.setattr(control_sets, "control_ids_from_saved_gene_set", _bug)
    agent = _lead_toolset_agent(_one_call_then_text("recovered"))

    with pytest.raises(TypeError):
        await agent.run("import my controls", deps=_deps())


class _NoControlSetRow:
    """The repository answer for a control set the account does not hold."""

    async def get_by_id(self, control_set_id: UUID) -> ControlSet | None:
        del control_set_id
        return None


async def _seam_message(error: AppError, args: dict[str, Any]) -> str:
    with pytest.raises(ModelRetry) as caught:
        await _route(error, args)
    return str(caught.value)


@pytest.mark.asyncio
async def test_the_control_set_service_refusal_names_its_listing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal the service raises, not a copy of it, carries the id."""
    missing = uuid4()
    service = ControlSetService(MagicMock())
    monkeypatch.setattr(service, "_repo", _NoControlSetRow())

    with pytest.raises(NotFoundError) as refused:
        await service.get(missing, uuid4())

    message = await _seam_message(refused.value, {"control_set_id": str(missing)})
    assert str(missing) in message
    assert "list_control_sets" in message


@pytest.mark.asyncio
async def test_the_gene_set_service_refusal_names_its_listing_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal the service raises, not a copy of it, carries the id."""

    async def _no_row(self: GeneSetStore, entity_id: str) -> GeneSet | None:
        del self, entity_id
        return None

    monkeypatch.setattr(GeneSetStore, "_load", _no_row)
    service = GeneSetService(GeneSetStore())

    with pytest.raises(NotFoundError) as refused:
        await service.get_for_user(uuid4(), _MISSING_GENE_SET)

    message = await _seam_message(refused.value, {"gene_set_id": _MISSING_GENE_SET})
    assert _MISSING_GENE_SET in message
    assert "list_gene_sets" in message


def test_every_read_id_has_a_listing_tool() -> None:
    """An id the seam reads without a listing tool produces guidance with a hole."""
    assert set(CallerSuppliedIds.model_fields) == set(LISTS_THE_IDS)


def test_every_named_listing_tool_is_callable_by_the_lead() -> None:
    """Guidance that names a tool the Lead cannot call is guidance it cannot take."""
    reachable = agent_tool_names(build_lead_agent())
    assert set(LISTS_THE_IDS.values()) <= reachable


def test_a_sign_in_the_site_did_not_answer_says_so_in_words() -> None:
    """A refusal names what happened, never the exception class behind it."""
    refusal = SiteUnavailableError("plasmodb", site_failure_reason(ConnectionError()))

    assert (
        refusal.detail
        == "Could not connect to plasmodb (the site could not be reached)."
    )


def test_a_sign_in_that_timed_out_says_the_site_did_not_answer() -> None:
    """A budget stop and a refused connection read differently."""
    refusal = SiteUnavailableError("toxodb", site_failure_reason(TimeoutError()))

    assert (
        refusal.detail
        == "Could not connect to toxodb (the site did not answer in time)."
    )
