"""The site's user-dataset searches, and the researcher's own uploads each one reads.

A search that declares a ``userDatasetType`` reads uploads of that VDI type. The
researcher's VDI listing says what they own; the search's vocabulary, read under
their token, says which of those the site can run.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from veupathdb.wdk import (
    EDA_USER_DATASET_PREFIX,
    VdiInstallDisposition,
    WDKEnumParam,
    WDKParameter,
    WDKSearch,
    eda_dataset_id,
    get_site,
    get_vdi_client,
)
from veupathdb_mcp.catalog import (
    eda_backed_search,
    get_raw_searches,
    read_search_definition,
)

USER_DATASET_TYPE_PROPERTY = "userDatasetType"

# Every user-dataset search is a gene search, listed under transcripts.
_RECORD_TYPE = "transcript"


@dataclass(frozen=True, slots=True)
class OwnedUpload:
    """One installed upload of the researcher on the site, by its VDI type."""

    vdi_id: str
    name: str
    type_name: str


@dataclass(frozen=True, slots=True)
class UserDatasetOffer:
    """One upload as the value of one search's dataset parameter."""

    search_name: str
    search_display_name: str
    parameter: str
    value: str
    upload_name: str


def user_dataset_types(search: WDKSearch) -> frozenset[str]:
    """The VDI types the search reads; empty for every other search."""
    return frozenset(search.properties.get(USER_DATASET_TYPE_PROPERTY, []))


def _single_pick(parameter: WDKParameter) -> WDKEnumParam | None:
    match parameter:
        case WDKEnumParam(type="single-pick-vocabulary") as pick:
            return pick
        case _:
            return None


def dataset_parameter(search: WDKSearch) -> WDKEnumParam | None:
    """The parameter a user-dataset search picks its upload in: its one single pick."""
    if not user_dataset_types(search):
        return None
    picks = [
        pick
        for parameter in search.parameters or []
        if (pick := _single_pick(parameter)) is not None
    ]
    return picks[0] if len(picks) == 1 else None


def _terms(parameter: WDKEnumParam) -> frozenset[str]:
    match parameter.vocabulary:
        case list() as entries:
            return frozenset(entry.term for entry in entries)
        case _:
            return frozenset()


def offers_for(
    search: WDKSearch, uploads: Iterable[OwnedUpload]
) -> list[UserDatasetOffer]:
    """The uploads of the search's type that its dataset vocabulary lists.

    A gene list is listed by its VDI id, an EDA-backed upload by its study's
    dataset id.
    """
    parameter = dataset_parameter(search)
    if parameter is None:
        return []
    types = user_dataset_types(search)
    terms = _terms(parameter)
    offers: list[UserDatasetOffer] = []
    for upload in uploads:
        if upload.type_name not in types:
            continue
        value = next(
            (v for v in (upload.vdi_id, eda_dataset_id(upload.vdi_id)) if v in terms),
            None,
        )
        if value is None:
            continue
        offers.append(
            UserDatasetOffer(
                search_name=search.url_segment,
                search_display_name=search.display_name,
                parameter=parameter.name,
                value=value,
                upload_name=upload.name,
            )
        )
    return offers


def export_search_for(
    searches: Sequence[WDKSearch],
    uploads: Sequence[OwnedUpload],
    dataset_id: str,
    *,
    reads_a_volcano: bool,
) -> str | None:
    """The user-dataset search an export of this study runs, or None for the generic one.

    The study must be the researcher's upload, and the search must read the
    upload's type and the export's kind, as the catalog reads it.
    """
    upload = next((u for u in uploads if eda_dataset_id(u.vdi_id) == dataset_id), None)
    if upload is None:
        return None
    for search in searches:
        described = eda_backed_search(search)
        if described is None or described.is_compute_backed != reads_a_volcano:
            continue
        if offers_for(search, [upload]):
            return search.url_segment
    return None


async def owned_uploads(site_id: str) -> list[OwnedUpload]:
    """The researcher's uploads installed on this site, under their own token."""
    project_id = get_site(site_id).project_id
    listing = await get_vdi_client(site_id).list_datasets(project_id)
    return [
        OwnedUpload(vdi_id=row.dataset_id, name=row.name, type_name=row.type.name)
        for row in listing
        if row.status.disposition(project_id) is VdiInstallDisposition.INSTALLED
    ]


async def user_dataset_offers(site_id: str, search_name: str) -> list[UserDatasetOffer]:
    """The researcher's uploads one search can run, read under their token.

    The catalog's cached definition holds the vocabulary of whoever read it
    first, so the vocabulary is read again here.
    """
    definition = await read_search_definition(site_id, _RECORD_TYPE, search_name)
    if dataset_parameter(definition) is None:
        return []
    return offers_for(definition, await owned_uploads(site_id))


async def user_dataset_export_search(
    site_id: str, dataset_id: str, *, reads_a_volcano: bool
) -> str | None:
    """The user-dataset search an export of this study runs on the site, if any.

    Only an upload's study carries the upload prefix, so no other study reads VDI.
    """
    if not dataset_id.startswith(EDA_USER_DATASET_PREFIX):
        return None
    uploads = await owned_uploads(site_id)
    owned = [u for u in uploads if eda_dataset_id(u.vdi_id) == dataset_id]
    if not owned:
        return None
    types = {u.type_name for u in owned}
    listed = await get_raw_searches(site_id, _RECORD_TYPE)
    definitions = [
        await read_search_definition(site_id, _RECORD_TYPE, search.url_segment)
        for search in listed
        if user_dataset_types(search) & types
    ]
    return export_search_for(
        definitions, owned, dataset_id, reads_a_volcano=reads_a_volcano
    )
