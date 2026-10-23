"""A verdict a model writes in a conversation is stored under its caller and read back by that caller alone."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.domain.audit.verdicts import GeneModelVerdict, read_cite
from pathfinder.services.audit.verdicts import (
    AuditCaller,
    conversation_verdicts,
    record_verdict,
)
from pathfinder.tests._support.audit import seed_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_MODEL = "test:auditor"
_VERDICT = GeneModelVerdict(
    genes=("EXA_0001", "EXR_0001"),
    model_genome="Examplea alpha A",
    verdict="error",
    error_type="intact_gene_called_pseudogene",
    certainty="high",
    cause="The strain gene keeps the reading frame its reference gene has.",
    cites=(read_cite("audit_pseudogene_call", "EXA_0001", "EXR_0001"),),
)


async def test_a_verdict_is_stored_under_its_caller() -> None:
    owner = await seed_thread()
    other = await seed_thread()
    caller = AuditCaller(
        user_id=owner.user_id,
        conversation_id=owner.conversation_id,
        site_id="plasmodb",
    )

    verdict_id = await record_verdict(
        caller=caller, origin="auditor", verdict=_VERDICT, model_id=_MODEL
    )

    (stored,) = await conversation_verdicts(owner.conversation_id, owner.user_id)
    assert (stored.id, stored.origin, stored.verdict, stored.review) == (
        verdict_id,
        "auditor",
        _VERDICT,
        None,
    )
    assert (stored.run_id, stored.finding_id) == (None, None)
    assert stored.model_dump(by_alias=True, mode="json")["verdict"]["modelGenome"] == (
        "Examplea alpha A"
    )
    assert await conversation_verdicts(owner.conversation_id, other.user_id) == []
    assert await conversation_verdicts(other.conversation_id, other.user_id) == []


async def test_a_verdict_with_no_thread_is_in_no_conversation() -> None:
    owner = await seed_thread()
    caller = AuditCaller(
        user_id=owner.user_id, conversation_id=None, site_id="plasmodb"
    )

    verdict_id = await record_verdict(
        caller=caller, origin="lead", verdict=_VERDICT, model_id=_MODEL
    )

    assert verdict_id > 0
    assert await conversation_verdicts(owner.conversation_id, owner.user_id) == []
    assert await conversation_verdicts(uuid4(), owner.user_id) == []
