"""Publishing a gene set to the researcher's VEuPathDB workspace, and reading it back.

Publication is opt-in and one-way. PathFinder keeps the set; the VDI id it
records points at a durable artifact the site owns.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field
from veupathdb.model import CamelModel
from veupathdb.wdk import (
    GENELIST_PLUGIN_NAME,
    GENELIST_PLUGIN_VERSION,
    VdiDatasetGoneError,
    VdiDatasetPostMeta,
    VdiDatasetType,
    VdiImportStatus,
    VdiUploadStatus,
    VdiVisibility,
    get_site,
    get_vdi_client,
)

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.operations import GeneSetService

_GENELIST = VdiDatasetType(name=GENELIST_PLUGIN_NAME, version=GENELIST_PLUGIN_VERSION)


class VdiPublicationRequest(CamelModel):
    """What the researcher chooses when publishing a set."""

    name: str = Field(min_length=3, max_length=1024)
    visibility: VdiVisibility = VdiVisibility.PRIVATE


class VdiPublication(CamelModel):
    """The dataset a publish created, and where the researcher reads it."""

    vdi_id: str
    dataset_url: str
    site_id: str
    gene_count: int


class VdiPublicationStatus(CamelModel):
    """Where a published dataset stands on the three axes VDI reports."""

    vdi_id: str
    dataset_url: str
    site_id: str
    upload: VdiUploadStatus
    import_status: VdiImportStatus | None = None
    installed_targets: list[str]
    installed: bool
    is_terminal: bool


def _summary(gene_count: int, set_name: str) -> str:
    return f"{gene_count} genes published from the PathFinder gene set '{set_name}'."


async def publish_to_vdi(
    service: GeneSetService,
    user_id: UUID,
    gene_set_id: str,
    *,
    name: str,
    visibility: VdiVisibility,
) -> VdiPublication:
    """Publish a gene set to the signed-in researcher's VEuPathDB workspace.

    :raises NotFoundError: If the set is missing or held by another user.
    :raises VdiServiceError: If the dataset service refuses the upload.
    """
    gene_set = await service.get_for_user(user_id, gene_set_id)
    site = get_site(gene_set.site_id)
    details = VdiDatasetPostMeta(
        type=_GENELIST,
        install_targets=[site.project_id],
        name=name,
        summary=_summary(len(gene_set.gene_ids), gene_set.name),
        visibility=visibility,
    )
    created = await get_vdi_client(gene_set.site_id).create_genelist(
        details=details, gene_ids=gene_set.gene_ids
    )
    await service.record_vdi_publication(gene_set, created.dataset_id)
    return VdiPublication(
        vdi_id=created.dataset_id,
        dataset_url=site.dataset_url(created.dataset_id),
        site_id=gene_set.site_id,
        gene_count=len(gene_set.gene_ids),
    )


async def vdi_publication_status(
    service: GeneSetService, user_id: UUID, gene_set_id: str
) -> VdiPublicationStatus:
    """Read where a published gene set stands on the site that holds it.

    :raises NotFoundError: If the set was never published, or the researcher
        removed the dataset on the site.
    """
    gene_set = await service.get_for_user(user_id, gene_set_id)
    if gene_set.vdi_id is None:
        msg = f"Gene set {gene_set_id} is not published to a VEuPathDB workspace."
        raise NotFoundError(detail=msg)
    site = get_site(gene_set.site_id)
    try:
        details = await get_vdi_client(gene_set.site_id).get(gene_set.vdi_id)
    except VdiDatasetGoneError as exc:
        await service.record_vdi_publication(gene_set, None)
        msg = f"The published dataset for gene set {gene_set_id} no longer exists."
        raise NotFoundError(detail=msg) from exc
    installed = details.installed_targets()
    return VdiPublicationStatus(
        vdi_id=details.dataset_id,
        dataset_url=site.dataset_url(details.dataset_id),
        site_id=gene_set.site_id,
        upload=details.status.upload.status,
        import_status=(
            None if details.status.import_ is None else details.status.import_.status
        ),
        installed_targets=installed,
        installed=set(details.install_targets) <= set(installed) and bool(installed),
        is_terminal=details.status.is_terminal(),
    )
