"""The researcher's upload each criterion of a spec runs on: the one its
user-dataset parameter binds, or the one whose study its analysis reads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import to_wire
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import EDA_USER_DATASET_PREFIX, WDKSearch, eda_dataset_id

from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies.user_dataset_searches import (
    OwnedUpload,
    dataset_parameter,
    owned_uploads,
)

logger = get_logger(__name__)


def _bound_ids(criterion: Criterion, searches: Mapping[str, WDKSearch]) -> set[str]:
    """The upload ids the criterion reads: its analysis's study, and the value
    of the dataset parameter a user-dataset search declares."""
    study = None if criterion.analysis is None else criterion.analysis.dataset_id
    ids = {study} if study and study.startswith(EDA_USER_DATASET_PREFIX) else set()
    search = searches.get(criterion.search_name)
    parameter = None if search is None else dataset_parameter(search)
    held = None if parameter is None else criterion.resolved_params.get(parameter.name)
    if held is not None:
        ids.add(to_wire(held.value))
    return ids


def uploads_run_on(
    spec: OperationalSpec,
    searches: Mapping[str, WDKSearch],
    uploads: Sequence[OwnedUpload],
) -> dict[str, OwnedUpload]:
    """Each criterion's upload, by criterion id, for the criteria that run on an
    upload. A gene list is bound by its VDI id, an EDA upload by its study."""
    named = {
        upload_id: upload
        for upload in uploads
        for upload_id in (upload.vdi_id, eda_dataset_id(upload.vdi_id))
    }
    found: dict[str, OwnedUpload] = {}
    for criterion in spec.criteria:
        for upload_id in sorted(_bound_ids(criterion, searches)):
            if upload_id in named:
                found[criterion.id] = named[upload_id]
    return found


async def uploads_the_specs_run_on(
    site_id: str,
    specs: Sequence[OperationalSpec | None],
    sheets: Mapping[str, WDKSearch],
) -> dict[str, OwnedUpload]:
    """Each criterion's upload, with the uploads read once from the site under
    the researcher's token. A listing the site does not answer names no upload."""
    held = [spec for spec in specs if spec is not None]
    if not any(_bound_ids(c, sheets) for spec in held for c in spec.criteria):
        return {}
    try:
        uploads = await owned_uploads(site_id)
    except (VEuPathDBError, OSError) as exc:
        logger.warning("uploads unreadable", site_id=site_id, error=str(exc))
        return {}
    found: dict[str, OwnedUpload] = {}
    for spec in held:
        found |= uploads_run_on(spec, sheets, uploads)
    return found


__all__ = ["uploads_run_on", "uploads_the_specs_run_on"]
