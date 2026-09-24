"""The control-set part of the evidence facade: persisting a control set and
sourcing its ids."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.control_sets import (
    ControlSetResponse,
    ControlSetService,
    NewControlSet,
)
from pathfinder.services.experiment import control_sourcing


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
) -> ControlSetResponse:
    """Persist a control set for one user. The caller commits the session."""
    return await ControlSetService(session).create(spec, user_id=user_id)


async def list_control_sets_for_site(
    session: AsyncSession,
    *,
    site_id: str,
    user_id: UUID,
) -> list[ControlSetResponse]:
    """Every control set this user may read on this site."""
    return await ControlSetService(session).list_for_site(
        site_id=site_id,
        user_id=user_id,
        tags=None,
    )


async def get_control_set(
    session: AsyncSession,
    control_set_id: UUID,
    user_id: UUID,
) -> ControlSetResponse:
    """One control set. Raises NotFoundError when the user may not read it."""
    return await ControlSetService(session).get(control_set_id, user_id)


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
