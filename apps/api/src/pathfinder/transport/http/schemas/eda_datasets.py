"""Response shapes of the researcher's own datasets."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict


class EdaOwnDatasetResponse(CamelModel):
    """One of the researcher's uploads. ``dataset_id`` is set once the study opens."""

    model_config = ConfigDict(from_attributes=True)

    vdi_id: str
    name: str
    created: datetime
    state: Literal["installing", "waiting", "installed", "failed"]
    message: str | None
    dataset_id: str | None
    can_subset: bool
    can_export_rows: bool


class EdaOwnDatasetListResponse(CamelModel):
    """The uploads, newest first, and the site page where the researcher uploads."""

    model_config = ConfigDict(from_attributes=True)

    datasets: list[EdaOwnDatasetResponse]
    upload_url: str
