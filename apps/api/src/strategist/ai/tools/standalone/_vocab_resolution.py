from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.parameters import match_exact_option
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterInfo, VocabNarrowing


async def _resolved(
    site_id: str,
    search_name: str,
    info: ParameterInfo,
    phrase: str,
    context: Mapping[str, object] | None,
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
    proposal: str | list[str] | None,
    context: Mapping[str, object] | None = None,
) -> str | list[str] | None:
    match proposal:
        case str():
            return await _resolved(site_id, search_name, info, proposal, context)
        case list():
            return [
                await _resolved(site_id, search_name, info, phrase, context)
                for phrase in proposal
            ]
        case None:
            return None


__all__ = ["bound_proposal"]
