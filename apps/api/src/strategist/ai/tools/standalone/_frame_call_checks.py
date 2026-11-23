"""The checks of one set_criterion call that read the sheet and the call."""

from __future__ import annotations

from difflib import get_close_matches

from veupathdb.domain.parameters import SinglePickValue
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone.gene_set_models import LISTING_PAGE
from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.services.strategies.user_dataset_searches import (
    dataset_parameter,
    user_dataset_offers,
    user_dataset_types,
)


def _bindable(infos: list[ParameterInfo]) -> list[str]:
    return sorted(i.name for i in infos if i.bindable)


def unknown_names(call: CriterionCall, infos: list[ParameterInfo]) -> Problems:
    """A proposal names a parameter of the search the call may set.

    A null proposal is dropped before the DAG's own name check, so a misspelt
    name paired with a null would otherwise set nothing and say nothing.
    """
    bindable = _bindable(infos)
    return Problems(
        found=tuple(
            Problem(
                key=RefusalKey(check=Check.UNKNOWN_NAMES, parameter=name),
                sentence=(
                    f"No such parameter on {call.search_name}: {name!r}. Nearest: "
                    f"{get_close_matches(name, bindable, n=5, cutoff=0.0)}. The valid "
                    f"names are listed above; do not request the sheet again. Valid "
                    f"names: {bindable}."
                ),
            )
            for name in sorted(set(call.params) - set(bindable))
        )
    )


def undecided(call: CriterionCall, infos: list[ParameterInfo]) -> Problems:
    """Every bindable required parameter needs a value or a null."""
    required = {i.name for i in infos if i.bindable and i.required}
    missing = sorted(required - set(call.params) - set(call.values))
    if not missing:
        return Problems()
    return Problems.one(
        RefusalKey(check=Check.UNDECIDED),
        f"Decide every required parameter of {call.search_name}: missing "
        f"{missing}. Pass a value from the sheet, or null for the default. "
        f"The valid names are listed above; do not request the sheet again.",
    )


async def upload_problems(
    site_id: str, definition: WDKSearch, call: CriterionCall
) -> Problems:
    """A user-dataset search binds an upload the researcher owns.

    Its vocabulary is per account, so the cached sheet cannot check it.
    """
    parameter = dataset_parameter(definition)
    if parameter is None:
        return Problems()
    key = RefusalKey(check=Check.UPLOAD, parameter=parameter.name)
    offers = await user_dataset_offers(site_id, call.search_name)
    if not offers:
        types = ", ".join(sorted(user_dataset_types(definition)))
        return Problems.one(
            key,
            f"{call.search_name} reads the researcher's own {types} uploads, and "
            f"this account has none installed on {site_id}, so it cannot run. Bind "
            f"nothing for this criterion, and say that the researcher uploads one "
            f"in My Data Sets on the site.",
        )
    match call.values.get(parameter.name):
        case SinglePickValue(value=value) if value in {o.value for o in offers}:
            return Problems()
        case _:
            uploads = ", ".join(
                f"{o.upload_name!r} ({o.value})" for o in offers[:LISTING_PAGE]
            )
            rest = len(offers) - LISTING_PAGE
            more = f" and {rest} more that list_gene_sets reads" if rest > 0 else ""
            return Problems.one(
                key,
                f"{parameter.name} on {call.search_name} picks one of the "
                f"researcher's own uploads: {uploads}{more}. Pass the value of the "
                f"upload the request refers to.",
            )
