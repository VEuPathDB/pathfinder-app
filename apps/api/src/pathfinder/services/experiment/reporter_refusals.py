from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from veupathdb.errors import VEuPathDBError

from pathfinder.services.experiment.column_tally import ColumnTallyRefusedError

REFUSAL_LIFETIME_SECONDS = 3600.0
_SERVER_ERROR = 500


@dataclass(frozen=True)
class ReporterRefusal:
    site_id: str
    reporter: str
    status: int
    until: float


class ReporterRefusedError(ColumnTallyRefusedError):
    def __init__(self, refusal: ReporterRefusal) -> None:
        self.refusal = refusal
        super().__init__(
            f"The site refuses its {refusal.reporter} column report "
            f"(HTTP {refusal.status}), so no column is counted that way on "
            f"{refusal.site_id} for now."
        )


def reporter_status(error: BaseException | None, reporter: str) -> int | None:
    match error:
        case httpx.HTTPStatusError(request=request, response=response) if (
            request.url.path.endswith(f"/reports/{reporter}")
        ):
            return response.status_code
        case VEuPathDBError():
            return reporter_status(error.__cause__, reporter)
        case _:
            return None


@dataclass
class ReporterRefusals:
    clock: Callable[[], float] = time.monotonic
    _held: dict[tuple[str, str], ReporterRefusal] = field(default_factory=dict)

    def held(self, site_id: str, reporter: str) -> ReporterRefusal | None:
        refusal = self._held.get((site_id, reporter))
        if refusal is None or refusal.until > self.clock():
            return refusal
        del self._held[(site_id, reporter)]
        return None

    def refused(
        self, site_id: str, reporter: str, error: BaseException
    ) -> ReporterRefusal | None:
        status = reporter_status(error, reporter)
        if status is None or status < _SERVER_ERROR:
            return None
        refusal = ReporterRefusal(
            site_id=site_id,
            reporter=reporter,
            status=status,
            until=self.clock() + REFUSAL_LIFETIME_SECONDS,
        )
        self._held[(site_id, reporter)] = refusal
        return refusal

    def clear(self) -> None:
        self._held.clear()


REPORTER_REFUSALS = ReporterRefusals()
