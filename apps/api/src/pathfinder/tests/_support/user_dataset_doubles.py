"""The recorded plasmodb user-dataset searches and one owned DESeq upload."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from veupathdb.wdk import WDKSearch

from pathfinder.services.strategies import user_dataset_searches
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "wdk"
UPLOAD_DATASET = "EDAUD_lhZ5ptRgo014J"


def wire_plasmodb_uploads(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Serve the recorded plasmodb searches and the account's one upload; the
    returned mock is the uploads read."""
    raw = json.loads((_FIXTURES / "user_dataset_searches_plasmodb.json").read_text())
    by_name = {e["urlSegment"]: WDKSearch.model_validate(e) for e in raw}

    async def definition(site_id: str, record_type: str, name: str) -> WDKSearch:
        del site_id, record_type
        return by_name[name]

    uploads = AsyncMock(
        return_value=[
            OwnedUpload(
                vdi_id="lhZ5ptRgo014J",
                name="pathfinder-uat-deseq",
                type_name="rnaseqrc",
            )
        ]
    )
    monkeypatch.setattr(user_dataset_searches, "owned_uploads", uploads)
    monkeypatch.setattr(
        user_dataset_searches,
        "get_raw_searches",
        AsyncMock(return_value=list(by_name.values())),
    )
    monkeypatch.setattr(user_dataset_searches, "read_search_definition", definition)
    return uploads
