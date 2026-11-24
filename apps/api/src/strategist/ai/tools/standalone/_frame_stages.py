"""The independent checks of one set_criterion call, run in stages that each
name every problem they find in one refusal."""

from __future__ import annotations

from pydantic_ai import RunContext
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.standalone._frame_answers import answers_the_sheet_lacks
from strategist.ai.tools.standalone._frame_call_checks import (
    undecided,
    unknown_names,
    upload_problems,
)
from strategist.ai.tools.standalone._frame_eda import waiting_problems
from strategist.ai.tools.standalone._frame_lookups import pick_problems
from strategist.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    radio_overrides,
)
from strategist.ai.tools.standalone._frame_reading import reading_label_problems
from strategist.ai.tools.standalone._frame_roles import (
    role_problems,
    saved_input_problems,
)
from strategist.ai.tools.standalone._frame_stated import word_problems
from strategist.domain.refusal import Problems
from strategist.domain.strategy.operational_spec import Criterion
from strategist.platform.refusals import refuse_problems


def _refused(problems: Problems, criterion_id: str, search_name: str) -> None:
    refuse_problems(problems.under(criterion=criterion_id, search=search_name))


def waiting_stage(
    state: AgentToolState, stated: Criterion, search_name: str, early: Problems
) -> None:
    waiting = waiting_problems(state, stated.id)
    if not waiting.empty:
        _refused(early.plus(waiting), stated.id, search_name)


def input_stage(
    state: AgentToolState, stated: Criterion, saved: str, early: Problems
) -> None:
    waiting_stage(state, stated, "", early)
    found = early.plus(answers_the_sheet_lacks(stated.answers, [])).plus(
        saved_input_problems(stated.id, stated.role, saved)
    )
    _refused(found, stated.id, "")


async def search_stage(
    ctx: RunContext[AgentDeps],
    stated: Criterion,
    definition: WDKSearch,
    early: Problems,
) -> None:
    waiting_stage(ctx.deps.agent_state, stated, definition.url_segment, early)
    found = early.plus(await role_problems(ctx, definition, stated.role))
    _refused(found, stated.id, definition.url_segment)


async def sheet_stage(
    ctx: RunContext[AgentDeps],
    stated: Criterion,
    call: CriterionCall,
    infos: list[ParameterInfo],
    definition: WDKSearch,
    *,
    early: Problems,
    reading: str,
) -> None:
    state = ctx.deps.agent_state
    found = (
        early.plus(answers_the_sheet_lacks(stated.answers, infos))
        .plus(reading_label_problems(state, stated.id, reading))
        .plus(await role_problems(ctx, definition, stated.role))
        .plus(unknown_names(call, infos))
        .plus(undecided(call, infos))
    )
    _refused(found, stated.id, call.search_name)


async def value_stage(
    ctx: RunContext[AgentDeps],
    definition: WDKSearch,
    call: CriterionCall,
    infos: list[ParameterInfo],
) -> dict[str, str]:
    state = ctx.deps.agent_state
    radio, off_halves = radio_overrides(definition, call, infos)
    found = (
        off_halves.plus(await upload_problems(ctx.deps.site_id, definition, call))
        .plus(word_problems(definition, call, infos, state))
        .plus(pick_problems(state, definition, call, infos))
    )
    _refused(found, call.criterion_id, call.search_name)
    return radio


def binding_stage(call: CriterionCall, found: Problems) -> None:
    _refused(found, call.criterion_id, call.search_name)
