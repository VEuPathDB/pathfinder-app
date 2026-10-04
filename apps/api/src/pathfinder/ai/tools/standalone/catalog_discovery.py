"""Catalog inspection tools: search overview and parameter vocabularies.

Tools that take an opaque identifier (search name, parameter id) raise
``ModelRetry`` with did-you-mean candidates so the model corrects itself in
the same step.
"""

from dataclasses import replace
from typing import Any, Literal

from assistant_core.graph.stream_events import ToolSummaryStatus
from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import coerce_context_values
from veupathdb_mcp.catalog import (
    GetParameterOptionsResult,
    ParameterInfo,
    ParameterNotOnSearch,
    ParentContextRequired,
    SearchOverviewResult,
    UnknownSearchError,
    VocabNarrowing,
    inspect_search,
    read_parameter_options,
)

from pathfinder.ai.agents.state import ParamVocabSnapshot
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._catalog_elsewhere import joined
from pathfinder.ai.tools.standalone._catalog_models import register_search


class AlreadyReadNotice(CamelModel):
    """Returned when the model re-reads something the agent state already holds.

    The full payload is suppressed because the model already holds it.
    """

    kind: Literal["already_read"] = "already_read"
    message: str
    search_name: str
    parameter_id: str | None = None


async def get_search_overview(
    ctx: RunContext[AgentDeps],
    search_name: str,
    record_type: str | None = None,
) -> ToolReturn[SearchOverviewResult | AlreadyReadNotice]:
    """Get a high-level overview of a search: description, parameters (required/optional), and dependencies.

    MUST be called before creating a step with this search -- it registers the
    search in the discovery gate and caches the parameter schema. Reading the
    same search twice returns a short "already inspected" notice, not a re-dump.

    Args:
        ctx: Agent run context.
        search_name: WDK search name (urlSegment), e.g. 'GenesByText'.
        record_type: Record type. Auto-resolved from search name if omitted (recommended).
    """
    deps = ctx.deps
    if deps.agent_state.get_overview(search_name) is not None:
        return with_summary(
            AlreadyReadNotice(
                message=(
                    f"You already inspected '{search_name}'; this is that read. "
                    "A criterion that already runs it re-binds with no other "
                    "read; a new criterion binds it from a search_for_searches "
                    "answer that names it."
                ),
                search_name=search_name,
            ),
            f"{search_name} already read",
            ctx=ctx,
            status="warn",
        )
    try:
        inspection = await inspect_search(
            deps.site_id,
            search_name,
            record_type=record_type,
            query=deps.agent_state.operational_spec_draft.goal,
        )
    except UnknownSearchError as exc:
        raise ModelRetry(exc.guidance) from exc

    register_search(deps.agent_state, inspection.definition, inspection.record_type)

    overview = inspection.overview
    return with_summary(
        overview,
        f"{search_name}: {count_noun(len(overview.required) + len(overview.optional), 'parameter')}",
        ctx=ctx,
    )


async def get_parameter_options(
    ctx: RunContext[AgentDeps],
    search_name: str,
    parameter_id: str,
    record_type: str | None = None,
    context_values: dict[str, Any] | None = None,
    query: str | list[str] | None = None,
) -> ToolReturn[GetParameterOptionsResult | AlreadyReadNotice]:
    """Get detailed parameter info including vocabulary/allowed values.

    For dependent parameters, pass context_values with the parent parameter's
    chosen value to get the refreshed vocabulary.

    Returns a discriminated union:
      - ``ParameterInfo`` (``kind="parameter_info"``) on success.
      - ``ParameterNotOnSearch`` (``kind="parameter_not_on_search"``) when
        ``parameter_id`` does not exist on ``search_name``. The payload
        carries did-you-mean suggestions plus the full valid list; call
        again with one of them.
      - ``ParentContextRequired`` (``kind="parent_context_required"``) when
        the vocabulary depends on parents no value is bound for; call again
        with them in ``context_values``.

    Args:
        ctx: Agent run context.
        search_name: WDK search name (urlSegment).
        parameter_id: Opaque WDK parameter identifier (e.g. ``min_pct_idents``).
            MUST be one of the names returned by ``get_search_overview`` for
            this search; copy verbatim, do not paraphrase.
        record_type: Record type. Auto-resolved from search name if omitted (recommended).
        context_values: Current values of the parent parameters this param
            depends on, for dependent vocab refresh. Pass the RAW value: a
            string for a single pick, a list for multi-pick; the system types
            it. Example: ``{"profileset_generic": "<term>"}``.
        query: One phrase, or a list of the phrasings of one concept, that
            narrows the vocabulary. Hyphen and space match alike, and a phrase
            also matches its words in any order. For a concept with several
            names pass them all, e.g. ["RNA binding", "RNA recognition", "KH"].
    """
    deps = ctx.deps
    explicit = coerce_context_values(context_values) if context_values else {}
    # Parents already bound by the spec outrank WDK defaults; an explicit
    # argument outranks both. WDK answers a sent value as the parameter's
    # initial value, so the read sends none of the parameter it reads.
    inherited = deps.agent_state.resolved_params_for(search_name)
    merged = {
        name: value
        for name, value in {**inherited, **explicit}.items()
        if name != parameter_id
    }
    typed_context = merged or None
    asked = VocabNarrowing(query=query, organism_hints=deps.agent_state.organism_hints)
    narrowing = replace(
        asked, request=deps.agent_state.phrasings_the_request_states(asked.terms)
    )
    read_key = deps.agent_state.param_read_key(
        search_name, parameter_id, context_values=typed_context, terms=narrowing.terms
    )
    if deps.agent_state.was_param_read(read_key):
        return with_summary(
            AlreadyReadNotice(
                message=(
                    f"You already read options for '{parameter_id}' on "
                    f"'{search_name}' with these exact context/query; same as "
                    "before. Use the values you saw; don't re-read."
                ),
                search_name=search_name,
                parameter_id=parameter_id,
            ),
            f"{parameter_id} on {search_name} already read",
            ctx=ctx,
            status="warn",
        )
    result = await read_parameter_options(
        deps.site_id,
        search_name,
        parameter_id,
        record_type=record_type,
        context_values=typed_context,
        narrowing=narrowing,
    )
    match result:
        case ParameterInfo():
            pass
        case ParentContextRequired(parent_parameter_ids=parents):
            return with_summary(
                result,
                f"{parameter_id} needs {joined(parents)} first",
                ctx=ctx,
                status="warn",
            )
        case ParameterNotOnSearch():
            return with_summary(
                result,
                f"{parameter_id} is not on {search_name}",
                ctx=ctx,
                status="warn",
            )
    _snapshot_param_vocab(deps, search_name, result)
    deps.agent_state.mark_param_read(read_key)
    if result.vocab_lookup is not None:
        deps.agent_state.record_lookup(search_name, parameter_id, result.vocab_lookup)
    return with_summary(
        result,
        _options_summary(parameter_id, result),
        ctx=ctx,
        status=_options_status(result),
    )


def _has_vocabulary_type(info: ParameterInfo) -> bool:
    return "vocabulary" in info.type


def _options_summary(parameter_id: str, info: ParameterInfo) -> str:
    if info.allowed_values_total is not None:
        shown = len(info.allowed_values or [])
        return f"{parameter_id}: {shown} of {info.allowed_values_total} options shown"
    options = len(info.vocabulary())
    if options or _has_vocabulary_type(info):
        return f"{parameter_id}: {options} options"
    return f"{parameter_id}: free-form {info.type}, no vocabulary"


def _options_status(info: ParameterInfo) -> ToolSummaryStatus:
    if len(info.vocabulary()):
        return "ok"
    return "empty" if _has_vocabulary_type(info) else "ok"


def _snapshot_param_vocab(
    deps: AgentDeps,
    search_name: str,
    info: ParameterInfo,
) -> None:
    overview = deps.agent_state.get_overview(search_name)
    if overview is None:
        return
    snapshot = ParamVocabSnapshot.model_validate(info, from_attributes=True)
    updated_vocab = {**overview.param_vocab, info.name: snapshot}
    updated = overview.model_copy(update={"param_vocab": updated_vocab})
    deps.agent_state.register_search(search_name, updated)
