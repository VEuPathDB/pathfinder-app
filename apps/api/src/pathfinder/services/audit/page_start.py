"""Starting a stored audit run again from its page: a resume after a halt, a retry of what a
finished run left unread or unreached."""

from __future__ import annotations

from uuid import UUID

from pathfinder.domain.audit.run_state import RunAction
from pathfinder.platform.audit_errors import AuditNotStartableError
from pathfinder.services.audit.job import start_run
from pathfinder.services.audit.queue import working
from pathfinder.services.audit.runs import RunOwner
from pathfinder.services.audit.views import AuditRunView, run_view

_REVIEWS_RUNNING = "this run's reviews are running; start it again when they finish"
_WORKING = "a task of this run is already queued or running"
_DELETED = "the conversation that started this run was deleted"

_OFFERED: dict[RunAction | None, str] = {
    None: "this run offers no start now",
    "resume": "this run offers a resume, not a retry",
    "retry": "this run offers a retry, not a resume",
}


async def start_from_page(
    run_id: UUID, user_id: UUID, action: RunAction
) -> AuditRunView:
    view = await run_view(run_id, user_id)
    if view.reviews_running:
        raise AuditNotStartableError(_REVIEWS_RUNNING)
    if view.action != action:
        raise AuditNotStartableError(_OFFERED[view.action])
    if await working(run_id):
        raise AuditNotStartableError(_WORKING)
    if view.run.conversation_id is None:
        raise AuditNotStartableError(_DELETED)
    owner = RunOwner(user_id=user_id, conversation_id=view.run.conversation_id)
    await start_run(run_id, owner, retry_unreached=action == "retry")
    return await run_view(run_id, user_id)
