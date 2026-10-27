from __future__ import annotations

from dataclasses import dataclass

import httpx
from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError

from pathfinder.services.audit.planning import site_organisms

logger = get_logger(__name__)


@dataclass
class HeldOrganisms:
    names: tuple[str, ...] | None = None
    read: bool = False

    async def of(self, site_id: str) -> tuple[str, ...] | None:
        if self.read:
            return self.names
        self.read = True
        try:
            self.names = await site_organisms(site_id)
        except (httpx.TransportError, VEuPathDBError, TimeoutError) as failed:
            logger.warning("Site organisms unread", site_id=site_id, error=str(failed))
        return self.names
