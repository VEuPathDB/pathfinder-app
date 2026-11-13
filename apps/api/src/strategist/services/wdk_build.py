"""The build number a VEuPathDB site's service root reports."""

from __future__ import annotations

from pydantic import ConfigDict
from veupathdb.errors import validate_response
from veupathdb.model import CamelModel
from veupathdb.wdk import get_wdk_client


class _ServiceRoot(CamelModel):
    model_config = ConfigDict(extra="ignore")

    build_number: str


async def site_build(site_id: str) -> str:
    """The build number the site's service root reports."""
    raw = await get_wdk_client(site_id).get("/")
    return validate_response(_ServiceRoot, raw, "WDK service root").build_number


__all__ = ["site_build"]
