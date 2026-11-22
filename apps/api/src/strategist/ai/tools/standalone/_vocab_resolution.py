from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.parameters import ParamValue, match_exact_option
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterInfo, VocabNarrowing


async def _resolved(
    site_id: str,
    search_name: str,
    info: ParameterInfo,
    phrase: str,
    context: Mapping[str, ParamValue] | None,
) -> str:
    if match_exact_option(info.vocabulary(), phrase) is not None:
        return phrase
    read = await catalog.read_parameter_options(
        site_id,
        search_name,
        info.name,
        context_values=context,
        narrowing=VocabNarrowing(query=phrase, request=phrase),
    )
    match read:
        case ParameterInfo(vocab_pick=pick) if pick is not None and pick.settled:
            return pick.value or phrase
        case _:
            return phrase


async def bound_proposal(
    site_id: str,
    search_name: str,
    info: ParameterInfo,
    proposal: list[str],
    context: Mapping[str, ParamValue] | None = None,
) -> list[str]:
    return [
        await _resolved(site_id, search_name, info, phrase, context)
        for phrase in proposal
    ]


__all__ = ["bound_proposal"]
