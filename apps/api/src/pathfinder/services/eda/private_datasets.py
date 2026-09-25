"""The researcher's own RNA-Seq uploads on one site, read from VDI and EDA as they stand.

The researcher uploads and deletes on the site. PathFinder lists what the
account owns and opens an installed study; it keeps no row of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from assistant_core.platform.logging import get_logger
from veupathdb.wdk import (
    RNASEQRC,
    VdiClient,
    VdiDatasetGoneError,
    VdiDatasetListEntry,
    VdiInstallDisposition,
    VdiServiceError,
    eda_dataset_id,
    get_site,
    get_vdi_client,
)

from pathfinder.services.eda.catalog import (
    OWN_SOURCE_TYPE,
    StudyCard,
    UnknownEdaDatasetError,
    refresh_permissions,
    resolve_dataset,
)

logger = get_logger(__name__)

NO_REASON = "VEuPathDB could not install the dataset and gave no reason."
NOT_VISIBLE_YET = "Installed; the study is not visible yet."

# The site's own page for a researcher's datasets, where uploads are made.
_WORKSPACE_PATH = "/app/workspace/datasets"

type OwnDatasetState = Literal["installing", "waiting", "installed", "failed"]


@dataclass(frozen=True, slots=True)
class OwnDataset:
    """One upload as the tab lists it. ``dataset_id`` is set once the study is readable."""

    vdi_id: str
    name: str
    created: datetime
    state: OwnDatasetState
    message: str | None = None
    dataset_id: str | None = None
    study_id: str | None = None
    can_subset: bool = False
    can_export_rows: bool = False


@dataclass(frozen=True, slots=True)
class OwnDatasets:
    """The uploads, newest first, and the site page where the researcher uploads."""

    datasets: list[OwnDataset]
    upload_url: str


async def own_datasets(site_id: str) -> OwnDatasets:
    """The researcher's count uploads on this site, as VDI and EDA report them now."""
    site = get_site(site_id)
    client = get_vdi_client(site_id)
    listing = await client.list_datasets(site.project_id)
    rows = sorted(
        (
            row
            for row in listing
            if row.type.name == RNASEQRC.name
            and row.type.version == RNASEQRC.version
            and site.project_id in row.install_targets
        ),
        key=lambda row: row.created,
        reverse=True,
    )
    refreshed = False
    datasets: list[OwnDataset] = []
    for row in rows:
        dataset = await _own(site.project_id, client, row)
        if dataset is None:
            continue
        if dataset.state == "installed":
            dataset, refreshed = await _readable(site_id, dataset, refreshed=refreshed)
        datasets.append(dataset)
    return OwnDatasets(
        datasets=datasets, upload_url=f"{site.web_base_url}{_WORKSPACE_PATH}"
    )


async def _own(
    project_id: str, client: VdiClient, row: VdiDatasetListEntry
) -> OwnDataset | None:
    """One row's state. A failed row reads the dataset, because only it holds VDI's text."""
    listed = OwnDataset(
        vdi_id=row.dataset_id, name=row.name, created=row.created, state="installing"
    )
    match row.status.disposition(project_id):
        case VdiInstallDisposition.FAILED:
            try:
                details = await client.get(row.dataset_id)
            except VdiDatasetGoneError:
                return None
            text = " ".join(details.status.failure_messages(project_id)) or NO_REASON
            return replace(listed, state="failed", message=text)
        case VdiInstallDisposition.INSTALLED:
            return replace(listed, state="installed")
        case _:
            return listed


async def _readable(
    site_id: str, installed: OwnDataset, *, refreshed: bool
) -> tuple[OwnDataset, bool]:
    """The installed dataset with its study permissions, and whether the map was re-read.

    A study installs after this credential's permission map was read, so a miss
    re-reads the map, once per listing.
    """
    dataset_id = eda_dataset_id(installed.vdi_id)
    try:
        entry = await resolve_dataset(site_id, dataset_id)
    except UnknownEdaDatasetError:
        if refreshed:
            return replace(installed, state="waiting", message=NOT_VISIBLE_YET), True
        refresh_permissions(site_id)
        return await _readable(site_id, installed, refreshed=True)
    return (
        replace(
            installed,
            dataset_id=dataset_id,
            study_id=entry.study_id,
            can_subset=entry.action_authorization.subsetting,
            can_export_rows=entry.action_authorization.results_all,
        ),
        refreshed,
    )


async def own_dataset_cards(
    site_id: str, query: str, limit: int = 5
) -> list[StudyCard]:
    """The researcher's installed uploads as study cards, the names matching the query first.

    VDI answering with an error leaves the site's own ranking to stand alone.
    """
    try:
        found = await own_datasets(site_id)
    except VdiServiceError as exc:
        logger.warning("The researcher's datasets were not read", error=str(exc))
        return []
    needle = query.strip().lower()
    cards = [
        StudyCard(
            dataset_id=dataset_id,
            study_id=study_id,
            display_name=dataset.name,
            short_display_name=dataset.name,
            description="",
            source_type=OWN_SOURCE_TYPE,
            can_subset=dataset.can_subset,
            can_export_rows=dataset.can_export_rows,
            sites=[site_id],
        )
        for dataset in found.datasets
        if (dataset_id := dataset.dataset_id) is not None
        and (study_id := dataset.study_id) is not None
    ]
    cards.sort(key=lambda card: needle not in card.display_name.lower())
    return cards[:limit]
