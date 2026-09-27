"""A saved control set served to the control test tools without a database."""

from __future__ import annotations

from types import ModuleType
from uuid import UUID

import pytest
from assistant_core.platform.db import DBSessionFactory

from pathfinder.domain.evidence import NamedControlSet
from pathfinder.services.evidence.control_sets import (
    SavedControls,
    UnknownControlSetError,
)

SAVED_SET_ID = "5f1c6a2e-0000-4000-8000-00000000c0de"
# The saved set as the conversation holds it attached.
SAVED_SET = NamedControlSet(id=SAVED_SET_ID, name="Saved controls")


def saved_set(
    positive_ids: list[str], negative_ids: list[str] | None = None
) -> SavedControls:
    """The one saved set of the site, holding these ids."""
    return SavedControls(
        control_set_id=SAVED_SET_ID,
        name="Saved controls",
        positive_ids=positive_ids,
        negative_ids=negative_ids or [],
    )


def serve_saved_controls(
    monkeypatch: pytest.MonkeyPatch, reader: ModuleType, saved: SavedControls
) -> None:
    """``reader`` reads ``saved`` as the site's only saved set."""

    async def read(
        db_session_factory: DBSessionFactory | None,
        control_set_id: str,
        *,
        site_id: str,
        user_id: UUID | None,
    ) -> SavedControls:
        del db_session_factory, site_id, user_id
        if control_set_id != saved.control_set_id:
            raise UnknownControlSetError(control_set_id, [])
        return saved

    monkeypatch.setattr(reader, "saved_control_set", read)
