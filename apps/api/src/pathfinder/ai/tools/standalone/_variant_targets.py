"""What a variant is allowed to name.

A variant runs one WDK search with values its vocabulary holds, and a pick it
names no entry for at the site's published default. A combine step is a
strategy structure, so it has no search to run.
"""

from __future__ import annotations

from difflib import get_close_matches

from pydantic import TypeAdapter
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    from_wire,
    match_exact_option,
    to_wire,
)
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME
from veupathdb_mcp.catalog import (
    ParameterInfo,
)

from pathfinder.ai.tools.standalone._frame_proposals import (
    CriterionCall,
    ParamProposals,
    refuse_unmatched_value,
)
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values
from pathfinder.domain.strategy.build_outcome import built_counts
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.evidence.comparisons import variant_search_parameters
from pathfinder.services.experiment.variant_comparison import (
    VariantInput,
    VariantSpec,
)
from pathfinder.services.strategies.pick_readings import site_default
from pathfinder.services.strategies.record_classes import (
    catalog_search_names,
    search_record_types,
)

_COMBINE_NAMES = frozenset({COMBINE_SEARCH_NAME, "Combine", "combine"})
_PICKS = frozenset({"single-pick-vocabulary", "multi-pick-vocabulary"})
# An empty pick with no default is refused with this many vocabulary entries.
_LISTED_ENTRIES = 60
# The reader ``set_criterion`` reads a proposed value with.
_PROPOSALS: TypeAdapter[ParamProposals] = TypeAdapter(ParamProposals)
# An unlisted search is refused with at most this many listed names near it.
_NEAREST_SEARCHES = 5
_NEAREST_CUTOFF = 0.3
# A multi-pick named by one of these words, when no entry has that name, runs
# every entry of its vocabulary.
_EVERY_ENTRY_WORDS = frozenset(
    {"all", "every", "*", "all fields", "every field", "everything"}
)


def reject_combine_variants(variants: list[VariantInput]) -> None:
    """Raises ModelRetry when a variant names a combine step."""
    named = [v for v in variants if v.search_name in _COMBINE_NAMES]
    if not named:
        return
    offending = "; ".join(f"{v.label} ({v.search_name})" for v in named)
    msg = (
        f"These variants name a combine step rather than a WDK search - "
        f"{offending}. A combine step has no search to run. To test a combine "
        "step, call run_control_tests_on_step with its wdk_step_id. To compare "
        "variants, name the leaf search each one varies."
    )
    raise ModelRetry(msg)


def _searches_run(session: StrategySession) -> dict[str, str]:
    """The search each step of the strategy runs, by step id."""
    graph = session.graph
    return {
        step_id: step.search_name
        for step_id, step in (graph.steps.items() if graph is not None else ())
        if step.search_name and step.search_name not in _COMBINE_NAMES
    }


def _refuse_a_search_no_step_runs(
    variants: list[VariantInput], session: StrategySession
) -> None:
    """Raises ModelRetry for a variant whose search no step of the strategy runs.

    A strategy with no step counts each variant alone, so every search passes.
    """
    runs = _searches_run(session)
    stray = [v for v in variants if runs and v.search_name not in runs.values()]
    if not stray:
        return
    named = "; ".join(
        f"{search} ({', '.join(dict.fromkeys(v.label for v in stray if v.search_name == search))})"
        for search in dict.fromkeys(v.search_name for v in stray)
    )
    counts = built_counts(session.graph, session.sync_state)
    steps = "; ".join(
        f"{step_id} runs {search}{_genes(counts.of(step_id))}"
        for step_id, search in runs.items()
    )
    msg = (
        f"{named} is no search a step of this strategy runs, and each variant is "
        f"counted in place in the strategy's result. The steps: {steps}. The count "
        "of a criterion's removal is the count of the step that stays. A search "
        "no step runs is counted alone with count_search."
    )
    raise ModelRetry(msg)


def _held_values(session: StrategySession, search_name: str) -> dict[str, str]:
    """The wire values a step running the search holds, when one step runs it."""
    graph = session.graph
    steps = [
        step
        for step in (graph.steps.values() if graph is not None else ())
        if step.search_name == search_name
    ]
    if len(steps) != 1:
        return {}
    return {name: to_wire(value) for name, value in steps[0].parameters.items()}


def _genes(count: int | None) -> str:
    return "" if count is None else f" ({count:,} genes)"


def _unknown_parameters(
    search_name: str, named: list[VariantSpec], infos: list[ParameterInfo]
) -> str | None:
    """The parameters the variants name that the search does not take, or None."""
    takes = [i.name for i in infos]
    unknown = [
        p
        for p in dict.fromkeys(p for v in named for p in v.parameters)
        if p not in takes
    ]
    if not unknown:
        return None
    labels = ", ".join(v.label for v in named if not set(v.parameters) <= set(takes))
    return (
        f"{search_name} takes no parameter {', '.join(unknown)} ({labels}). "
        f"The parameters it takes: {', '.join(takes)}."
    )


def _nearest(search: str, names: list[str]) -> str:
    close = get_close_matches(search, names, _NEAREST_SEARCHES, _NEAREST_CUTOFF)
    return ", ".join(close) or "none"


async def _listed_under(
    site_id: str, variants: list[VariantInput]
) -> list[VariantSpec]:
    """Each variant under the record type the site's catalog lists its search
    under. Raises ModelRetry for a search the catalog does not list."""
    listed = await search_record_types(site_id, [v.search_name for v in variants])
    unlisted = list(
        dict.fromkeys(v.search_name for v in variants if v.search_name not in listed)
    )
    if unlisted:
        names = await catalog_search_names(site_id)
        msg = " ".join(
            f"{site_id} lists no search {search} "
            f"({', '.join(v.label for v in variants if v.search_name == search)}). "
            f"Nearest searches: {_nearest(search, names)}."
            for search in unlisted
        )
        raise ModelRetry(msg)
    return [
        VariantSpec(
            label=v.label,
            search_name=v.search_name,
            parameters=v.parameters,
            record_type=listed[v.search_name],
        )
        for v in variants
    ]


def _empty_pick(search_name: str, label: str, info: ParameterInfo) -> ModelRetry:
    entries = [option.value for option in info.vocabulary()]
    return ModelRetry(
        f"{info.name} on {search_name} takes at least one entry ({label}), and the "
        f"site refuses an empty pick. Its vocabulary holds {len(entries)} entries: "
        f"{', '.join(entries[:_LISTED_ENTRIES])}"
        f"{', ...' if len(entries) > _LISTED_ENTRIES else ''}."
    )


def _entry_value(
    variant: VariantSpec, info: ParameterInfo, value: ParamValue
) -> ParamValue:
    """The value as the vocabulary's own entries, the way ``set_criterion`` reads it.

    A filter takes a facet expression, not an entry, so it is not checked here.
    """
    options = info.vocabulary()
    if not options or info.param_kind == "filter":
        return value
    proposals = _PROPOSALS.validate_python({info.name: value.to_decoded()})
    picks = proposal_values(proposals[info.name])
    if not picks:
        default = site_default(info)
        if default is None:
            raise _empty_pick(variant.search_name, variant.label, info)
        return default
    if (
        info.param_kind == "multi-pick-vocabulary"
        and len(picks) == 1
        and picks[0].strip().casefold() in _EVERY_ENTRY_WORDS
        and match_exact_option(options, picks[0]) is None
    ):
        return MultiPickValue(values=[option.value for option in options])
    call = CriterionCall(
        criterion_id=variant.label,
        search_name=variant.search_name,
        text="",
        params=proposals,
    )
    refuse_unmatched_value(call, info, options)
    entries = [match_exact_option(options, pick) or pick for pick in picks]
    if info.param_kind == "multi-pick-vocabulary":
        return MultiPickValue(values=entries)
    return SinglePickValue(value=entries[0])


def _sheet_value(info: ParameterInfo) -> ParamValue | None:
    """The value the site's sheet gives the parameter, as a step of the search
    sends it; None for an empty value and a pick whose default takes no option."""
    if info.param_kind in _PICKS:
        return site_default(info)
    return (
        from_wire(info.param_kind, info.default_value) if info.default_value else None
    )


def _published_defaults(
    variant: VariantSpec, infos: dict[str, ParameterInfo]
) -> dict[str, ParamValue]:
    """The sheet's value of each parameter the variant names no value for."""
    return {
        name: default
        for name, info in infos.items()
        if name not in variant.parameters
        and (default := _sheet_value(info)) is not None
    }


def _site_set(infos: dict[str, ParameterInfo]) -> dict[str, ParamValue]:
    """Each hidden required parameter at the value the site sets, which no
    caller chooses."""
    return {
        name: from_wire(info.param_kind, info.default_value)
        for name, info in infos.items()
        if not info.is_visible and info.required and info.default_value is not None
    }


type _Search = tuple[str, str]


async def checked_variants(
    session: StrategySession, stated: list[VariantInput]
) -> list[VariantSpec]:
    """The variants as ``resolved_variants`` reads them. Refuses a variant of a
    search no step of the strategy runs, since each one is counted in place."""
    _refuse_a_search_no_step_runs(stated, session)
    return await resolved_variants(session, stated)


async def resolved_variants(
    session: StrategySession, stated: list[VariantInput]
) -> list[VariantSpec]:
    """The variants under the record type the catalog lists each search under,
    with each vocabulary value as the entry it names and each pick they name no
    entry for at the site's published default, and every other parameter they
    name no value for at the value the site's sheet gives it, as a step of the
    search sends it. A hidden required parameter runs at the value the site
    sets. Refuses a search the catalog
    does not list, an unknown parameter, and a value the vocabulary under the
    variant's parents lacks; a value a step holds passes as it is."""
    site_id = session.site_id
    variants = await _listed_under(site_id, stated)
    read: dict[tuple[_Search, tuple[tuple[str, str], ...]], list[ParameterInfo]] = {}

    async def infos_at(search: _Search, context: dict[str, str]) -> list[ParameterInfo]:
        key = (search, tuple(sorted(context.items())))
        if key not in read:
            read[key] = await variant_search_parameters(site_id, *search, context)
        return read[key]

    searches = list(dict.fromkeys((v.record_type, v.search_name) for v in variants))
    published = {search: await infos_at(search, {}) for search in searches}
    problems = [
        problem
        for search, infos in published.items()
        if (
            problem := _unknown_parameters(
                search[1], [v for v in variants if v.search_name == search[1]], infos
            )
        )
    ]
    if problems:
        msg = (
            f"{' '.join(problems)} A step of the strategy is never a parameter: "
            "each variant is counted in place in the strategy's result."
        )
        raise ModelRetry(msg)
    checked: list[VariantSpec] = []
    for variant in variants:
        search = (variant.record_type, variant.search_name)
        held = _held_values(session, variant.search_name)
        parents = {
            info.name: to_wire(variant.parameters[info.name])
            for info in published[search]
            if info.controls_vocab_of and info.name in variant.parameters
        }
        infos = {info.name: info for info in await infos_at(search, parents)}
        site_set = _site_set(infos)
        entries = {
            name: value
            if held.get(name) == to_wire(value)
            else _entry_value(variant, infos[name], value)
            for name, value in variant.parameters.items()
            if name not in site_set
        }
        entries = {**_published_defaults(variant, infos), **entries, **site_set}
        checked.append(variant.model_copy(update={"parameters": entries}))
    return checked
