"""The EDA study catalog: browse, search, and resolve a dataset to a study."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

import httpx
from assistant_core.platform.logging import get_logger
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import (
    EdaPermissionEntry,
    EdaStudyDetail,
    EdaStudyOverview,
    get_eda_client,
)
from veupathdb.errors import WDKLoginRequiredError
from veupathdb.wdk import get_site_router
from veupathdb_mcp.catalog import sites_publishing
from veupathdb_mcp.embeddings import (
    SemanticIndexUnavailableError,
    SyncReport,
    search_study_index,
    strip_markup,
    study_index_is_built,
    sync_study_index,
)

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.eda.study_site import PORTAL, not_here

logger = get_logger(__name__)

# The source type EDA gives a study the researcher uploaded.
OWN_SOURCE_TYPE = "user_submitted"

# A tool payload carries the gist of a description, not the whole abstract.
_DESCRIPTION_LIMIT = 600


def study_cache_key(*, base_url: str, study: EdaStudyOverview) -> str:
    """Content address of a curated study's fetched metadata, by its content hash."""
    return f"{base_url}|{study.id}|{study.sha1hash}"


class UnknownEdaDatasetError(NotFoundError):
    """A dataset with no ``perDataset`` entry for this user.

    Resolution and authorization are the same call, so an inaccessible dataset
    and a nonexistent one are one case.
    """

    def __init__(self, dataset_id: str, known: Sequence[str]) -> None:
        self.dataset_id = dataset_id
        self.guidance = (
            f"Dataset {dataset_id!r} has no entry in this account's EDA "
            f"permissions, so it does not exist or is not accessible. "
            f"{len(known)} datasets are available; search for one by name "
            f"instead of guessing an id."
        )
        super().__init__(title="Study not found", detail=self.guidance)


# The curated catalog, which is the same for every account on a site. The
# listing also names each account's own studies, which never enter this map.
_studies: dict[str, list[EdaStudyOverview]] = {}

# Authorization maps, addressed by the site and the credential that read them.
_permission_maps: dict[str, dict[str, EdaPermissionEntry]] = {}

# A credential is one entry, and a long-lived process sees many. At the cap
# the map is dropped whole and every account reads again.
_PERMISSION_CACHE_MAX_ENTRIES = 512

# Study details, addressed by the version their listing reports.
_details: dict[str, EdaStudyDetail] = {}

# Whole entity sizes, addressed like the study detail they belong to.
_entity_totals: dict[str, int] = {}


def _permissions_key(site_id: str) -> str:
    """The site and the credential the call carries, as one address."""
    token = veupathdb_auth_token_ctx.get()
    if not token:
        raise WDKLoginRequiredError
    return f"{site_id}|{hashlib.sha256(token.encode()).hexdigest()}"


async def _permissions(site_id: str) -> dict[str, EdaPermissionEntry]:
    """The authorization map for the account this call carries.

    ``/permissions`` answers for the calling account, so the answer is never
    reused for another credential.
    """
    key = _permissions_key(site_id)
    cached = _permission_maps.get(key)
    if cached is None:
        cached = await get_eda_client(site_id).get_permissions()
        if len(_permission_maps) >= _PERMISSION_CACHE_MAX_ENTRIES:
            _permission_maps.clear()
        _permission_maps[key] = cached
    return cached


def refresh_permissions(site_id: str) -> None:
    """Drop this credential's authorization map, so the next read asks again.

    A study the account installs after its map was read is absent until then.
    """
    _permission_maps.pop(_permissions_key(site_id), None)


async def resolve_dataset(site_id: str, dataset_id: str) -> EdaPermissionEntry:
    """The dataset's permission entry, which carries its study id.

    Resolution goes through ``/permissions`` and nothing else. The id suffixes
    agree for most curated studies and not for all of them.
    """
    per_dataset = await _permissions(site_id)
    entry = per_dataset.get(dataset_id)
    if entry is None:
        raise UnknownEdaDatasetError(dataset_id, sorted(per_dataset))
    return entry


@dataclass(frozen=True, slots=True)
class StudyCard:
    """One study as the agent and the tab see it.

    ``relevance`` is a cosine in [0, 1]; a negative cosine is no relevance.
    """

    dataset_id: str
    study_id: str
    display_name: str
    short_display_name: str
    description: str
    source_type: str
    relevance: float = 0.0
    can_subset: bool = False
    can_export_rows: bool = False
    # The genomics sites that publish the dataset, ["portal"] when none does,
    # and empty when the experiment store did not answer.
    sites: list[str] = field(default_factory=list)
    # Why the study does not open on the site that listed it, or None.
    not_here: str | None = None


async def list_studies(site_id: str) -> list[EdaStudyOverview]:
    """The curated catalog. It is not the study universe and not the resolver.

    ``/studies`` answers for the calling account, so its user rows are dropped
    before the answer is shared.
    """
    listed = _studies.get(site_id)
    if listed is None:
        listed = [
            study
            for study in await get_eda_client(site_id).list_studies()
            if study.source_type == "curated"
        ]
        _studies[site_id] = listed
    return listed


async def preload_study_index() -> SyncReport | None:
    """Sync the study index once, under the service account token.

    The EDA service answers with the portal's catalog on every site, so one
    index serves them all: the first site that answers is the one that syncs.
    """
    settings = get_settings()
    if not settings.embedding_index_sync_enabled:
        logger.info("[warm-up] This process does not sync the EDA study index")
        return None
    token = settings.veupathdb_auth_token
    if not token:
        logger.info("[warm-up] No service token, so no EDA study index is synced")
        return None
    veupathdb_auth_token_ctx.set(token)
    for site_id in _preload_order(settings.veupathdb_default_site):
        try:
            report = await sync_study_index(await list_studies(site_id))
        except (
            NotFoundError,
            SemanticIndexUnavailableError,
            OSError,
            httpx.HTTPError,
        ) as exc:
            logger.warning(
                "[warm-up] EDA study index sync failed",
                site_id=site_id,
                error=str(exc),
            )
            continue
        logger.info(
            "[warm-up] EDA study index synced",
            site_id=site_id,
            added=report.added,
            updated=report.updated,
            removed=report.removed,
            reused=report.reused,
            embedded_texts=report.embedded_texts,
        )
        return report
    return None


def _preload_order(default_site: str) -> list[str]:
    """The sites the warm-up tries, the configured default first."""
    ids = [site.id for site in get_site_router().list_sites()]
    return [default_site, *[site_id for site_id in ids if site_id != default_site]]


def _plain(description: str | None) -> str:
    """The description without its inline markup, trimmed for a tool payload."""
    if not description:
        return ""
    return strip_markup(description).strip()[:_DESCRIPTION_LIMIT]


NAME_MATCH_GUIDANCE = (
    "The study index is not built yet; results are matched by name only."
)


StudyRanking = Literal["semantic", "name"]


@dataclass(frozen=True, slots=True)
class StudySearch:
    """The ranked studies, the catalog behind them, and how they were ranked.

    ``catalog_size`` is how many studies this account can see on the site, so
    a semantic ranking reports the closest few of a number the reader knows.
    """

    cards: list[StudyCard]
    catalog_size: int
    ranking: StudyRanking = "semantic"

    @property
    def guidance(self) -> str:
        """What to say when the ranking is not semantic."""
        return NAME_MATCH_GUIDANCE if self.ranking == "name" else ""


async def search_studies(
    site_id: str,
    query: str,
    limit: int = 10,
) -> StudySearch:
    """Rank the studies this account can see against a natural-language query."""
    per_dataset = await _permissions(site_id)
    by_dataset = {s.dataset_id: s for s in await list_studies(site_id)}
    catalog_size = sum(1 for dataset_id in by_dataset if dataset_id in per_dataset)
    if not await study_index_is_built():
        return StudySearch(
            cards=await _with_sites(
                site_id, _by_name(query, per_dataset, by_dataset, limit)
            ),
            catalog_size=catalog_size,
            ranking="name",
        )
    try:
        hits = await search_study_index(query, top_k=len(by_dataset) or 1)
    except SemanticIndexUnavailableError as exc:
        logger.warning("EDA study search fell back to names", error=str(exc))
        return StudySearch(
            cards=await _with_sites(
                site_id, _by_name(query, per_dataset, by_dataset, limit)
            ),
            catalog_size=catalog_size,
            ranking="name",
        )
    cards: list[StudyCard] = []
    # The full ranking is walked, so a study with no permission entry does not
    # consume a card slot.
    for hit in hits:
        entry = per_dataset.get(hit.entry_id)
        overview = by_dataset.get(hit.entry_id)
        if entry is None or overview is None:
            continue
        cards.append(_card(entry, overview, relevance=max(0.0, hit.similarity)))
        if len(cards) >= limit:
            break
    return StudySearch(
        cards=await _with_sites(site_id, cards), catalog_size=catalog_size
    )


async def _with_sites(site_id: str, cards: list[StudyCard]) -> list[StudyCard]:
    """Each card labelled with the genomics sites that publish its dataset, and
    with why it does not open on ``site_id`` when another site publishes it."""
    if not cards:
        return cards
    try:
        published = await sites_publishing([card.dataset_id for card in cards])
    except SemanticIndexUnavailableError as exc:
        logger.warning("Study sites were not read", error=str(exc))
        return cards
    return [
        _labelled(site_id, card, published.get(card.dataset_id, [PORTAL]))
        for card in cards
    ]


def _labelled(site_id: str, card: StudyCard, sites: list[str]) -> StudyCard:
    own = card.source_type == OWN_SOURCE_TYPE
    return replace(card, sites=sites, not_here=not_here(site_id, sites, own=own))


def _by_name(
    query: str,
    per_dataset: dict[str, EdaPermissionEntry],
    by_dataset: dict[str, EdaStudyOverview],
    limit: int,
) -> list[StudyCard]:
    """The studies whose name contains the query, ordered by name."""
    needle = query.strip().lower()
    cards = [
        _card(entry, overview, relevance=0.0)
        for dataset_id, overview in by_dataset.items()
        if needle in overview.display_name.lower()
        and (entry := per_dataset.get(dataset_id)) is not None
    ]
    cards.sort(key=lambda card: card.display_name)
    return cards[:limit]


def _card(
    entry: EdaPermissionEntry,
    overview: EdaStudyOverview,
    *,
    relevance: float,
) -> StudyCard:
    return StudyCard(
        dataset_id=overview.dataset_id,
        study_id=entry.study_id,
        display_name=overview.display_name,
        short_display_name=overview.short_display_name or "",
        description=_plain(overview.description),
        source_type=overview.source_type,
        relevance=relevance,
        can_subset=entry.action_authorization.subsetting,
        can_export_rows=entry.action_authorization.results_all,
    )


async def browse_studies(site_id: str, limit: int = 10) -> list[StudyCard]:
    """The catalog this account can see, ordered by name and unranked.

    The tab's study picker opens with no query, so a blank search is a browse
    rather than an empty answer.
    """
    per_dataset = await _permissions(site_id)
    cards = [
        _card(entry, overview, relevance=0.0)
        for overview in await list_studies(site_id)
        if (entry := per_dataset.get(overview.dataset_id)) is not None
    ]
    cards.sort(key=lambda card: card.display_name)
    return await _with_sites(site_id, cards[:limit])


async def get_study_detail(site_id: str, study: EdaStudyOverview) -> EdaStudyDetail:
    """The full entity tree, cached on the version the listing reports.

    A re-listed study whose ``sha1hash`` changed reads again; an unchanged one
    is served from the cache.
    """
    client = get_eda_client(site_id)
    key = study_cache_key(base_url=client.base_url, study=study)
    detail = _details.get(key)
    if detail is None:
        detail = await client.get_study(study.id)
        _details[key] = detail
    return detail


async def _listed_study(site_id: str, study_id: str) -> EdaStudyOverview | None:
    return next((s for s in await list_studies(site_id) if s.id == study_id), None)


async def unfiltered_entity_count(
    site_id: str,
    *,
    study_id: str,
    entity_id: str,
) -> int:
    """The entity's whole size, cached on the version the listing reports.

    A study with no ``/studies`` row reports no version, so its size reads
    again, as its detail does.
    """
    client = get_eda_client(site_id)
    overview = await _listed_study(site_id, study_id)
    if overview is None:
        return await client.count(study_id=study_id, entity_id=entity_id, filters=[])
    key = f"{study_cache_key(base_url=client.base_url, study=overview)}|{entity_id}"
    total = _entity_totals.get(key)
    if total is None:
        total = await client.count(study_id=study_id, entity_id=entity_id, filters=[])
        _entity_totals[key] = total
    return total


async def get_study_detail_for_dataset(
    site_id: str,
    dataset_id: str,
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    """The two reads every authoring call needs, in the one order that works."""
    entry = await resolve_dataset(site_id, dataset_id)
    overview = await _listed_study(site_id, entry.study_id)
    if overview is None:
        # A dataset can resolve to a study with no ``/studies`` row, which
        # reports no version, so its detail is read again every time.
        return entry, await get_eda_client(site_id).get_study(entry.study_id)
    return entry, await get_study_detail(site_id, overview)
