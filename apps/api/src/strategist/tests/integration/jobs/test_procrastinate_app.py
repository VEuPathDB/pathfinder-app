from __future__ import annotations

import pytest

from strategist.jobs.app import procrastinate_app
from strategist.jobs.tasks import echo_task


@pytest.mark.asyncio
async def test_defer_echo_task(db_cleaner: None, patch_app_db_engine: None) -> None:
    del db_cleaner, patch_app_db_engine
    async with procrastinate_app.open_async():
        job_id = await echo_task.defer_async(message="hello")
        assert isinstance(job_id, int)
        assert job_id > 0
