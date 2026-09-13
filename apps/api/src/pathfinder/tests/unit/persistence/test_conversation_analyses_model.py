"""PathFinder stores a reference to the upstream analysis and nothing else."""

from __future__ import annotations

from sqlalchemy import Table

from pathfinder.persistence.models import (
    ConversationAnalysis,
    ConversationAnalysisView,
)

_ANALYSES: Table = ConversationAnalysis.metadata.tables["conversation_analyses"]


def test_the_table_is_named_by_the_contract() -> None:
    assert ConversationAnalysis.__tablename__ == "conversation_analyses"


def test_the_conversation_is_the_primary_key_so_one_analysis_is_bound() -> None:
    keys = [c.name for c in _ANALYSES.primary_key.columns]
    assert keys == ["conversation_id"]


def test_the_row_holds_only_the_reference_its_revision_and_the_preview() -> None:
    """Storing the descriptor would create a copy that drifts on the next edit."""
    columns = {c.name for c in _ANALYSES.columns}
    assert columns == {
        "conversation_id",
        "site_id",
        "dataset_id",
        "analysis_id",
        "revision",
        "subset_previewed",
        "created_at",
    }


def test_the_conversation_foreign_key_cascades() -> None:
    fks = list(ConversationAnalysis.__table__.c.conversation_id.foreign_keys)
    assert len(fks) == 1
    assert fks[0].column.table.name == "conversations"
    assert fks[0].ondelete == "CASCADE"


def test_the_revision_starts_at_zero_and_is_never_null() -> None:
    """The mutation counter is what the reconcile rule orders two surfaces by."""
    revision = ConversationAnalysis.__table__.c.revision
    assert revision.nullable is False
    assert revision.server_default.arg == "0"


def test_the_view_reads_the_reference_and_refuses_anything_else() -> None:
    view = ConversationAnalysisView.model_validate(
        {
            "site_id": "plasmodb",
            "dataset_id": "DS_53f554ec6a",
            "analysis_id": "t4fszEJ",
            "revision": 3,
        }
    )
    assert view.dataset_id == "DS_53f554ec6a"
    assert view.revision == 3
    assert set(ConversationAnalysisView.model_fields) == {
        "site_id",
        "dataset_id",
        "analysis_id",
        "revision",
        "subset_previewed",
    }


def test_the_preview_of_the_subset_is_recorded_on_the_analysis() -> None:
    """The export follows the count, and the count outlives its message."""
    previewed = ConversationAnalysis.__table__.c.subset_previewed
    assert previewed.nullable is False
    assert previewed.server_default.arg == "false"
