from __future__ import annotations

from typing import override

from strategist.tests._support.recording_wdk import RecordingWDK


class CountingStrategyAPI(RecordingWDK):
    def __init__(self) -> None:
        super().__init__(next_id=1000)

    @override
    async def delete_orphaned_steps(self, step_ids: list[int]) -> list[int]:
        self._record("delete_orphaned_steps", step_ids=step_ids)
        return await super().delete_orphaned_steps(step_ids)
