from collections.abc import Sequence

from alembic import op

revision: str = "2026_11_03_0002"
down_revision: str | Sequence[str] | None = "2026_11_03_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE audit_runs SET stages = jsonb_set(stages, '{halted}', to_jsonb("
        "regexp_replace(stages->>'halted', "
        r"'^(the audit job failed: [A-Za-z_][A-Za-z0-9_]*): .*$', "
        r"'\1: An internal error occurred')::text)) "
        "WHERE starts_with(stages->>'halted', 'the audit job failed: ')"
    )
    op.execute(
        "UPDATE audit_genomes SET message = regexp_replace(message, "
        r"'(the audit job failed: [A-Za-z_][A-Za-z0-9_]*): .*$', "
        r"'\1: An internal error occurred') "
        "WHERE position('the audit job failed: ' in message) > 0"
    )
    op.execute(
        "UPDATE audit_findings SET message = regexp_replace(message, "
        r"'(the audit job failed: [A-Za-z_][A-Za-z0-9_]*): .*$', "
        r"'\1: An internal error occurred') "
        "WHERE position('the audit job failed: ' in message) > 0"
    )
    op.execute(
        "UPDATE audit_evidence SET message = regexp_replace(message, "
        r"'(the audit job failed: [A-Za-z_][A-Za-z0-9_]*): .*$', "
        r"'\1: An internal error occurred') "
        "WHERE position('the audit job failed: ' in message) > 0"
    )
    op.execute(
        "UPDATE audit_findings AS finding "
        "SET message = 'An internal error occurred' "
        "FROM audit_runs AS run "
        "WHERE finding.run_id = run.id AND finding.status IN ('unreached', 'unread') "
        "AND finding.message = run.stages->>'targetFailure'"
    )
    op.execute(
        "UPDATE audit_runs SET stages = jsonb_set(stages, '{targetFailure}', "
        "to_jsonb('An internal error occurred'::text)) "
        "WHERE jsonb_typeof(stages->'targetFailure') = 'string'"
    )
    op.execute(
        "UPDATE audit_genomes SET message = 'An internal error occurred' "
        "WHERE status IN ('failed', 'unreached') "
        "AND message ~ '(https?://|-> HTTP [0-9]+)'"
    )
    op.execute(
        "UPDATE audit_findings SET message = 'An internal error occurred' "
        "WHERE status IN ('failed', 'unreached') "
        "AND message ~ '(https?://|-> HTTP [0-9]+)'"
    )
    op.execute(
        "UPDATE audit_evidence SET message = 'An internal error occurred' "
        "WHERE status IN ('failed', 'unreached') "
        "AND message ~ '(https?://|-> HTTP [0-9]+)'"
    )
    op.execute(
        "UPDATE audit_runs SET stages = jsonb_set(stages, '{stages}', ("
        "SELECT jsonb_agg(CASE "
        "WHEN stage->>'message' ~ '(https?://|-> HTTP [0-9]+)' "
        "THEN jsonb_set(stage, '{message}', "
        "to_jsonb('An internal error occurred'::text)) "
        "ELSE stage END ORDER BY place) "
        "FROM jsonb_array_elements(stages->'stages') "
        "WITH ORDINALITY AS held(stage, place))) "
        "WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(stages->'stages') AS stage "
        "WHERE stage->>'message' ~ '(https?://|-> HTTP [0-9]+)')"
    )


def downgrade() -> None:
    pass
