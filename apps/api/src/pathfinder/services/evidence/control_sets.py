"""The control-set part of the evidence facade: persisting a control set and
sourcing its ids."""

from collections.abc import Sequence
from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.control_sets import (
    ControlSetResponse,
    ControlSetService,
    NewControlSet,
)
from pathfinder.services.experiment import control_sourcing


class SavedControls(CamelModel):
    """A saved control set as a control test runs it."""

    model_config = ConfigDict(frozen=True)

    control_set_id: str
    name: str
    positive_ids: list[str]
    negative_ids: list[str]
    conversation_id: UUID | None = None
    """The thread the set was saved in, or None for a set saved outside one."""


class UnknownControlSetError(NotFoundError):
    """A control set id that names no set the user may read on the site."""

    def __init__(
        self, control_set_id: str, saved: Sequence[ControlSetResponse]
    ) -> None:
        named = "; ".join(f"{cs.id} ({cs.name})" for cs in saved) or "none"
        super().__init__(
            title="Control set not found",
            detail=(
                f"control_set_id {control_set_id!r} names no control set saved on "
                f"this site. The saved control sets: {named}."
            ),
        )


def new_control_set(
    *,
    name: str,
    site_id: str,
    record_type: str,
    positive_ids: list[str],
    negative_ids: list[str],
    source: str,
) -> NewControlSet:
    """The input a control set is created from."""
    return NewControlSet(
        name=name,
        site_id=site_id,
        record_type=record_type,
        positive_ids=positive_ids,
        negative_ids=negative_ids,
        source=source,
    )


async def create_control_set(
    session: AsyncSession,
    spec: NewControlSet,
    *,
    user_id: UUID,
    conversation_id: UUID | None,
) -> ControlSetResponse:
    """Persist a control set for one user, saved in ``conversation_id`` when
    one is given. The caller commits the session."""
    return await ControlSetService(session).create(
        spec, user_id=user_id, conversation_id=conversation_id
    )


def _saved(held: ControlSetResponse) -> SavedControls:
    return SavedControls(
        control_set_id=held.id,
        name=held.name,
        positive_ids=held.positive_ids,
        negative_ids=held.negative_ids,
        conversation_id=held.conversation_id,
    )


async def saved_control_sets(
    db_session_factory: DBSessionFactory | None,
    *,
    site_id: str,
    user_id: UUID | None,
) -> list[SavedControls]:
    """Every control set this user may read on this site. A turn with no user
    reads none."""
    if db_session_factory is None or user_id is None:
        return []
    async with db_session_factory() as session:
        held = await ControlSetService(session).list_for_site(
            site_id=site_id, user_id=user_id, tags=None
        )
    return [_saved(cs) for cs in held]


async def get_control_set(
    session: AsyncSession,
    control_set_id: UUID,
    user_id: UUID,
) -> ControlSetResponse:
    """One control set. Raises NotFoundError when the user may not read it."""
    return await ControlSetService(session).get(control_set_id, user_id)


def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


async def saved_control_set(
    db_session_factory: DBSessionFactory | None,
    control_set_id: str,
    *,
    site_id: str,
    user_id: UUID | None,
) -> SavedControls:
    """The saved set a control test runs, read under this user on this site.

    Raises UnknownControlSetError, which names the sets the user may read on
    the site, when the id names none of them. A turn with no user reads none.
    """
    if db_session_factory is None or user_id is None:
        raise UnknownControlSetError(control_set_id, [])
    parsed = _as_uuid(control_set_id)
    async with db_session_factory() as session:
        service = ControlSetService(session)
        held = None if parsed is None else await service.find(parsed, user_id)
        if held is not None and held.site_id == site_id:
            return _saved(held)
        saved = await service.list_for_site(site_id=site_id, user_id=user_id, tags=None)
    raise UnknownControlSetError(control_set_id, saved)


async def validate_control_ids(
    site_id: str,
    gene_ids: list[str],
    *,
    record_type: str = "transcript",
) -> control_sourcing.ResolvedControls:
    """Split gene ids WDK recognizes from the ones it does not."""
    return await control_sourcing.validate_control_ids(
        site_id,
        gene_ids,
        record_type=record_type,
    )


async def control_ids_from_saved_gene_set(
    user_id: UUID,
    gene_set_id: str,
) -> list[str]:
    """The gene ids a saved gene set holds."""
    return await control_sourcing.control_ids_from_saved_gene_set(user_id, gene_set_id)


async def control_ids_from_strategy(
    session: AsyncSession,
    strategy_id: UUID,
    site_id: str,
    user_id: UUID,
) -> control_sourcing.StrategyControls:
    """The result gene ids of another strategy, or the reason there are none."""
    return await control_sourcing.control_ids_from_strategy(
        session,
        strategy_id,
        site_id,
        user_id,
    )
