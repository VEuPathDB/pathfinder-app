"""The readings of a phylogenetic profile's species lists: a group required in
every member against at least one member, and no species excluded."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from veupathdb.domain.parameters import (
    ParamValue,
    PhyleticBinding,
    PhyleticTree,
    StringValue,
    derive_binding,
    to_wire,
)

from pathfinder.domain.strategy.operational_spec import Measurement
from pathfinder.services.strategies.pick_readings import CountWith

# The WDK parameters that list the species a phylogenetic profile requires
# and the ones it forbids.
_INCLUDED_SPECIES = "included_species"
_EXCLUDED_SPECIES = "excluded_species"
# A group is two species or more; one species reads the same both ways.
_SMALLEST_GROUP = 2


def _as_values(derived: PhyleticBinding) -> dict[str, ParamValue]:
    return {name: StringValue(value=v) for name, v in derived.model_dump().items()}


async def _strain_readings(
    count_with: CountWith,
    params: Mapping[str, ParamValue],
    bound: int,
    value: ParamValue,
    tree: PhyleticTree,
) -> list[Measurement]:
    """A species group required in every member, against at least one member.

    A census holds each species present or absent, so the genes with at least
    one member present are the genes with no constraint on the group less the
    genes with every member absent. Either count missing leaves it unmeasured.
    """
    excluded = params.get(_EXCLUDED_SPECIES)
    excluded_codes = tree.resolve_terms(to_wire(excluded) if excluded else "").codes
    included_codes = tree.resolve_terms(to_wire(value)).codes
    states = tree.leaf_states(included_codes, excluded_codes)
    group = sorted(code for code, state in states.items() if state == "include")
    if len(group) < _SMALLEST_GROUP:
        return []
    free = derive_binding(tree, [], excluded_codes)
    absent = derive_binding(tree, [], [*excluded_codes, *group])
    found: list[Measurement] = []
    match free, absent:
        case PhyleticBinding(), PhyleticBinding():
            without, none = await asyncio.gather(
                count_with(_as_values(free)),
                count_with(_as_values(absent)),
            )
            found.append(
                Measurement(
                    kind="any_strain",
                    param=_INCLUDED_SPECIES,
                    count=None if without is None or none is None else without - none,
                    reading=f"at least one of {len(group)} species",
                )
            )
    found.append(
        Measurement(
            kind="all_strains",
            param=_INCLUDED_SPECIES,
            count=bound,
            reading=f"all {len(group)} species",
        )
    )
    return found


async def _excluded_reading(
    count_with: CountWith,
    params: Mapping[str, ParamValue],
    bound: int,
    name: str,
    value: ParamValue,
    tree: PhyleticTree,
) -> list[Measurement]:
    """The count with no species excluded, when it counts more."""
    included = params.get(_INCLUDED_SPECIES)
    included_codes = tree.resolve_terms(to_wire(included) if included else "").codes
    if not tree.resolve_terms(to_wire(value)).codes:
        return []
    match derive_binding(tree, included_codes, []):
        case PhyleticBinding() as free:
            count = await count_with(_as_values(free))
        case _:
            return []
    if count is not None and count <= bound:
        return []
    return [
        Measurement(
            kind="loosest_bound", param=name, count=count, reading="no species excluded"
        )
    ]


async def species_readings(
    count_with: CountWith,
    params: Mapping[str, ParamValue],
    bound: int,
    name: str,
    value: ParamValue,
    tree: PhyleticTree,
) -> list[Measurement]:
    """The other readings of one species list of a binding that counted
    ``bound`` records with ``params``."""
    if name == _INCLUDED_SPECIES:
        return await _strain_readings(count_with, params, bound, value, tree)
    return await _excluded_reading(count_with, params, bound, name, value, tree)


__all__ = ["species_readings"]
