import json
import re
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

revision: str = "2026_11_03_0002"
down_revision: str | Sequence[str] | None = "2026_11_03_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENERIC = "An internal error occurred"
_RAW = re.compile(
    r"https?://|-> HTTP [0-9]+"
    r"|\A(Data parsing failed:|VEuPathDB service error:)"
    r"|\b(api[_-]?key|token|password|secret)="
    r"|[?&][A-Za-z_][A-Za-z0-9_.-]*="
)
_REASON = re.compile(r"(the audit job failed: [A-Za-z_][A-Za-z0-9_]*): .*\Z", re.DOTALL)
_STAGE_DETAIL = re.compile(r"\A(.*?) \((.*)\)\Z", re.DOTALL)
_PREFILTER = {
    "pattern": (
        "https?://|-> HTTP [0-9]+|Data parsing failed:|VEuPathDB service error:"
        "|the audit job failed: |(api[_-]?key|token|password|secret)="
        "|[?&][A-Za-z_][A-Za-z0-9_.-]*="
    )
}
_LABELS = (
    "BUSCO scores failed: ",
    "BUSCO scores unreached: ",
    "genome provenance failed: ",
    "genome provenance unreached: ",
)
_WRITTEN = (
    "its genome use is unknown",
    "the worker stopped during this unit 3 times",
)
_READ_UNITS = (
    "SELECT id, message FROM audit_genomes WHERE message ~ :pattern",
    "SELECT id, message FROM audit_findings WHERE message ~ :pattern",
    "SELECT id, message FROM audit_evidence WHERE message ~ :pattern",
)
_WRITE_UNITS = (
    "UPDATE audit_genomes SET message = :message WHERE id = :id",
    "UPDATE audit_findings SET message = :message WHERE id = :id",
    "UPDATE audit_evidence SET message = :message WHERE id = :id",
)


def _label_of(segment: str) -> str:
    return next((label for label in _LABELS if segment.startswith(label)), "")


def clean_text(message: str) -> str:
    kept: list[str] = []
    tainted = False
    for segment in _REASON.sub(rf"\1: {_GENERIC}", message).split("; "):
        label = _label_of(segment)
        if _RAW.search(segment[len(label) :]):
            cleaned = f"{label}{_GENERIC}"
            if not kept or kept[-1] != cleaned:
                kept.append(cleaned)
            tainted = True
        elif not tainted or label or segment in _WRITTEN:
            kept.append(segment)
    return "; ".join(kept)


def clean_stage_note(note: str) -> str:
    detail = _STAGE_DETAIL.match(note)
    if detail is None:
        return clean_text(note)
    head, inner = detail.groups()
    if _RAW.search(head):
        return _GENERIC
    return f"{head} ({_GENERIC})" if _RAW.search(inner) else note


def _clean_units(connection: Connection) -> None:
    for read, write in zip(_READ_UNITS, _WRITE_UNITS, strict=True):
        for row_id, message in connection.execute(text(read), _PREFILTER).all():
            connection.execute(
                text(write), {"id": row_id, "message": clean_text(message)}
            )


def _clean_runs(connection: Connection) -> None:
    connection.execute(
        text(
            "UPDATE audit_findings AS finding SET message = :generic "
            "FROM audit_runs AS run WHERE finding.run_id = run.id "
            "AND finding.status IN ('unreached', 'unread') "
            "AND finding.message = run.stages->>'targetFailure'"
        ),
        {"generic": _GENERIC},
    )
    connection.execute(
        text(
            "UPDATE audit_runs SET stages = jsonb_set("
            "stages, '{targetFailure}', to_jsonb(CAST(:generic AS text))) "
            "WHERE stages->>'targetFailure' IS NOT NULL"
        ),
        {"generic": _GENERIC},
    )
    rows = connection.execute(
        text("SELECT id, stages FROM audit_runs WHERE stages::text ~ :pattern"),
        _PREFILTER,
    ).all()
    for run_id, stages in rows:
        match stages:
            case {"halted": str() as halted}:
                stages["halted"] = _REASON.sub(rf"\1: {_GENERIC}", halted, count=1)
            case _:
                pass
        match stages:
            case {"stages": list() as held}:
                for stage in held:
                    stage["message"] = clean_stage_note(stage["message"])
            case _:
                pass
        connection.execute(
            text(
                "UPDATE audit_runs SET stages = CAST(:stages AS jsonb) WHERE id = :id"
            ),
            {"id": run_id, "stages": json.dumps(stages)},
        )


def _clean_result(result: dict[str, object]) -> None:
    match result:
        case {"evidenceUnread": list() as unread}:
            result["evidenceUnread"] = [clean_text(reason) for reason in unread]
        case _:
            pass
    match result:
        case {"correctionReason": str() as reason}:
            result["correctionReason"] = clean_text(reason)
        case _:
            pass
    match result:
        case {"reason": str() as reason}:
            result["reason"] = clean_text(reason)
        case _:
            pass
    match result:
        case {"orthologs": {"reason": str() as reason} as orthologs}:
            orthologs["reason"] = clean_text(reason)
        case _:
            pass


def _clean_payloads(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "SELECT id, payload FROM audit_evidence "
            "WHERE payload IS NOT NULL AND kind = 'confirmation' "
            "AND payload::text ~ :pattern"
        ),
        _PREFILTER,
    ).all()
    for row_id, payload in rows:
        _clean_result(payload["confirmation"]["result"])
        connection.execute(
            text(
                "UPDATE audit_evidence SET payload = CAST(:payload AS jsonb) "
                "WHERE id = :id"
            ),
            {"id": row_id, "payload": json.dumps(payload)},
        )


def scrub_raw_text(connection: Connection) -> None:
    _clean_runs(connection)
    _clean_units(connection)
    _clean_payloads(connection)


def upgrade() -> None:
    scrub_raw_text(op.get_bind())


def downgrade() -> None:
    pass
