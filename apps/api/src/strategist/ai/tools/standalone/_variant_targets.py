"""What a variant is allowed to name.

A variant runs one WDK search with values its vocabulary holds, and a pick it
does not name at the site's published default. A combine step is a
strategy structure, so it has no search to run.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from difflib import get_close_matches
from typing import Annotated

from pydantic import Field, JsonValue
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import (
    PHYLETIC_LIST_PARAMS,
    MultiPickValue,
    ParamValue,
    from_wire,
    match_exact_option,
    to_wire,
    wire_map,
)
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import (
    BoundValues,
    ParameterInfo,
    ResolveContext,
    is_phyletic_sheet,
)

from strategist.ai.tools.standalone._stated_values import typed_values
from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.domain.strategy.build_outcome import built_counts
from strategist.domain.strategy.session import StrategySession
from strategist.platform.library_refusals import library_problems
from strategist.platform.refusals import ProblemsRefusal, refuse_problems
from strategist.services.evidence.comparisons import (
    variant_phyletic_values,
    variant_search_parameters,
)
from strategist.services.experiment.variant_comparison import (
    VariantInput,
    VariantSpec,
)
from strategist.services.strategies.pick_readings import site_default
from strategist.services.strategies.record_classes import (
    catalog_search_names,
    search_record_types,
)

_COMBINE_NAMES = frozenset({COMBINE_SEARCH_NAME, "Combine", "combine"})
_PICKS = frozenset({"single-pick-vocabulary", "multi-pick-vocabulary"})
# An unlisted search is refused with at most this many listed names near it.
_NEAREST_SEARCHES = 5
_NEAREST_CUTOFF = 0.3
# A multi-pick named by one of these words, when no entry has that name, runs
# every entry of its vocabulary.
_EVERY_ENTRY_WORDS = frozenset(
    {"all", "every", "*", "all fields", "every field", "everything"}
)


ComparedVariants = Annotated[list[VariantInput], Field(min_length=2)]


def reject_combine_variants(variants: list[VariantInput]) -> None:
    """Raises ModelRetry when a variant names a combine step."""
    named = [v for v in variants if v.search_name in _COMBINE_NAMES]
    if not named:
        return
    offending = "; ".join(f"{v.label} ({v.search_name})" for v in named)
    msg = (
        f"These variants name a combine step rather than a WDK search - "
        f"{offending}. A combine step has no search to run. A combine step is "
        "tested by a control test on that step, by its wdk_step_id. To compare "
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


def _held_values(session: StrategySession, search_name: str) -> dict[str, ParamValue]:
    """The values a step running the search holds, when one step runs it."""
    graph = session.graph
    steps = [
        step
        for step in (graph.steps.values() if graph is not None else ())
        if step.search_name == search_name
    ]
    if len(steps) != 1:
        return {}
    return dict(steps[0].parameters)


def _genes(count: int | None) -> str:
    return "" if count is None else f" ({count:,} genes)"


_IN_PLACE = Problems.one(
    RefusalKey(check=Check.IN_PLACE),
    "A step of the strategy is never a parameter: each variant is counted in "
    "place in the strategy's result.",
)


def _unknown_parameters(
    search_name: str, named: list[VariantInput], infos: list[ParameterInfo]
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


async def _listed_under(site_id: str, variants: list[VariantInput]) -> dict[str, str]:
    """The record type the site's catalog lists each variant's search under.
    Raises ModelRetry for a search the catalog does not list."""
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
    return listed


def _names_every_entry(info: ParameterInfo, stated: JsonValue) -> bool:
    match stated:
        case [str(word)] if info.param_kind == "multi-pick-vocabulary":
            return (
                word.strip().casefold() in _EVERY_ENTRY_WORDS
                and match_exact_option(info.vocabulary(), word) is None
            )
        case _:
            return False


def _every_entry(info: ParameterInfo) -> MultiPickValue:
    return MultiPickValue(values=[option.value for option in info.vocabulary()])


def _sheet_value(info: ParameterInfo) -> ParamValue | None:
    """The value the site's sheet gives the parameter, as a step of the search
    sends it; None for an empty value and a pick whose default takes no option."""
    if info.param_kind in _PICKS:
        return site_default(info)
    return (
        from_wire(info.param_kind, info.default_value) if info.default_value else None
    )


def _published_defaults(
    variant: VariantInput, infos: dict[str, ParameterInfo]
) -> dict[str, ParamValue]:
    """The sheet's value of each parameter the variant names no value for."""
    return {
        name: default
        for name, info in infos.items()
        if name not in variant.parameters
        and (default := _sheet_value(info)) is not None
    }


def _site_set(infos: dict[str, ParameterInfo]) -> dict[str, ParamValue]:
    """Each required parameter the site sets, at the value it sets."""
    return {
        name: from_wire(info.param_kind, value)
        for name, info in infos.items()
        if info.required and (value := info.site_value) is not None
    }


type _Search = tuple[str, str]
type _InfosAt = Callable[[_Search, dict[str, str]], Awaitable[list[ParameterInfo]]]


async def _derived_phyletic(
    about: ResolveContext, search: _Search, values: dict[str, ParamValue]
) -> dict[str, ParamValue] | Problems:
    lists = {
        name: to_wire(values[name]) for name in PHYLETIC_LIST_PARAMS if name in values
    }
    try:
        return await variant_phyletic_values(about, *search, lists)
    except ValidationError as refused:
        return library_problems(refused, RefusalKey(check=Check.PHYLETIC))


def _of_variant(problems: Problems, variant: VariantInput) -> Problems:
    return Problems(
        found=tuple(
            Problem(
                key=p.key.under(criterion=variant.label, search=variant.search_name),
                sentence=f"{variant.label}: {p.sentence}",
            )
            for p in problems.found
        )
    )


def required_problems(
    variant: VariantInput, infos: Mapping[str, ParameterInfo], every: set[str]
) -> Problems:
    return Problems(
        found=tuple(
            Problem(
                key=RefusalKey(check=Check.REQUIRED, parameter=name),
                sentence=(
                    f"{variant.search_name} requires "
                    f"{info.display_name or info.name}; state a value."
                ),
            )
            for name, info in infos.items()
            if info.required
            and name not in variant.parameters
            and name not in every
            and info.site_value is None
            and _sheet_value(info) is None
        )
    )


async def _variant_spec(
    about: ResolveContext,
    search: _Search,
    variant: VariantInput,
    read: BoundValues,
    *,
    every: set[str],
    published: list[ParameterInfo],
    infos_at: _InfosAt,
) -> VariantSpec | Problems:
    values = {n: v for n, v in read.items() if n in variant.parameters}
    parents = {
        info.name: values[info.name]
        for info in published
        if info.wire_children and info.name in values
    }
    infos = {info.name: info for info in await infos_at(search, wire_map(parents))}
    site_set = _site_set(infos)
    entries = {
        **{n: v for n, v in values.items() if n not in site_set},
        **{n: _every_entry(infos[n]) for n in every if n not in site_set},
    }
    spec = VariantSpec(
        label=variant.label,
        search_name=variant.search_name,
        record_type=search[0],
        parameters={**_published_defaults(variant, infos), **entries, **site_set},
    )
    required = required_problems(variant, infos, every)
    if not is_phyletic_sheet(list(infos.values())):
        return spec if required.empty else required
    match await _derived_phyletic(about, search, values):
        case Problems() as refused:
            return required.plus(refused)
        case derived if required.empty:
            return spec.model_copy(
                update={"parameters": {**spec.parameters, **derived}}
            )
        case _:
            return required


async def checked_variants(
    session: StrategySession, stated: list[VariantInput], about: ResolveContext
) -> list[VariantSpec]:
    """The variants as ``resolved_variants`` reads them. Refuses a variant of a
    search no step of the strategy runs, since each one is counted in place."""
    _refuse_a_search_no_step_runs(stated, session)
    try:
        return await resolved_variants(session, stated, about)
    except ProblemsRefusal as refused:
        checks = {problem.key.check for problem in refused.problems.found}
        if "variant_parameters" not in checks:
            raise
        raise ProblemsRefusal(refused.problems.plus(_IN_PLACE)) from refused


async def resolved_variants(
    session: StrategySession, stated: list[VariantInput], about: ResolveContext
) -> list[VariantSpec]:
    """The variants under the record type the catalog lists each search under,
    with each vocabulary value as the entry it names and each pick they do not
    name at the site's published default, and every other parameter they
    name no value for at the value the site's sheet gives it, as a step of the
    search sends it. A required parameter the site sets runs at the value it
    sets. Refuses a search the catalog
    does not list, an unknown parameter, and a value the vocabulary under the
    variant's parents lacks; a value a step holds passes as it is."""
    site_id = session.site_id
    listed = await _listed_under(site_id, stated)
    read: dict[tuple[_Search, tuple[tuple[str, str], ...]], list[ParameterInfo]] = {}

    async def infos_at(search: _Search, context: dict[str, str]) -> list[ParameterInfo]:
        key = (search, tuple(sorted(context.items())))
        if key not in read:
            read[key] = await variant_search_parameters(site_id, *search, context)
        return read[key]

    searches = list(
        dict.fromkeys((listed[v.search_name], v.search_name) for v in stated)
    )
    published = {search: await infos_at(search, {}) for search in searches}
    refuse_problems(
        Problems(
            found=tuple(
                Problem(
                    key=RefusalKey(check=Check.VARIANT_PARAMETERS, search=search[1]),
                    sentence=said,
                )
                for search, infos in published.items()
                if (
                    said := _unknown_parameters(
                        search[1],
                        [v for v in stated if v.search_name == search[1]],
                        infos,
                    )
                )
            )
        )
    )
    checked: list[VariantSpec] = []
    found = Problems()
    for variant in stated:
        search = (listed[variant.search_name], variant.search_name)
        sheet = {info.name: info for info in published[search]}
        every = {
            name
            for name, value in variant.parameters.items()
            if _names_every_entry(sheet[name], value)
        }
        try:
            stated_read = await typed_values(
                about,
                variant.search_name,
                {
                    name: value
                    for name, value in variant.parameters.items()
                    if name not in every
                },
                record_type=search[0],
                bound=_held_values(session, variant.search_name),
            )
        except ProblemsRefusal as refused:
            unparented = {
                name: info
                for name, info in sheet.items()
                if not set(info.wire_parents) & set(variant.parameters)
            }
            problems = required_problems(variant, unparented, every).plus(
                refused.problems
            )
        else:
            match await _variant_spec(
                about,
                search,
                variant,
                stated_read,
                every=every,
                published=published[search],
                infos_at=infos_at,
            ):
                case Problems() as refused_spec:
                    problems = refused_spec
                case spec:
                    checked.append(spec)
                    problems = Problems()
        found = found.plus(_of_variant(problems, variant))
    refuse_problems(found)
    return checked
