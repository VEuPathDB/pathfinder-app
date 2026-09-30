"""What a variant is allowed to name.

A variant runs one WDK search with values its vocabulary holds. A combine step
is a strategy structure, so it has no search to run.
"""

from __future__ import annotations

from pydantic import TypeAdapter
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParameterCanonicalizer,
    ParamValue,
    SinglePickValue,
    match_exact_option,
    to_wire,
)
from veupathdb.domain.strategy import COMBINE_SEARCH_NAME
from veupathdb_mcp.catalog import (
    ParameterInfo,
    adapt_param_specs_from_search,
    fetch_search_details,
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
from pathfinder.services.experiment.variant_comparison import VariantSpec

_COMBINE_NAMES = frozenset({COMBINE_SEARCH_NAME, "Combine", "combine"})
# An empty pick is refused with the vocabulary, up to this many entries of it.
_LISTED_ENTRIES = 60
# The reader ``set_criterion`` reads a proposed value with.
_PROPOSALS: TypeAdapter[ParamProposals] = TypeAdapter(ParamProposals)


def reject_combine_variants(variants: list[VariantSpec]) -> None:
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


def refuse_a_search_no_step_runs(
    variants: list[VariantSpec], session: StrategySession
) -> None:
    """Raises ModelRetry for a variant whose search no step of the strategy runs.

    A strategy with no step counts each variant alone, so every search passes.
    """
    graph = session.graph
    runs = {
        step_id: step.search_name
        for step_id, step in (graph.steps.items() if graph is not None else ())
        if step.search_name and step.search_name not in _COMBINE_NAMES
    }
    stray = [v for v in variants if runs and v.search_name not in runs.values()]
    if not stray:
        return
    named = "; ".join(
        f"{search} ({', '.join(dict.fromkeys(v.label for v in stray if v.search_name == search))})"
        for search in dict.fromkeys(v.search_name for v in stray)
    )
    counts = built_counts(graph, session.sync_state)
    steps = "; ".join(
        f"{step_id} runs {search}{_genes(counts.of(step_id))}"
        for step_id, search in runs.items()
    )
    msg = (
        f"{named} is no search a step of this strategy runs, and each variant is "
        f"counted in place in the strategy's result. The steps: {steps}. The count "
        "of a criterion's removal is the count of the step that stays."
    )
    raise ModelRetry(msg)


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
        raise _empty_pick(variant.search_name, variant.label, info)
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


type _Search = tuple[str, str]


async def checked_variants(
    site_id: str, variants: list[VariantSpec]
) -> list[VariantSpec]:
    """The variants with each vocabulary value as the entry it names.

    Raises ModelRetry for a parameter the search does not take or a value its
    vocabulary, read under the variant's parent values, does not hold."""
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
        parents = {
            info.name: to_wire(variant.parameters[info.name])
            for info in published[search]
            if info.controls_vocab_of and info.name in variant.parameters
        }
        infos = {info.name: info for info in await infos_at(search, parents)}
        entries = {
            name: _entry_value(variant, infos[name], value)
            for name, value in variant.parameters.items()
        }
        trees = [n for n in entries if infos[n].allowed_values_tree is not None]
        if trees:
            entries |= await _tree_leaves(site_id, variant, entries, trees)
        checked.append(variant.model_copy(update={"parameters": entries}))
    return checked


async def _tree_leaves(
    site_id: str,
    variant: VariantSpec,
    entries: dict[str, ParamValue],
    trees: list[str],
) -> dict[str, ParamValue]:
    """Each tree value as the leaves the site counts, read by the canonicalizer
    ``set_criterion``'s binding runs, from the search's published definition."""
    response, _ = await fetch_search_details(
        SearchContext(site_id, variant.record_type, variant.search_name)
    )
    specs = adapt_param_specs_from_search(response.search_data)
    return ParameterCanonicalizer(specs).canonicalize(
        {name: entries[name] for name in trees}
    )
