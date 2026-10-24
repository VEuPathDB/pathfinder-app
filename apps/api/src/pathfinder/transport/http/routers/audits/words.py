from fastapi import APIRouter

from pathfinder.services.audit.words import AUDIT_WORDS, AuditWords

router = APIRouter()


@router.get(
    "/words",
    response_model=AuditWords,
    summary="The words an audit page names each value the audit routes send by.",
)
async def get_audit_words() -> AuditWords:
    return AUDIT_WORDS
