"""Worker-side body of one review job of a finished audit run."""

from __future__ import annotations

from time import monotonic

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.lease import advisory_lease
from pydantic import JsonValue

from pathfinder.ai.audit.review import review_until_done
from pathfinder.assistants.registry import assistant_role_models
from pathfinder.domain.audit.verdicts import ReviewProgress
from pathfinder.jobs.auth_context import attach_application
from pathfinder.platform.errors import ProviderKeyError
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID
from pathfinder.platform.log_ids import LogIds, log_ids_scope
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.platform.tiers import REVIEW_ROLE
from pathfinder.services.audit.queue import audit_lock
from pathfinder.services.audit.reviews import (
    ReviewedRun,
    ReviewJob,
    reviewed_run,
    set_progress,
)
from pathfinder.services.provider_keys import load_keyring, record_refusals
from pathfinder.services.turn_payment import turn_payment


async def _review(run: ReviewedRun) -> None:
    model_id = assistant_role_models(AUDIT_ASSISTANT_ID, {})[REVIEW_ROLE]
    keyring = await load_keyring(run.user_id)
    try:
        async with async_session_factory() as session:
            await turn_payment(session, run.user_id, [model_id])
    except ProviderKeyError as refused:
        await set_progress(
            run.run_id, ReviewProgress(status="stopped", message=refused.title)
        )
        return
    with attach_keyring(keyring) as keys:
        try:
            await review_until_done(run, model_id=model_id, started=monotonic())
        finally:
            await record_refusals(run.user_id, keys.refusals)


async def run_review_job(payload: dict[str, JsonValue]) -> None:
    job = ReviewJob.model_validate(payload)
    async with attach_application(), advisory_lease(audit_lock(job.run_id)) as held:
        run = await reviewed_run(job.run_id) if held else None
        if run is None or run.status != "finished":
            return
        ids = LogIds(
            run_id=run.run_id,
            user_id=run.user_id,
            conversation_id=run.conversation_id,
            site_id=run.site_id,
        )
        with log_ids_scope(ids):
            await _review(run)
