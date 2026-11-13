"""Worker-side body of one review job of a finished audit run."""

from __future__ import annotations

from time import monotonic

from assistant_core.platform.db import async_session_factory
from pydantic import JsonValue

from strategist.ai.audit.review import review_until_done
from strategist.assistants.registry import assistant_role_models
from strategist.jobs.auth_context import attach_application
from strategist.platform.errors import ProviderKeyError
from strategist.platform.identity import AUDIT_ASSISTANT_ID
from strategist.platform.log_ids import LogIds, log_ids_scope
from strategist.platform.model_keys import attach_keyring
from strategist.platform.tiers import REVIEW_ROLE
from strategist.services.audit.lease_pool import audit_lease
from strategist.services.audit.reviews import (
    ReviewedRun,
    ReviewJob,
    record_progress,
    reviewed_run,
)
from strategist.services.provider_keys import load_keyring, record_refusals
from strategist.services.turn_payment import turn_payment

REVIEW_FAILED = "the review job failed"


async def _reviewed(run: ReviewedRun) -> None:
    model_id = assistant_role_models(AUDIT_ASSISTANT_ID, {})[REVIEW_ROLE]
    keyring = await load_keyring(run.user_id)
    try:
        async with async_session_factory() as session:
            await turn_payment(session, run.user_id, [model_id])
    except ProviderKeyError as refused:
        await record_progress(run, "stopped", refused.title)
        return
    with attach_keyring(keyring) as keys:
        try:
            await review_until_done(run, model_id=model_id, started=monotonic())
        finally:
            await record_refusals(run.user_id, keys.refusals)


async def _review(run: ReviewedRun) -> None:
    try:
        await _reviewed(run)
    except Exception as error:
        await record_progress(
            run, "stopped", f"{REVIEW_FAILED}: {type(error).__name__}"
        )
        raise


async def run_review_job(payload: dict[str, JsonValue]) -> None:
    job = ReviewJob.model_validate(payload)
    async with attach_application(), audit_lease(job.run_id) as held:
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
