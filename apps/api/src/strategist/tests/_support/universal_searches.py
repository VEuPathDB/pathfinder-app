from __future__ import annotations

from veupathdb_mcp.catalog import SearchMatch

TEXT_SEARCH = SearchMatch(
    name="GenesByText",
    display_name="Gene Text Search",
    description="Search all text fields for genes matching a keyword or phrase.",
    record_type="transcript",
    category="general",
    returns="transcript",
)
