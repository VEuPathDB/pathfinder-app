"""The record classes a site declares for the searches a tree runs."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping

from veupathdb.domain.strategy import (
    CombineOp,
    StrategyStep,
    StrategyStepNode,
    walk,
)
from veupathdb.wdk import WDKRecordType, WDKSearch
from veupathdb_mcp.catalog import (
    get_raw_record_types,
    get_raw_searches,
    make_record_type_resolver,
)

from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.domain.strategy.record_class_check import (
    SearchRecordClasses,
    first_mixed_combine,
    mixed_combine_refusal,
    step_class_of,
    transform_input_refusal,
)
from pathfinder.services.strategies.step_search import COLOCATION_SEARCH


def record_classes_of(search: WDKSearch, listed_under: str) -> SearchRecordClasses:
    """What the search returns and what its input step may hold."""
    return SearchRecordClasses(
        display_name=search.display_name,
        returns=search.output_record_class_name or listed_under,
        takes=tuple(search.allowed_primary_input_record_class_names or ()),
    )


async def search_record_types(
    site_id: str, search_names: Collection[str]
) -> dict[str, str]:
    """The record type the catalog lists each named search under. A search the
    catalog does not list is left out."""
    listed_under = await make_record_type_resolver(site_id)
    found: dict[str, str] = {}
    for name in sorted(set(search_names)):
        record_type = await listed_under(name)
        if record_type is not None:
            found[name] = record_type
    return found


async def catalog_search_names(site_id: str) -> list[str]:
    """Every search name the site's catalog lists, under any record type."""
    return [
        search.url_segment
        for record in await get_raw_record_types(site_id)
        for search in await get_raw_searches(site_id, record.url_segment)
    ]


async def record_class_names(site_id: str) -> dict[str, str]:
    """The plural display name of each record class the site publishes."""
    return {
        record.url_segment: record.display_name_plural or record.url_segment
        for record in await get_raw_record_types(site_id)
    }


async def site_transforms(site_id: str) -> dict[str, SearchRecordClasses]:
    return {
        search.url_segment: record_classes_of(search, record.url_segment)
        for record in await get_raw_record_types(site_id)
        for search in await get_raw_searches(site_id, record.url_segment)
        if search.allowed_primary_input_record_class_names
    }


def _own_search(step: StrategyStep) -> str | None:
    if step.operator is CombineOp.COLOCATE:
        return COLOCATION_SEARCH
    return step.search_name


async def fill_record_classes(site_id: str, steps: dict[str, StrategyStep]) -> None:
    unclassed = [
        (step, name)
        for step in steps.values()
        if not step.record_class and (name := _own_search(step))
    ]
    if not unclassed:
        return
    listed_under = await make_record_type_resolver(site_id)
    for step, name in unclassed:
        step.record_class = await listed_under(name)


async def step_record_class(
    site_id: str, steps: dict[str, StrategyStep], step_id: str
) -> str | None:
    await fill_record_classes(site_id, steps)
    return step_class_of(steps, step_id)


def unclassed_step_failure(step_id: str, search_name: str) -> StepPushFailure:
    return StepPushFailure(
        step_id=step_id,
        search_name=search_name,
        error=(
            f"The site lists no record type for {search_name or step_id}, so "
            f"PathFinder cannot address the step and did not send it."
        ),
    )


def _own_node_search(node: StrategyStepNode) -> str:
    if node.operator is CombineOp.COLOCATE:
        return COLOCATION_SEARCH
    return node.search_name


async def tree_record_class_refusal(
    site_id: str, root: StrategyStepNode, held: Mapping[str, str]
) -> str | None:
    nodes = walk(root)
    if len(nodes) == 1:
        return None
    searches = {n.id: _own_node_search(n) for n in nodes}
    listed = await search_record_types(site_id, list(searches.values()))
    own = {
        **{sid: listed[name] for sid, name in searches.items() if name in listed},
        **held,
    }
    names = await record_class_names(site_id)
    transforms = await site_transforms(site_id)
    mixed = first_mixed_combine(root, own)
    if mixed is not None:
        return mixed_combine_refusal(mixed, names, transforms)
    return transform_input_refusal(root, own, transforms, names)


async def names_of_every_record_type(site_id: str) -> dict[str, list[str]]:
    return record_names_of(await get_raw_record_types(site_id))


def record_names_of(records: Iterable[WDKRecordType]) -> dict[str, list[str]]:
    return {
        record.url_segment: list(
            dict.fromkeys(
                name
                for name in [
                    record.url_segment,
                    record.display_name,
                    record.display_name_plural,
                    record.short_display_name,
                ]
                if name
            )
        )
        for record in records
    }
