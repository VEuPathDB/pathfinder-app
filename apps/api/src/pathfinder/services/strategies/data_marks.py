"""What the site says each criterion of a spec runs on: the type of the upload it
reads, and the assay of the dataset record its study or its search names."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import EDA_USER_DATASET_PREFIX, WDKSearch
from veupathdb_mcp.catalog import dataset_assay, study_assay

from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies.bound_uploads import uploads_the_specs_run_on
from pathfinder.services.strategies.text_queries import search_definitions
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload

logger = get_logger(__name__)


def _curated_studies(criteria: Sequence[Criterion]) -> list[str]:
    studies = (c.analysis.dataset_id for c in criteria if c.analysis is not None)
    return sorted(
        {study for study in studies if not study.startswith(EDA_USER_DATASET_PREFIX)}
    )


async def marks_with_uploads(
    site_id: str,
    specs: Sequence[OperationalSpec | None],
    uploads: Mapping[str, OwnedUpload],
) -> DataMarks:
    """The marks of every criterion of the specs, beside the uploads they read.

    A catalog the site does not answer marks no search and no study.
    """
    criteria = [c for spec in specs if spec is not None for c in spec.criteria]
    searches: dict[str, str] = {}
    studies: dict[str, str] = {}
    try:
        for name in sorted({c.search_name for c in criteria if c.search_name}):
            if (assay := await dataset_assay(site_id, name)) is not None:
                searches[name] = assay
        for study in _curated_studies(criteria):
            if (assay := await study_assay(site_id, study)) is not None:
                studies[study] = assay
    except (VEuPathDBError, OSError) as exc:
        logger.warning("catalog marks unreadable", site_id=site_id, error=str(exc))
    return DataMarks(
        uploads={c: u.type_name for c, u in uploads.items()},
        studies=studies,
        searches=searches,
    )


async def read_data_marks(
    site_id: str, specs: Sequence[OperationalSpec | None]
) -> DataMarks:
    """The marks of every criterion of the specs, with the uploads they read."""
    sheets: dict[str, WDKSearch] = {}
    for spec in specs:
        sheets |= await search_definitions(site_id, spec)
    uploads = await uploads_the_specs_run_on(site_id, specs, sheets)
    return await marks_with_uploads(site_id, specs, uploads)
